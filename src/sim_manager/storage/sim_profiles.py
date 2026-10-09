"""Bounded SIM metadata stores; production files use current-user Windows DPAPI.

Only names, optional phones, carrier choices, UUIDs and fingerprints persist.
Active flags and account state are runtime values and are always reset on load.
"""

from __future__ import annotations

from dataclasses import replace
import ctypes
import json
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from sim_manager.account_models import AccountState
from sim_manager.sim_models import SimCarrier, SimProfile

MAX_PROFILES = 100
MAX_PLAIN_BYTES = 65536
MAX_FILE_BYTES = 131072
_FIELDS = frozenset({"profile_id", "name", "phone_number", "carrier", "identity_key"})
_ENTROPY = b"SIMManager:SIMProfiles:metadata:v1"
_ERROR = "SIM profile storage is unavailable."


class SimProfileStoreError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(_ERROR)


class SimProfileStore(Protocol):
    def load(self) -> tuple[SimProfile, ...]: ...
    def save(self, profiles: tuple[SimProfile, ...]) -> None: ...


class ProfileProtection(Protocol):
    def protect(self, plaintext: bytearray) -> bytearray: ...
    def unprotect(self, encrypted: bytearray) -> bytearray: ...


def _metadata(profiles: object) -> tuple[SimProfile, ...]:
    if not isinstance(profiles, tuple) or len(profiles) > MAX_PROFILES:
        raise SimProfileStoreError()
    result = []
    ids: set[str] = set()
    identities: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, SimProfile) or profile.profile_id in ids or profile.identity_key is not None and profile.identity_key in identities:
            raise SimProfileStoreError()
        ids.add(profile.profile_id)
        if profile.identity_key is not None:
            identities.add(profile.identity_key)
        result.append(replace(profile, active=False, account_state=AccountState()))
    return tuple(result)


def _encode(profiles: tuple[SimProfile, ...]) -> bytearray:
    items = [{
        "profile_id": profile.profile_id,
        "name": profile.name,
        "phone_number": profile.phone_number,
        "carrier": profile.carrier.value,
        "identity_key": profile.identity_key,
    } for profile in _metadata(profiles)]
    encoded = bytearray(json.dumps({"version": 1, "profiles": items}, ensure_ascii=True, separators=(",", ":")).encode("utf-8"))
    if len(encoded) > MAX_PLAIN_BYTES:
        encoded[:] = b"\x00" * len(encoded)
        raise SimProfileStoreError()
    return encoded


def _decode(plaintext: bytearray) -> tuple[SimProfile, ...]:
    if not isinstance(plaintext, bytearray) or not 1 <= len(plaintext) <= MAX_PLAIN_BYTES:
        raise SimProfileStoreError()
    failed = False
    result: tuple[SimProfile, ...] = ()
    try:
        payload = json.loads(plaintext.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"version", "profiles"} or type(payload["version"]) is not int or payload["version"] != 1:
            raise ValueError()
        rows = payload["profiles"]
        if not isinstance(rows, list) or len(rows) > MAX_PROFILES:
            raise ValueError()
        profiles = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != _FIELDS:
                raise ValueError()
            profiles.append(SimProfile(
                profile_id=row["profile_id"], name=row["name"],
                phone_number=row["phone_number"], carrier=SimCarrier(row["carrier"]),
                identity_key=row["identity_key"],
            ))
        result = _metadata(tuple(profiles))
    except Exception as error:
        error.__traceback__ = None
        error.__context__ = None
        error.__cause__ = None
        failed = True
    if failed:
        raise SimProfileStoreError() from None
    return result


class MemorySimProfileStore:
    """Explicit isolated metadata storage for tests, demos and injected apps."""

    def __init__(self, profiles: tuple[SimProfile, ...] = ()) -> None:
        self._profiles = _metadata(profiles)

    def load(self) -> tuple[SimProfile, ...]:
        return _metadata(self._profiles)

    def save(self, profiles: tuple[SimProfile, ...]) -> None:
        self._profiles = _metadata(profiles)

    def __repr__(self) -> str:
        return "MemorySimProfileStore(<details omitted>)"


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


class _WindowsProfileProtection:
    """Load native libraries only when an explicit protect/unprotect runs."""

    def _transform(self, value: bytearray, *, protect: bool) -> bytearray:
        if os.name != "nt" or not isinstance(value, bytearray) or not 1 <= len(value) <= MAX_FILE_BYTES:
            raise SimProfileStoreError()
        failed = False
        output = _DataBlob()
        owned_input = None
        entropy_buffer = None
        local_free = None
        result = bytearray()
        try:
            crypt = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
            kernel = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
            local_free = kernel.LocalFree
            local_free.argtypes = [ctypes.c_void_p]
            local_free.restype = ctypes.c_void_p
            operation = crypt.CryptProtectData if protect else crypt.CryptUnprotectData
            operation.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_wchar_p if protect else ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(_DataBlob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(_DataBlob)]
            operation.restype = ctypes.c_int
            owned_input = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
            entropy_buffer = (ctypes.c_ubyte * len(_ENTROPY)).from_buffer_copy(_ENTROPY)
            input_blob = _DataBlob(len(value), owned_input)
            entropy_blob = _DataBlob(len(_ENTROPY), entropy_buffer)
            # No machine-scope flag: protection belongs to the current user.
            # UI_FORBIDDEN prevents a native prompt during an ordinary metadata read.
            if not operation(ctypes.byref(input_blob), None, ctypes.byref(entropy_blob), None, None, 1, ctypes.byref(output)):
                raise ValueError()
            bound = MAX_FILE_BYTES if protect else MAX_PLAIN_BYTES
            if not output.pbData or not 1 <= output.cbData <= bound:
                raise ValueError()
            result = bytearray(ctypes.string_at(output.pbData, output.cbData))
        except Exception as error:
            error.__traceback__ = None
            error.__context__ = None
            error.__cause__ = None
            failed = True
        finally:
            try:
                if owned_input is not None:
                    ctypes.memset(owned_input, 0, len(value))
                if entropy_buffer is not None:
                    ctypes.memset(entropy_buffer, 0, len(_ENTROPY))
                if output.pbData and local_free is not None:
                    # On valid output wipe the native allocation before release.
                    if output.cbData <= MAX_FILE_BYTES:
                        ctypes.memset(output.pbData, 0, output.cbData)
                    local_free(ctypes.cast(output.pbData, ctypes.c_void_p))
            except Exception as error:
                error.__traceback__ = None
                error.__context__ = None
                error.__cause__ = None
                failed = True
        if failed:
            result[:] = b"\x00" * len(result)
            raise SimProfileStoreError() from None
        return result

    def protect(self, plaintext: bytearray) -> bytearray:
        return self._transform(plaintext, protect=True)

    def unprotect(self, encrypted: bytearray) -> bytearray:
        return self._transform(encrypted, protect=False)


class WindowsSimProfileStore:
    def __init__(self, path: Path | str | None = None, *, protection: ProfileProtection | None = None) -> None:
        if path is not None and not isinstance(path, (str, Path)):
            raise SimProfileStoreError()
        self._path = Path(path) if path is not None else None
        self._protection = protection if protection is not None else _WindowsProfileProtection()

    def _location(self) -> Path:
        if self._path is not None:
            return self._path
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data or not Path(local_app_data).is_absolute():
            raise SimProfileStoreError()
        return Path(local_app_data) / "SIM Manager" / "sim-profiles.dpapi"

    def load(self) -> tuple[SimProfile, ...]:
        encrypted = bytearray()
        plaintext = bytearray()
        failed = False
        result: tuple[SimProfile, ...] = ()
        try:
            path = self._location()
            try:
                with path.open("rb") as stream:
                    encrypted = bytearray(stream.read(MAX_FILE_BYTES + 1))
            except FileNotFoundError:
                return ()
            if not 1 <= len(encrypted) <= MAX_FILE_BYTES:
                raise ValueError()
            plaintext = self._protection.unprotect(encrypted)
            result = _decode(plaintext)
        except Exception as error:
            error.__traceback__ = None
            error.__context__ = None
            error.__cause__ = None
            failed = True
        finally:
            encrypted[:] = b"\x00" * len(encrypted)
            if isinstance(plaintext, bytearray):
                plaintext[:] = b"\x00" * len(plaintext)
        if failed:
            raise SimProfileStoreError() from None
        return result

    def save(self, profiles: tuple[SimProfile, ...]) -> None:
        plaintext = bytearray()
        encrypted = bytearray()
        temporary: Path | None = None
        failed = False
        try:
            plaintext = _encode(profiles)
            encrypted = self._protection.protect(plaintext)
            if not isinstance(encrypted, bytearray) or not 1 <= len(encrypted) <= MAX_FILE_BYTES:
                raise ValueError()
            path = self._location()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
        except Exception as error:
            error.__traceback__ = None
            error.__context__ = None
            error.__cause__ = None
            failed = True
        finally:
            if isinstance(plaintext, bytearray):
                plaintext[:] = b"\x00" * len(plaintext)
            if isinstance(encrypted, bytearray):
                encrypted[:] = b"\x00" * len(encrypted)
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        if failed:
            raise SimProfileStoreError() from None

    def __repr__(self) -> str:
        return "WindowsSimProfileStore(<details omitted>)"

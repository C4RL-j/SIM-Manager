"""D2 admin credentials in the current Windows user's local credential set.

The app-specific generic credential contains a bounded versioned UTF-16LE blob.
It uses CRED_PERSIST_LOCAL_MACHINE, which persists for this user on this computer
without roaming. Both login fields stay inside the credential blob; UserName
metadata is unset. There is no file/database, MyDITO session or Qt dependency.

Native contract: Microsoft Learn CREDENTIALW, CredReadW, CredWriteW, CredDeleteW
and CredFree under /windows/win32/api/wincred/. DLL access is lazy. Native read
allocations and mutable temporary blobs are wiped before release where possible;
Python strings returned for sign-in cannot be reliably erased from memory.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from hashlib import sha256
import ipaddress
import os
from typing import Protocol
from urllib.parse import urlsplit


_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168
_MAX_BLOB_BYTES = 5 * 512
_MAGIC = b"SMD2\x01\x00"
_HEADER_BYTES = len(_MAGIC) + 4
_TARGET_PREFIX = "SIMManager:D2:admin:v1:"
_ERROR_MESSAGE = "Router credential storage is unavailable."


class CredentialStoreError(Exception):
    """A closed error without native detail, credential values or raw context."""

    def __init__(self) -> None:
        super().__init__(_ERROR_MESSAGE)


@dataclass(frozen=True, slots=True, repr=False)
class RememberedD2Login:
    username: str
    password: str

    def __repr__(self) -> str:
        return "RememberedD2Login(<details omitted>)"


class CredentialBackend(Protocol):
    """Injectable opaque-blob boundary; tests must use an offline backend.

    read returns an owned mutable blob that the store wipes after decoding.
    write consumes the blob synchronously; it must not retain caller memory.
    Missing read returns None and deleting a missing target is idempotent.
    """

    def read(self, target: str) -> bytearray | None:
        ...

    def write(self, target: str, blob: bytearray) -> None:
        ...

    def delete(self, target: str) -> None:
        ...


def _discard_exception(error: BaseException) -> None:
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        pending.extend(value for value in (current.__cause__, current.__context__)
                       if value is not None)
        current.__traceback__ = None
        current.__cause__ = None
        current.__context__ = None


def _wipe(blob: bytearray | None) -> None:
    if type(blob) is bytearray and blob:
        ctypes.memset((ctypes.c_ubyte * len(blob)).from_buffer(blob), 0, len(blob))


def _target_for(origin: str) -> str:
    canonical: str | None = None
    try:
        if (type(origin) is str and len(origin) <= 512 and origin
                and "\\" not in origin
                and not any(ord(char) < 33 or ord(char) == 127 for char in origin)):
            parts = urlsplit(origin)
            address = ipaddress.ip_address(parts.hostname or "")
            port = parts.port if parts.port is not None else 443
            if (parts.scheme == "https" and address.is_private
                    and not address.is_unspecified and not address.is_multicast
                    and parts.username is None and parts.password is None
                    and parts.path in ("", "/") and not parts.query
                    and not parts.fragment and "%" not in str(address)
                    and 1 <= port <= 65535):
                host = f"[{address}]" if address.version == 6 else str(address)
                authority = host if port == 443 else f"{host}:{port}"
                canonical = f"https://{authority}"
    except Exception as error:
        _discard_exception(error)
    finally:
        origin = None
    if canonical is None:
        raise CredentialStoreError()
    return _TARGET_PREFIX + sha256(canonical.encode("ascii")).hexdigest()


def _encode_login(username: str, password: str) -> bytearray:
    result: bytearray | None = None
    username_blob: bytearray | None = None
    password_blob: bytearray | None = None
    try:
        if (type(username) is str and type(password) is str
                and username.strip() and password
                and len(username) <= 256 and len(password) <= 1280
                and "\x00" not in username and "\x00" not in password):
            username_blob = bytearray(username, "utf-16-le", errors="strict")
            password_blob = bytearray(password, "utf-16-le", errors="strict")
            total = _HEADER_BYTES + len(username_blob) + len(password_blob)
            if len(username_blob) <= 512 and total <= _MAX_BLOB_BYTES:
                result = bytearray(_MAGIC)
                result.extend(len(username_blob).to_bytes(2, "little"))
                result.extend(len(password_blob).to_bytes(2, "little"))
                result.extend(username_blob)
                result.extend(password_blob)
    except Exception as error:
        _discard_exception(error)
    finally:
        username = password = None
        _wipe(username_blob)
        _wipe(password_blob)
    if result is None:
        raise CredentialStoreError()
    return result


def _decode_login(blob: bytearray) -> RememberedD2Login:
    result: RememberedD2Login | None = None
    username = password = None
    view = None
    try:
        if (type(blob) is bytearray and _HEADER_BYTES <= len(blob) <= _MAX_BLOB_BYTES
                and blob[:len(_MAGIC)] == _MAGIC):
            username_bytes = int.from_bytes(blob[len(_MAGIC):len(_MAGIC) + 2], "little")
            password_bytes = int.from_bytes(blob[len(_MAGIC) + 2:_HEADER_BYTES], "little")
            if (0 < username_bytes <= 512 and username_bytes % 2 == 0
                    and password_bytes > 0 and password_bytes % 2 == 0
                    and _HEADER_BYTES + username_bytes + password_bytes == len(blob)):
                boundary = _HEADER_BYTES + username_bytes
                view = memoryview(blob)
                username = str(view[_HEADER_BYTES:boundary], "utf-16-le", errors="strict")
                password = str(view[boundary:], "utf-16-le", errors="strict")
                if (username.strip() and password
                        and "\x00" not in username and "\x00" not in password):
                    result = RememberedD2Login(username, password)
    except Exception as error:
        _discard_exception(error)
    finally:
        username = password = None
        if view is not None:
            view.release()
    if result is None:
        raise CredentialStoreError()
    return result


class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_uint32),
                ("dwHighDateTime", ctypes.c_uint32)]


class _CredentialW(ctypes.Structure):
    # Fixed 32-bit DWORDs avoid host-dependent c_ulong widths in offline tests.
    _fields_ = [
        ("Flags", ctypes.c_uint32), ("Type", ctypes.c_uint32),
        ("TargetName", ctypes.c_wchar_p), ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FileTime), ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", ctypes.c_uint32), ("AttributeCount", ctypes.c_uint32),
        ("Attributes", ctypes.c_void_p), ("TargetAlias", ctypes.c_wchar_p),
        ("UserName", ctypes.c_wchar_p),
    ]


class _WindowsCredentialBackend:
    def __init__(self, *, api=None, last_error=None) -> None:
        self._api = api
        self._last_error = last_error

    def __repr__(self) -> str:
        return "_WindowsCredentialBackend(<details omitted>)"

    def _get_api(self):
        if self._api is None:
            if os.name != "nt":
                raise CredentialStoreError()
            api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
            pointer = ctypes.POINTER(_CredentialW)
            api.CredReadW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32,
                                      ctypes.c_uint32, ctypes.POINTER(pointer)]
            api.CredReadW.restype = ctypes.c_int32
            api.CredWriteW.argtypes = [pointer, ctypes.c_uint32]
            api.CredWriteW.restype = ctypes.c_int32
            api.CredDeleteW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32]
            api.CredDeleteW.restype = ctypes.c_int32
            api.CredFree.argtypes = [ctypes.c_void_p]
            api.CredFree.restype = None
            self._last_error = ctypes.get_last_error
            self._api = api
        return self._api

    def read(self, target: str) -> bytearray | None:
        api = self._get_api()
        pointer = ctypes.POINTER(_CredentialW)()
        if not api.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            if self._last_error() == _ERROR_NOT_FOUND:
                return None
            raise CredentialStoreError()
        blob = None
        size = 0
        credential = None
        failed = False
        try:
            if not pointer:
                raise CredentialStoreError()
            credential = pointer.contents
            size = credential.CredentialBlobSize
            if (credential.Type != _CRED_TYPE_GENERIC
                    or credential.Persist != _CRED_PERSIST_LOCAL_MACHINE
                    or not _HEADER_BYTES <= size <= _MAX_BLOB_BYTES
                    or not credential.CredentialBlob):
                raise CredentialStoreError()
            blob = bytearray(size)
            ctypes.memmove((ctypes.c_ubyte * size).from_buffer(blob),
                           credential.CredentialBlob, size)
        except Exception as error:
            _discard_exception(error)
            failed = True
        finally:
            try:
                if (credential is not None and credential.CredentialBlob
                        and 0 < size <= _MAX_BLOB_BYTES):
                    ctypes.memset(credential.CredentialBlob, 0, size)
                if pointer:
                    api.CredFree(pointer)
            except Exception as error:
                _discard_exception(error)
                failed = True
        if failed:
            _wipe(blob)
            blob = None
            raise CredentialStoreError()
        return blob

    def write(self, target: str, blob: bytearray) -> None:
        api = self._get_api()
        if type(blob) is not bytearray or not _HEADER_BYTES <= len(blob) <= _MAX_BLOB_BYTES:
            raise CredentialStoreError()
        credential = _CredentialW()
        credential.Type = _CRED_TYPE_GENERIC
        credential.TargetName = target
        credential.CredentialBlobSize = len(blob)
        credential.CredentialBlob = ctypes.cast(
            (ctypes.c_ubyte * len(blob)).from_buffer(blob), ctypes.POINTER(ctypes.c_ubyte),
        )
        credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
        try:
            if not api.CredWriteW(ctypes.byref(credential), 0):
                raise CredentialStoreError()
        finally:
            ctypes.memset(ctypes.byref(credential), 0, ctypes.sizeof(credential))

    def delete(self, target: str) -> None:
        api = self._get_api()
        if not api.CredDeleteW(target, _CRED_TYPE_GENERIC, 0):
            if self._last_error() != _ERROR_NOT_FOUND:
                raise CredentialStoreError()


class WindowsD2CredentialStore:
    """Explicit D2-only storage with a private, stable origin-scoped target."""

    def __init__(self, origin: str, *, backend: CredentialBackend | None = None) -> None:
        self._target = _target_for(origin)
        self._backend = backend

    def __repr__(self) -> str:
        return "WindowsD2CredentialStore(<details omitted>)"

    def _get_backend(self) -> CredentialBackend:
        if self._backend is None:
            self._backend = _WindowsCredentialBackend()
        return self._backend

    def load(self) -> RememberedD2Login | None:
        blob = None
        result = None
        failed = False
        try:
            blob = self._get_backend().read(self._target)
            if blob is not None:
                result = _decode_login(blob)
        except Exception as error:
            _discard_exception(error)
            failed = True
        finally:
            _wipe(blob)
            blob = None
        if failed:
            raise CredentialStoreError()
        return result

    def save(self, username: str, password: str) -> None:
        blob = None
        failed = False
        try:
            blob = _encode_login(username, password)
            self._get_backend().write(self._target, blob)
        except Exception as error:
            _discard_exception(error)
            failed = True
        finally:
            username = password = None
            _wipe(blob)
            blob = None
        if failed:
            raise CredentialStoreError()

    def delete(self) -> None:
        failed = False
        try:
            self._get_backend().delete(self._target)
        except Exception as error:
            _discard_exception(error)
            failed = True
        if failed:
            raise CredentialStoreError()

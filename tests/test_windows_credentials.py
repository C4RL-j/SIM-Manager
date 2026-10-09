"""Offline Windows credential contract; no real vault or router is accessed."""

from __future__ import annotations

import contextlib
import ctypes
from dataclasses import FrozenInstanceError
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

from sim_manager.storage import windows_credentials as credentials


ORIGIN = "https://192.168.1.1"
USERNAME = "SyntheticAdmin42"
PASSWORD = "Synthetic private password 246810"


class MemoryBackend:
    def __init__(self):
        self.records = {}
        self.calls = []
        self.last_read = None
        self.last_write = None

    def read(self, target):
        self.calls.append(("read", target))
        value = self.records.get(target)
        self.last_read = bytearray(value) if value is not None else None
        return self.last_read

    def write(self, target, blob):
        self.calls.append(("write", target))
        self.last_write = blob
        self.records[target] = bytearray(blob)

    def delete(self, target):
        self.calls.append(("delete", target))
        self.records.pop(target, None)


class NativeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self.callback(*args)


class NativeAPI:
    """Real ctypes layouts and fake native functions, without loading a DLL."""

    def __init__(self, payload=None):
        self.payload = bytearray(payload if payload is not None else credentials._encode_login(USERNAME, PASSWORD))
        self.error = 5
        self.read_success = True
        self.write_success = True
        self.delete_success = True
        self.read_type = 1
        self.read_persist = 2
        self.read_size = len(self.payload)
        self.null_read_pointer = False
        self.null_blob_pointer = False
        self.read_blob = None
        self.read_credential = None
        self.calls = []
        self.write_metadata = None
        self.write_blob = None
        self.freed_blob = None
        self.CredReadW = NativeFunction(self._read)
        self.CredWriteW = NativeFunction(self._write)
        self.CredDeleteW = NativeFunction(self._delete)
        self.CredFree = NativeFunction(self._free)

    def _read(self, target, credential_type, flags, output):
        self.calls.append(("read", target, credential_type, flags))
        if not self.read_success:
            return 0
        if self.null_read_pointer:
            return 1
        self.read_blob = (ctypes.c_ubyte * len(self.payload)).from_buffer_copy(self.payload)
        self.read_credential = credentials._CredentialW()
        self.read_credential.Type = self.read_type
        self.read_credential.Persist = self.read_persist
        self.read_credential.CredentialBlobSize = self.read_size
        if not self.null_blob_pointer:
            self.read_credential.CredentialBlob = ctypes.cast(self.read_blob, ctypes.POINTER(ctypes.c_ubyte))
        ctypes.cast(output, ctypes.POINTER(ctypes.POINTER(credentials._CredentialW)))[0] = ctypes.pointer(self.read_credential)
        return 1

    def _write(self, pointer, flags):
        self.calls.append(("write", flags))
        value = ctypes.cast(pointer, ctypes.POINTER(credentials._CredentialW)).contents
        self.write_metadata = (value.Type, value.Persist, value.Flags,
                               value.AttributeCount, value.UserName, value.Comment,
                               value.TargetAlias, value.TargetName)
        self.write_blob = bytearray(value.CredentialBlob[:value.CredentialBlobSize])
        return int(self.write_success)

    def _delete(self, target, credential_type, flags):
        self.calls.append(("delete", target, credential_type, flags))
        return int(self.delete_success)

    def _free(self, pointer):
        self.calls.append(("free",))
        self.freed_blob = bytes(self.read_blob) if self.read_blob is not None else None

    def backend(self):
        return credentials._WindowsCredentialBackend(api=self, last_error=lambda: self.error)


class RememberedLoginTests(unittest.TestCase):
    def test_fields_are_available_only_through_explicit_private_access(self):
        value = credentials.RememberedD2Login(USERNAME, PASSWORD)
        self.assertEqual(value.username, USERNAME)
        self.assertEqual(value.password, PASSWORD)
        self.assertEqual(repr(value), "RememberedD2Login(<details omitted>)")
        self.assertEqual(str(value), "RememberedD2Login(<details omitted>)")

    def test_model_is_frozen_without_arbitrary_attributes(self):
        value = credentials.RememberedD2Login(USERNAME, PASSWORD)
        with self.assertRaises(FrozenInstanceError):
            value.password = "Synthetic replacement"
        self.assertFalse(hasattr(value, "__dict__"))

    def test_wrongly_typed_fields_are_still_opaque(self):
        value = credentials.RememberedD2Login({PASSWORD: USERNAME}, [PASSWORD])
        self.assertNotIn(PASSWORD, repr(value))
        self.assertNotIn(USERNAME, str(value))


class CredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.backend = MemoryBackend()
        self.store = credentials.WindowsD2CredentialStore(ORIGIN, backend=self.backend)

    def test_construction_is_inert_and_repr_hides_origin_and_credentials(self):
        self.assertEqual(self.backend.calls, [])
        self.assertEqual(repr(self.store), "WindowsD2CredentialStore(<details omitted>)")
        self.assertNotIn(ORIGIN, str(self.store))

    def test_missing_load_and_delete_are_idempotent(self):
        self.assertIsNone(self.store.load())
        self.store.delete()
        self.store.delete()
        self.assertIsNone(self.store.load())

    def test_save_load_delete_round_trip_with_alphanumeric_username(self):
        self.store.save(USERNAME, PASSWORD)
        saved = self.store.load()
        self.assertEqual(saved.username, USERNAME)
        self.assertEqual(saved.password, PASSWORD)
        self.store.delete()
        self.assertIsNone(self.store.load())

    def test_save_replaces_only_the_same_origin_credential(self):
        other = credentials.WindowsD2CredentialStore("https://192.168.1.2", backend=self.backend)
        self.store.save(USERNAME, PASSWORD)
        other.save("SyntheticOther99", "Synthetic other password")
        self.store.save("SyntheticReplacement88", "Synthetic new password")
        self.assertEqual(self.store.load().username, "SyntheticReplacement88")
        self.assertEqual(other.load().username, "SyntheticOther99")
        self.store.delete()
        self.assertIsNotNone(other.load())

    def test_canonical_origin_variations_share_one_scoped_target(self):
        variants = (ORIGIN, ORIGIN + "/", ORIGIN + ":443", ORIGIN + ":443/")
        targets = {credentials.WindowsD2CredentialStore(value, backend=self.backend)._target for value in variants}
        self.assertEqual(len(targets), 1)
        self.assertTrue(next(iter(targets)).startswith("SIMManager:D2:admin:v1:"))
        self.assertNotIn("192.168.1.1", next(iter(targets)))

    def test_private_ipv6_and_nondefault_ports_are_scoped_independently(self):
        values = ("https://[fd00::1]", "https://[fd00:0:0:0:0:0:0:1]:443/",
                  "https://[fd00::1]:8443", ORIGIN + ":8443")
        targets = [credentials.WindowsD2CredentialStore(value, backend=self.backend)._target for value in values]
        self.assertEqual(targets[0], targets[1])
        self.assertEqual(len(set(targets)), 3)

    def test_untrusted_or_malformed_origins_fail_closed_before_backend_access(self):
        values = ("https://my.dito.ph/", "https://smartbrosettings.net/",
                  "https://8.8.8.8", "http://192.168.1.1", ORIGIN + "/web/v1/user/login",
                  ORIGIN + "?token=SYNTHETIC", ORIGIN + "#private", "https://user:secret@192.168.1.1",
                  "https://192.168.1.1\\@evil.example/", " https://192.168.1.1",
                  "https://192.168.1.1\n/", "https://0.0.0.0", "https://224.0.0.1",
                  "https://[fd00::1%scope]", ORIGIN + ":0", ORIGIN + ":65536", None, {})
        for value in values:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(credentials.CredentialStoreError) as caught:
                    credentials.WindowsD2CredentialStore(value, backend=self.backend)
                self.assertEqual(str(caught.exception), credentials._ERROR_MESSAGE)
                self.assertIsNone(caught.exception.__context__)
        self.assertEqual(self.backend.calls, [])

    def test_unicode_fields_are_utf16_validated_and_preserved_without_trimming(self):
        self.store.save(" Synthetic用户7 ", " Synthetic café 🙂 password ")
        value = self.store.load()
        self.assertEqual(value.username, " Synthetic用户7 ")
        self.assertEqual(value.password, " Synthetic café 🙂 password ")

    def test_invalid_fields_do_not_write_or_format_private_values(self):
        class PrivateObject:
            def __str__(self):
                raise AssertionError(PASSWORD)
            def __repr__(self):
                return PASSWORD
        values = (("", PASSWORD), ("   ", PASSWORD), (USERNAME, ""),
                  (USERNAME + "\x00", PASSWORD), (USERNAME, PASSWORD + "\x00"),
                  ("\ud800", PASSWORD), (USERNAME, "\udfff"),
                  (PrivateObject(), PASSWORD), (USERNAME, PrivateObject()),
                  ("a" * 257, PASSWORD), (USERNAME, "x" * 1281))
        for username, password in values:
            with self.subTest(value_types=(type(username).__name__, type(password).__name__)):
                with self.assertRaises(credentials.CredentialStoreError) as caught:
                    self.store.save(username, password)
                self.assertEqual(caught.exception.args, (credentials._ERROR_MESSAGE,))
                self.assertIsNone(caught.exception.__cause__)
                self.assertIsNone(caught.exception.__context__)
        self.assertEqual(self.backend.calls, [])

    def test_native_maximum_blob_size_and_utf16_unit_bounds(self):
        # One ASCII username leaves precisely this many UTF-16 password units.
        maximum_password = "x" * ((2560 - credentials._HEADER_BYTES - 2) // 2)
        self.store.save("a", maximum_password)
        self.assertEqual(len(next(iter(self.backend.records.values()))), 2560)
        self.assertEqual(self.store.load().password, maximum_password)
        with self.assertRaises(credentials.CredentialStoreError):
            self.store.save("a", maximum_password + "x")
        with self.assertRaises(credentials.CredentialStoreError):
            self.store.save("🙂" * 129, PASSWORD)

    def test_mutable_write_and_read_copies_are_wiped(self):
        self.store.save(USERNAME, PASSWORD)
        self.assertTrue(self.backend.last_write)
        self.assertFalse(any(self.backend.last_write))
        self.assertEqual(self.store.load().password, PASSWORD)
        self.assertFalse(any(self.backend.last_read))

    def test_malformed_blobs_fail_closed_and_are_wiped(self):
        good = credentials._encode_login(USERNAME, PASSWORD)
        malformed = [bytearray(), bytearray(b"bad-version"), good + b"\x00", good[:-1],
                     bytearray(b"x" * 2561), bytearray(good)]
        malformed[-1][-2:] = b"\x00\xd8"  # Unpaired high surrogate.
        for blob in malformed:
            with self.subTest(size=len(blob)):
                self.backend.records[self.store._target] = blob
                with self.assertRaises(credentials.CredentialStoreError) as caught:
                    self.store.load()
                self.assertEqual(str(caught.exception), credentials._ERROR_MESSAGE)
                self.assertIsNone(caught.exception.__context__)
                self.assertFalse(any(self.backend.last_read))

    def test_empty_nul_and_bad_length_blob_fields_are_rejected(self):
        values = (("a", "\x00"), (" ", "a"), ("a", ""))
        for username, password in values:
            username_data = username.encode("utf-16-le")
            password_data = password.encode("utf-16-le")
            blob = bytearray(credentials._MAGIC + len(username_data).to_bytes(2, "little")
                             + len(password_data).to_bytes(2, "little") + username_data + password_data)
            self.backend.records[self.store._target] = blob
            with self.assertRaises(credentials.CredentialStoreError):
                self.store.load()
        blob = credentials._encode_login(USERNAME, PASSWORD)
        blob[len(credentials._MAGIC):len(credentials._MAGIC) + 2] = b"\x01\x00"
        self.backend.records[self.store._target] = blob
        with self.assertRaises(credentials.CredentialStoreError):
            self.store.load()

    def test_wrong_backend_result_types_are_not_coerced_or_exposed(self):
        for value in (b"synthetic private bytes", PASSWORD, {PASSWORD: USERNAME}, True):
            backend = Mock()
            backend.read.return_value = value
            store = credentials.WindowsD2CredentialStore(ORIGIN, backend=backend)
            with self.assertRaises(credentials.CredentialStoreError) as caught:
                store.load()
            self.assertEqual(caught.exception.args, (credentials._ERROR_MESSAGE,))

    def test_raw_backend_errors_and_chains_are_removed(self):
        for operation in ("read", "write", "delete"):
            with self.subTest(operation=operation):
                inner = ValueError(PASSWORD)
                outer = RuntimeError(USERNAME, PASSWORD)
                outer.__cause__ = inner
                backend = Mock()
                getattr(backend, operation).side_effect = outer
                store = credentials.WindowsD2CredentialStore(ORIGIN, backend=backend)
                with self.assertRaises(credentials.CredentialStoreError) as caught:
                    if operation == "write":
                        store.save(USERNAME, PASSWORD)
                    elif operation == "read":
                        store.load()
                    else:
                        store.delete()
                self.assertEqual(caught.exception.args, (credentials._ERROR_MESSAGE,))
                self.assertIsNone(caught.exception.__context__)
                self.assertIsNone(caught.exception.__cause__)
                self.assertIsNone(outer.__traceback__)
                self.assertIsNone(outer.__cause__)
                self.assertIsNone(inner.__traceback__)

    def test_write_failure_wipes_the_supplied_blob(self):
        captured = []
        def fail(target, blob):
            captured.append(blob)
            raise RuntimeError(PASSWORD)
        self.backend.write = fail
        with self.assertRaises(credentials.CredentialStoreError):
            self.store.save(USERNAME, PASSWORD)
        self.assertFalse(any(captured[0]))

    def test_no_stdout_stderr_logs_files_or_network_io(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), self.assertNoLogs(level="DEBUG"), \
                patch("builtins.open", side_effect=AssertionError("File access forbidden")), \
                patch("socket.create_connection", side_effect=AssertionError("Network forbidden")):
            self.store.save(USERNAME, PASSWORD)
            self.assertEqual(self.store.load().password, PASSWORD)
            self.store.delete()
        self.assertEqual(output.getvalue(), "")

    def test_import_and_construction_on_nonwindows_do_not_load_dll(self):
        name = "_sim_manager_offline_windows_credentials"
        spec = importlib.util.spec_from_file_location(name, Path(credentials.__file__))
        module = importlib.util.module_from_spec(spec)
        dll = Mock(side_effect=AssertionError("Native DLL access forbidden"))
        sys.modules[name] = module
        try:
            with patch.object(ctypes, "WinDLL", dll, create=True), patch("os.name", "posix"):
                spec.loader.exec_module(module)
                store = module.WindowsD2CredentialStore(ORIGIN)
                dll.assert_not_called()
                with self.assertRaises(module.CredentialStoreError):
                    store.load()
                dll.assert_not_called()
        finally:
            sys.modules.pop(name, None)


class NativeCredentialBridgeTests(unittest.TestCase):
    def test_structure_uses_windows_field_width_and_pointer_layout(self):
        self.assertEqual(ctypes.sizeof(credentials._FileTime), 8)
        self.assertEqual(ctypes.sizeof(credentials._CredentialW), 80 if ctypes.sizeof(ctypes.c_void_p) == 8 else 52)
        self.assertEqual(credentials._CredentialW.Type.offset, 4)
        self.assertEqual(credentials._CredentialW.TargetName.offset, 8)

    def test_native_write_is_generic_local_current_user_without_username_metadata(self):
        api = NativeAPI()
        store = credentials.WindowsD2CredentialStore(ORIGIN, backend=api.backend())
        store.save(USERNAME, PASSWORD)
        self.assertEqual(api.calls, [("write", 0)])
        self.assertEqual(api.write_metadata[:7], (1, 2, 0, 0, None, None, None))
        self.assertTrue(api.write_metadata[7].startswith("SIMManager:D2:admin:v1:"))
        decoded = credentials._decode_login(api.write_blob)
        self.assertEqual(decoded.username, USERNAME)
        self.assertEqual(decoded.password, PASSWORD)

    def test_native_read_returns_fields_and_wipes_before_credfree(self):
        api = NativeAPI()
        store = credentials.WindowsD2CredentialStore(ORIGIN, backend=api.backend())
        value = store.load()
        self.assertEqual(value.username, USERNAME)
        self.assertEqual(value.password, PASSWORD)
        self.assertEqual(api.calls[0][2:], (1, 0))
        self.assertEqual(api.calls[-1], ("free",))
        self.assertEqual(api.freed_blob, b"\x00" * len(api.payload))

    def test_native_missing_read_and_delete_do_not_raise(self):
        api = NativeAPI()
        api.error = 1168
        api.read_success = api.delete_success = False
        store = credentials.WindowsD2CredentialStore(ORIGIN, backend=api.backend())
        self.assertIsNone(store.load())
        store.delete()
        self.assertEqual([call[0] for call in api.calls], ["read", "delete"])
        self.assertEqual(api.calls[-1][2:], (1, 0))

    def test_native_access_denied_errors_are_closed_without_error_code(self):
        for operation in ("read", "write", "delete"):
            with self.subTest(operation=operation):
                api = NativeAPI()
                setattr(api, operation + "_success", False)
                api.error = 5
                store = credentials.WindowsD2CredentialStore(ORIGIN, backend=api.backend())
                with self.assertRaises(credentials.CredentialStoreError) as caught:
                    if operation == "write":
                        store.save(USERNAME, PASSWORD)
                    elif operation == "read":
                        store.load()
                    else:
                        store.delete()
                self.assertEqual(caught.exception.args, (credentials._ERROR_MESSAGE,))
                self.assertIsNone(caught.exception.__context__)

    def test_native_malformed_type_persistence_size_or_null_blob_frees_safely(self):
        cases = (("read_type", 2), ("read_persist", 3), ("read_size", 0),
                 ("read_size", 2561), ("null_blob_pointer", True))
        for field, value in cases:
            with self.subTest(field=field, value=value):
                api = NativeAPI()
                setattr(api, field, value)
                store = credentials.WindowsD2CredentialStore(ORIGIN, backend=api.backend())
                with self.assertRaises(credentials.CredentialStoreError):
                    store.load()
                self.assertEqual(api.calls[-1], ("free",))

    def test_native_success_with_null_credential_pointer_fails_closed(self):
        api = NativeAPI()
        api.null_read_pointer = True
        store = credentials.WindowsD2CredentialStore(ORIGIN, backend=api.backend())
        with self.assertRaises(credentials.CredentialStoreError):
            store.load()
        self.assertEqual(len(api.calls), 1)

    def test_native_function_exception_does_not_expose_private_text(self):
        api = NativeAPI()
        api.CredWriteW.callback = Mock(side_effect=RuntimeError(USERNAME, PASSWORD))
        store = credentials.WindowsD2CredentialStore(ORIGIN, backend=api.backend())
        with self.assertRaises(credentials.CredentialStoreError) as caught:
            store.save(USERNAME, PASSWORD)
        self.assertEqual(str(caught.exception), credentials._ERROR_MESSAGE)
        self.assertIsNone(caught.exception.__context__)

    def test_credfree_exception_is_closed_after_native_secret_wipe(self):
        api = NativeAPI()
        api.CredFree.callback = Mock(side_effect=RuntimeError(PASSWORD))
        store = credentials.WindowsD2CredentialStore(ORIGIN, backend=api.backend())
        with self.assertRaises(credentials.CredentialStoreError) as caught:
            store.load()
        self.assertFalse(any(api.read_blob))
        self.assertIsNone(caught.exception.__context__)

    def test_dll_binding_is_lazy_and_uses_exact_unicode_api_prototypes(self):
        api = NativeAPI()
        dll = Mock(return_value=api)
        with patch("os.name", "nt"), patch.object(ctypes, "WinDLL", dll, create=True), \
                patch.object(ctypes, "get_last_error", lambda: 5, create=True):
            store = credentials.WindowsD2CredentialStore(ORIGIN)
            dll.assert_not_called()
            store.delete()
        dll.assert_called_once_with("Advapi32.dll", use_last_error=True)
        self.assertEqual(api.CredReadW.argtypes[:3], [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32])
        self.assertEqual(api.CredWriteW.argtypes[1], ctypes.c_uint32)
        self.assertEqual(api.CredDeleteW.argtypes, [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32])
        self.assertIs(api.CredReadW.restype, ctypes.c_int32)
        self.assertEqual(api.CredFree.argtypes, [ctypes.c_void_p])
        self.assertIsNone(api.CredFree.restype)

    def test_dll_loader_failure_is_sanitized(self):
        with patch("os.name", "nt"), patch.object(ctypes, "WinDLL", Mock(side_effect=OSError(PASSWORD)), create=True):
            store = credentials.WindowsD2CredentialStore(ORIGIN)
            with self.assertRaises(credentials.CredentialStoreError) as caught:
                store.load()
        self.assertEqual(caught.exception.args, (credentials._ERROR_MESSAGE,))
        self.assertIsNone(caught.exception.__context__)


if __name__ == "__main__":
    unittest.main()

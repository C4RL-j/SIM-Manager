"""Synthetic startup registration; no real registry or executable is accessed."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest
from unittest.mock import patch

from sim_manager.services import windows_startup as startup


EXECUTABLE = r"C:\Synthetic portable apps\Renamed SIM Manager.exe"


class MemoryBackend:
    def __init__(self):
        self.value = None
        self.calls = []
        self.failure = None

    def _operation(self, name):
        self.calls.append(name)
        if self.failure == name:
            raise RuntimeError("SYNTHETIC_PRIVATE_PATH_AND_PROVIDER_ERROR")

    def read(self):
        self._operation("read")
        return self.value

    def write(self, command):
        self._operation("write")
        self.value = command

    def delete(self):
        self._operation("delete")
        self.value = None


class RegistryKey:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MemoryRegistry:
    HKEY_CURRENT_USER = "synthetic-HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 3

    def __init__(self):
        self.values = {"AnotherApplication": ("synthetic-unrelated-command", self.REG_SZ)}
        self.calls = []

    def OpenKey(self, hive, path, reserved, access):
        self.calls.append(("open", hive, path, reserved, access))
        return RegistryKey()

    def CreateKeyEx(self, hive, path, reserved, access):
        self.calls.append(("create", hive, path, reserved, access))
        return RegistryKey()

    def QueryValueEx(self, key, name):
        self.calls.append(("query", name))
        if name not in self.values:
            raise FileNotFoundError()
        return self.values[name]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.calls.append(("write", name, reserved, kind))
        self.values[name] = value, kind

    def DeleteValue(self, key, name):
        self.calls.append(("delete", name))
        if name not in self.values:
            raise FileNotFoundError()
        del self.values[name]


class WindowsStartupTests(unittest.TestCase):
    def test_source_launch_is_unavailable_and_never_reads_or_mutates_registry(self):
        backend = MemoryBackend()
        with patch.object(startup, "_WindowsRunBackend", side_effect=AssertionError("Real registry forbidden")):
            unavailable = startup.WindowsStartupService(frozen=False)
            service = startup.WindowsStartupService(backend, EXECUTABLE, frozen=False)
        for candidate in (unavailable, service):
            self.assertFalse(candidate.available)
            self.assertFalse(candidate.is_enabled())
            self.assertFalse(candidate.set_enabled(True))
            self.assertFalse(candidate.set_enabled(False))
            self.assertTrue(candidate.issue)
        self.assertEqual(backend.calls, [])

    def test_frozen_registration_is_opt_in_quoted_and_follows_current_renamed_executable(self):
        backend = MemoryBackend()
        with patch.object(startup.sys, "frozen", True, create=True), \
                patch.object(startup.sys, "executable", EXECUTABLE), \
                patch.object(startup.sys, "platform", "win32"), \
                patch.object(startup, "_WindowsRunBackend", return_value=backend) as native:
            service = startup.WindowsStartupService()
        native.assert_called_once_with()
        self.assertTrue(service.available)
        self.assertFalse(service.issue)
        self.assertEqual(backend.calls, [])
        self.assertFalse(service.is_enabled())
        self.assertFalse(service.issue)
        self.assertEqual(backend.calls, ["read"])
        self.assertTrue(service.set_enabled(True))
        self.assertEqual(backend.value, '"' + EXECUTABLE + '"')
        self.assertTrue(service.is_enabled())
        renamed_path = r"C:\Synthetic portable apps\My renamed portable.exe"
        renamed = startup.WindowsStartupService(backend, renamed_path, frozen=True)
        self.assertFalse(renamed.is_enabled())
        self.assertFalse(renamed.issue)
        self.assertTrue(renamed.set_enabled(True))
        self.assertEqual(backend.value, '"' + renamed_path + '"')
        self.assertTrue(renamed.is_enabled())
        self.assertTrue(renamed.set_enabled(False))
        self.assertTrue(renamed.set_enabled(False))
        self.assertIsNone(backend.value)

    def test_native_backend_uses_only_own_current_user_run_value(self):
        registry = MemoryRegistry()
        backend = startup._WindowsRunBackend(registry)
        service = startup.WindowsStartupService(backend, EXECUTABLE, frozen=True)
        self.assertEqual(registry.calls, [])
        self.assertFalse(service.is_enabled())
        self.assertTrue(service.set_enabled(True))
        self.assertTrue(service.is_enabled())
        registry.values["SIMManager"] = ('"' + EXECUTABLE + '"', registry.REG_SZ + 1)
        self.assertFalse(service.is_enabled())
        self.assertTrue(service.issue)
        self.assertTrue(service.set_enabled(True))
        self.assertTrue(service.set_enabled(False))
        self.assertTrue(service.set_enabled(False))
        self.assertEqual(registry.values,
                         {"AnotherApplication": ("synthetic-unrelated-command", registry.REG_SZ)})
        for call in registry.calls:
            if call[0] in ("open", "create"):
                self.assertEqual(call[1:4], (registry.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run", 0))
                self.assertIn(call[4], (registry.KEY_READ, registry.KEY_SET_VALUE))
            else:
                self.assertEqual(call[1], "SIMManager")

    def test_invalid_commands_and_overlong_utf16_values_are_unavailable_without_backend_access(self):
        for executable in ("", "relative.exe", r"C:relative.exe", r"\rooted.exe",
                           r"C:\app\python.exe -m sim_manager", 'C:\\app\\bad"name.exe',
                           "C:\\app\\bad\nname.exe", r"C:\app\bad:name.exe",
                           r"C:\app\bad*.exe", "C:\\" + "a" * 252 + ".exe",
                           "C:\\" + "\U0001f600" * 126 + ".exe", "C:\\bad\ud800.exe"):
            with self.subTest(kind=type(executable).__name__):
                backend = MemoryBackend()
                service = startup.WindowsStartupService(backend, executable, frozen=True)
                self.assertFalse(service.available)
                self.assertFalse(service.set_enabled(True))
                self.assertEqual(backend.calls, [])
        backend = MemoryBackend()
        at_limit = "C:\\" + "a" * 251 + ".exe"
        service = startup.WindowsStartupService(backend, at_limit, frozen=True)
        self.assertTrue(service.available)
        self.assertTrue(service.set_enabled(True))
        self.assertEqual(len(backend.value.encode("utf-16-le")) // 2, 260)

    def test_failures_wrong_value_types_and_invalid_toggle_stay_closed_and_private(self):
        output = StringIO()
        backend = MemoryBackend()
        service = startup.WindowsStartupService(backend, EXECUTABLE, frozen=True)
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            for operation in ("read", "write", "delete"):
                backend.failure = operation
                result = service.is_enabled() if operation == "read" else service.set_enabled(operation == "write")
                self.assertFalse(result)
                self.assertTrue(service.issue)
                self.assertNotIn("SYNTHETIC_PRIVATE", repr(service))
                self.assertNotIn(EXECUTABLE, repr(service))
            backend.failure = None
            for value in (True, 1, {}, []):
                backend.value = value
                self.assertFalse(service.is_enabled())
                self.assertTrue(service.issue)
            calls = len(backend.calls)
            for value in (1, 0, "true", None):
                self.assertFalse(service.set_enabled(value))
                self.assertTrue(service.issue)
            self.assertEqual(len(backend.calls), calls)
            self.assertTrue(service.set_enabled(True))
            self.assertFalse(service.issue)
            self.assertTrue(service.is_enabled())
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()

"""Explicit current-user startup registration for a frozen Windows executable.

Construction and availability checks never access the registry. Source launches
are unavailable rather than registering a developer interpreter/module command.
Only an explicit set_enabled call may change this application's Run value.
"""

from __future__ import annotations

import ntpath
import sys
from typing import Protocol


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "SIMManager"
_MAX_COMMAND_UNITS = 260


class WindowsStartupBackend(Protocol):
    """One application-owned value; missing reads/deletes are idempotent."""

    def read(self) -> str | None:
        ...

    def write(self, command: str) -> None:
        ...

    def delete(self) -> None:
        ...


class _WindowsRunBackend:
    def __init__(self, registry=None) -> None:
        if registry is None:
            import winreg
            registry = winreg
        self._registry = registry

    def __repr__(self) -> str:
        return "WindowsRunBackend(<details omitted>)"

    def read(self) -> str | None:
        registry = self._registry
        try:
            with registry.OpenKey(registry.HKEY_CURRENT_USER, _RUN_KEY, 0, registry.KEY_READ) as key:
                value, kind = registry.QueryValueEx(key, _VALUE_NAME)
        except FileNotFoundError:
            return None
        if kind != registry.REG_SZ or type(value) is not str:
            raise ValueError("Windows startup setting is unavailable.")
        return value

    def write(self, command: str) -> None:
        registry = self._registry
        with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, _RUN_KEY, 0, registry.KEY_SET_VALUE) as key:
            registry.SetValueEx(key, _VALUE_NAME, 0, registry.REG_SZ, command)

    def delete(self) -> None:
        registry = self._registry
        try:
            with registry.OpenKey(registry.HKEY_CURRENT_USER, _RUN_KEY, 0, registry.KEY_SET_VALUE) as key:
                registry.DeleteValue(key, _VALUE_NAME)
        except FileNotFoundError:
            pass


def _executable_command(executable: object) -> str | None:
    if type(executable) is not str or not executable:
        return None
    drive, tail = ntpath.splitdrive(executable)
    if (not drive or not ntpath.isabs(executable)
            or not executable.lower().endswith(".exe")
            or '"' in executable
            or any(character in '<>"|?*:' for character in tail)
            or any(ord(character) < 32 for character in executable)):
        return None
    command = '"' + executable + '"'
    try:
        # The Windows Run limit counts the complete UTF-16 command, including
        # quotes. No arguments, shell, environment expansion or working directory
        # are needed for the portable frozen application.
        if len(command.encode("utf-16-le")) // 2 <= _MAX_COMMAND_UNITS:
            return command
    except UnicodeError:
        pass
    return None


class WindowsStartupService:
    def __init__(self, backend: WindowsStartupBackend | None = None,
                 executable: str | None = None, frozen: bool | None = None) -> None:
        self._issue = False
        self._backend = None
        self._command = None
        is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        if is_frozen is not True:
            return
        command = _executable_command(sys.executable if executable is None else executable)
        if command is None:
            return
        if backend is None:
            if sys.platform != "win32":
                return
            try:
                backend = _WindowsRunBackend()
            except Exception:
                self._issue = True
                return
        self._backend, self._command = backend, command

    def __repr__(self) -> str:
        return "WindowsStartupService(<details omitted>)"

    @property
    def available(self) -> bool:
        return self._backend is not None and self._command is not None

    @property
    def issue(self) -> bool:
        return self._issue

    def is_enabled(self) -> bool:
        if not self.available:
            self._issue = True
            return False
        try:
            value = self._backend.read()
            if value is not None and type(value) is not str:
                self._issue = True
                return False
        except Exception:
            self._issue = True
            return False
        self._issue = False
        return value == self._command

    def set_enabled(self, enabled: bool) -> bool:
        if type(enabled) is not bool or not self.available:
            self._issue = True
            return False
        try:
            if enabled:
                self._backend.write(self._command)
            else:
                self._backend.delete()
        except Exception:
            self._issue = True
            return False
        self._issue = False
        return True

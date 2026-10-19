"""Public application preferences; carrier and router sessions never persist here."""

from dataclasses import dataclass

from PySide6.QtCore import QSettings


PREFERENCES_SAVE_FAILURE = "Application settings could not be saved. Changes apply for this session."
_KEYS = ("application/auto_refresh", "application/refresh_interval", "application/close_to_tray")


@dataclass(frozen=True, slots=True)
class AppPreferences:
    auto_refresh: bool = True
    refresh_interval: int = 30
    close_to_tray: bool = True

    def __post_init__(self) -> None:
        if (type(self.auto_refresh) is not bool
                or type(self.refresh_interval) is not int
                or self.refresh_interval not in (15, 30, 60)
                or type(self.close_to_tray) is not bool):
            raise ValueError("Application preferences are invalid.")


class MemoryPreferencesStore:
    """Explicit demo/injected composition uses no user settings storage."""

    def __init__(self, initial: AppPreferences = AppPreferences()) -> None:
        self._value = initial if type(initial) is AppPreferences else AppPreferences()

    def load(self) -> AppPreferences:
        return self._value

    def save(self, value: AppPreferences) -> bool:
        if type(value) is not AppPreferences:
            return False
        self._value = value
        return True


def _boolean(value: object, default: bool) -> bool:
    if type(value) is bool:
        return value
    # QSettings INI files encode booleans as these exact strings.
    if type(value) is str and value in ("true", "false"):
        return value == "true"
    return default


def _interval(value: object, default: int) -> int:
    if type(value) is int and value in (15, 30, 60):
        return value
    if type(value) is str and value in ("15", "30", "60"):
        return int(value)
    return default


class QtPreferencesStore:
    """Only three non-sensitive options use native current-user Qt settings.

    Tests inject isolated INI settings or fakes. Production constructs this
    store only for the normal application, never demo or injected providers.
    """

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings
        if settings is None:
            try:
                self._settings = QSettings(
                    QSettings.Format.NativeFormat, QSettings.Scope.UserScope,
                    "SIM Manager", "SIM Manager",
                )
            except Exception:
                # Native settings failure must not prevent application startup.
                self._settings = None

    def load(self) -> AppPreferences:
        defaults = AppPreferences()
        try:
            self._settings.sync()
            if self._settings.status() != QSettings.Status.NoError:
                return defaults
            values = tuple(self._settings.value(key) for key in _KEYS)
            if self._settings.status() != QSettings.Status.NoError:
                return defaults
            return AppPreferences(
                auto_refresh=_boolean(values[0], defaults.auto_refresh),
                refresh_interval=_interval(values[1], defaults.refresh_interval),
                close_to_tray=_boolean(values[2], defaults.close_to_tray),
            )
        except Exception:
            return defaults

    def save(self, value: AppPreferences) -> bool:
        if type(value) is not AppPreferences:
            return False
        try:
            for key, setting in zip(_KEYS, (value.auto_refresh, value.refresh_interval, value.close_to_tray)):
                self._settings.setValue(key, setting)
            self._settings.sync()
            return self._settings.status() == QSettings.Status.NoError
        except Exception:
            return False

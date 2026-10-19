"""Router and application settings, independent of SIM account controls."""

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFormLayout, QFrame, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from sim_manager.models import DeviceState
from sim_manager import __version__
from sim_manager.services.presentation import DeviceView, present_device
from sim_manager.ui.pages.overview import OverviewPage
from sim_manager.ui.preferences import AppPreferences, PREFERENCES_SAVE_FAILURE


class _ConnectionDetails(OverviewPage):
    """Keep the existing diagnostic fields and rendering, at settings scale."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.layout().takeAt(self.layout().count() - 1)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

    def _field(self, name: str, key: str, *, primary: bool = False, compact: bool = False) -> QVBoxLayout:
        return super()._field("Router carrier" if key == "carrier" else name,
                              key, compact=True)


class SettingsPage(QWidget):
    preferences_changed = Signal(object)
    startup_requested = Signal(bool)

    def __init__(self, parent: QWidget | None = None, *, router_address: str | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._preferences = AppPreferences()
        self._tray_available = False
        self.router_address_label = QLabel(router_address or "192.168.1.1 (default)")
        self.router_address_label.setTextFormat(Qt.TextFormat.PlainText)
        self.router_address_label.setWordWrap(True)
        self.connection_label = QLabel("Unknown")
        self.connection_label.setTextFormat(Qt.TextFormat.PlainText)
        self.connection_label.setWordWrap(True)
        router_group = self._group("Router information", (
            ("Router address", self.router_address_label), ("Status", self.connection_label),
        ))
        self.saved_login_note = QLabel()
        self.saved_login_note.setTextFormat(Qt.TextFormat.PlainText)
        self.saved_login_note.setWordWrap(True)
        self.saved_login_note.setObjectName("muted")
        self.saved_login_note.hide()
        self.forget_login_button = QPushButton("Forget saved login")
        self.forget_login_button.setAccessibleName("Forget saved D2 router login")
        self.forget_login_button.hide()
        router_group.layout().addWidget(self.saved_login_note)
        router_group.layout().addWidget(self.forget_login_button)
        layout.addWidget(router_group)
        self.connection_details_toggle = QPushButton("▸ Connection details")
        self.connection_details_toggle.setCheckable(True)
        self.connection_details_toggle.setAccessibleName("Connection details")
        self.connection_details_toggle.setAccessibleDescription("Expand router and signal diagnostics")
        layout.addWidget(self.connection_details_toggle)
        self.connection_details = _ConnectionDetails()
        self.connection_values = self.connection_details.values
        self.connection_details.hide()
        layout.addWidget(self.connection_details)
        self.connection_details_toggle.toggled.connect(self._toggle_connection_details)
        layout.addWidget(self._preferences_group())
        layout.addWidget(self._group("Application information", (
            ("Name", QLabel("SIM Manager")), ("Version", QLabel(__version__)),
        )))
        note = QLabel("Router settings are read-only in this version.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        self.render(present_device(DeviceState()))

    def _preferences_group(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        content = QVBoxLayout(card)
        content.setContentsMargins(18, 16, 18, 18)
        content.setSpacing(10)
        heading = QLabel("Application behavior")
        heading.setObjectName("cardTitle")
        content.addWidget(heading)
        self.auto_refresh_toggle = QCheckBox("Auto-refresh")
        self.auto_refresh_toggle.setAccessibleName("Enable automatic refresh")
        content.addWidget(self.auto_refresh_toggle)
        self.refresh_interval_combo = QComboBox()
        self.refresh_interval_combo.setAccessibleName("Automatic refresh interval")
        for seconds in (15, 30, 60):
            self.refresh_interval_combo.addItem(f"{seconds} seconds", seconds)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        interval_label = QLabel("Refresh interval")
        interval_label.setObjectName("muted")
        form.addRow(interval_label, self.refresh_interval_combo)
        content.addLayout(form)
        self.start_with_windows_toggle = QCheckBox("Start with Windows")
        self.start_with_windows_toggle.setAccessibleName("Start with Windows")
        content.addWidget(self.start_with_windows_toggle)
        self.startup_notice_label = QLabel()
        self.startup_notice_label.setObjectName("muted")
        self.startup_notice_label.setTextFormat(Qt.TextFormat.PlainText)
        self.startup_notice_label.setWordWrap(True)
        self.startup_notice_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        content.addWidget(self.startup_notice_label)
        self.set_startup_state(False, False)
        self.start_with_windows_toggle.toggled.connect(self.startup_requested)
        self.close_to_tray_toggle = QCheckBox("Keep running in tray when\nclosing window")
        self.close_to_tray_toggle.setAccessibleName("Keep running in tray when closing window")
        content.addWidget(self.close_to_tray_toggle)
        self.tray_notice_label = QLabel()
        self.preferences_notice_label = QLabel()
        for label in (self.tray_notice_label, self.preferences_notice_label):
            label.setObjectName("muted")
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            content.addWidget(label)
        self.preferences_notice_label.hide()
        self.set_preferences(self._preferences)
        self.set_tray_available(self._tray_available)
        self.auto_refresh_toggle.toggled.connect(self._preferences_edited)
        self.refresh_interval_combo.currentIndexChanged.connect(self._preferences_edited)
        self.close_to_tray_toggle.toggled.connect(self._preferences_edited)
        return card

    def set_startup_state(self, enabled: bool, available: bool, *, failed: bool = False) -> None:
        with QSignalBlocker(self.start_with_windows_toggle):
            self.start_with_windows_toggle.setChecked(enabled is True)
        self.start_with_windows_toggle.setEnabled(available is True)
        self.startup_notice_label.setText(
            "Windows startup could not be updated. Try again." if failed else
            "Starts SIM Manager when you sign in to Windows." if available else
            "Start with Windows is available in the Windows executable."
        )

    def set_preferences(self, preferences: AppPreferences) -> None:
        """Apply stored/runtime options without creating a user edit signal."""
        self._preferences = preferences if type(preferences) is AppPreferences else AppPreferences()
        with (QSignalBlocker(self.auto_refresh_toggle), QSignalBlocker(self.refresh_interval_combo),
              QSignalBlocker(self.close_to_tray_toggle)):
            self.auto_refresh_toggle.setChecked(self._preferences.auto_refresh)
            self.refresh_interval_combo.setCurrentIndex(
                self.refresh_interval_combo.findData(self._preferences.refresh_interval),
            )
            self.close_to_tray_toggle.setChecked(self._preferences.close_to_tray)
        self.refresh_interval_combo.setEnabled(self._preferences.auto_refresh)
        self.close_to_tray_toggle.setEnabled(self._tray_available)

    def set_tray_available(self, available: bool) -> None:
        """A missing tray changes availability, not the saved user's option."""
        self._tray_available = available is True
        self.close_to_tray_toggle.setEnabled(self._tray_available)
        self.tray_notice_label.setText(
            "" if self._tray_available else
            "System tray is unavailable. Closing the window will exit SIM Manager.",
        )
        self.tray_notice_label.setVisible(not self._tray_available)

    def set_preferences_notice(self, message: str) -> None:
        text = "" if type(message) is str and message == "" else PREFERENCES_SAVE_FAILURE
        self.preferences_notice_label.setText(text)
        self.preferences_notice_label.setVisible(bool(text))

    def _preferences_edited(self, _value=None) -> None:
        self._preferences = AppPreferences(
            auto_refresh=self.auto_refresh_toggle.isChecked(),
            refresh_interval=self.refresh_interval_combo.currentData(),
            close_to_tray=self.close_to_tray_toggle.isChecked(),
        )
        self.refresh_interval_combo.setEnabled(self._preferences.auto_refresh)
        self.preferences_changed.emit(self._preferences)

    def _toggle_connection_details(self, expanded: bool) -> None:
        self.connection_details.setVisible(expanded)
        self.connection_details_toggle.setText(("▾" if expanded else "▸") + " Connection details")
        self.connection_details_toggle.setAccessibleDescription(
            "Collapse router and signal diagnostics" if expanded else "Expand router and signal diagnostics"
        )

    def render(self, view: DeviceView) -> None:
        self.connection_label.setText(view.router_status)
        self.connection_details.render(view)

    def _group(self, title: str, rows: tuple) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        content = QVBoxLayout(card)
        content.setContentsMargins(18, 16, 18, 18)
        content.setSpacing(14)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        content.addWidget(heading)
        form = QFormLayout()
        form.setHorizontalSpacing(28)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        for name, value in rows:
            label = QLabel(name)
            label.setObjectName("muted")
            form.addRow(label, value)
        content.addLayout(form)
        return card

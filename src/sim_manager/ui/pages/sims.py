"""Saved SIM profile presentation; selecting a row never activates a SIM."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from sim_manager.services.accounts import AccountService
from sim_manager.sim_models import SimCarrier, SimProfile
from sim_manager.ui.accounts import AccountControls


def _text_label(text: str = "", *, muted: bool = False) -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    policy = label.sizePolicy()
    policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
    label.setSizePolicy(policy)
    if muted:
        label.setObjectName("muted")
    return label


def _card(title: str):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 16, 18, 18)
    layout.setSpacing(10)
    heading = _text_label(title)
    heading.setObjectName("cardTitle")
    layout.addWidget(heading)
    return frame, layout


class SimsPage(QWidget):
    create_requested = Signal(str, str, object)
    rename_requested = Signal(str, str)

    def __init__(self, account_service: AccountService | None = None, *, demo: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._profiles: tuple[SimProfile, ...] = ()
        self._active_profile: SimProfile | None = None
        self._current_sim = False
        self._last_active_id: str | None = None
        self._form_context = None
        self._rename_profile_id: str | None = None
        self._rename_source_name: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.notice_label = _text_label(muted=True)
        self.notice_label.hide()
        layout.addWidget(self.notice_label)
        self.empty_label = _text_label("No saved SIM profiles.", muted=True)
        layout.addWidget(self.empty_label)
        self.profile_list = QListWidget()
        self.profile_list.setAccessibleName("Saved SIM profiles")
        self.profile_list.setMinimumHeight(110)
        self.profile_list.setMaximumHeight(220)
        self.profile_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.profile_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.profile_list.currentRowChanged.connect(self._select_profile)
        layout.addWidget(self.profile_list)
        self.profile_card, details = _card("SIM profile")
        self.profile_name_label = _text_label()
        self.profile_number_label = _text_label()
        self.profile_carrier_label = _text_label()
        self.profile_state_label = _text_label(muted=True)
        for value in (self.profile_name_label, self.profile_number_label,
                      self.profile_carrier_label, self.profile_state_label):
            policy = value.sizePolicy()
            policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
            value.setSizePolicy(policy)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for title, value in (("Name", self.profile_name_label), ("Phone number", self.profile_number_label),
                             ("Carrier label", self.profile_carrier_label), ("Status", self.profile_state_label)):
            form.addRow(_text_label(title, muted=True), value)
        details.addLayout(form)
        rename = QHBoxLayout()
        self.rename_name_input = QLineEdit()
        self.rename_name_input.setAccessibleName("New SIM profile name")
        self.rename_name_input.setMaxLength(80)
        self.rename_button = QPushButton("Rename")
        self.rename_button.clicked.connect(self._rename_selected)
        self.rename_name_input.returnPressed.connect(self._rename_selected)
        rename.addWidget(self.rename_name_input, 1)
        rename.addWidget(self.rename_button)
        details.addLayout(rename)
        layout.addWidget(self.profile_card)
        self.account_controls = AccountControls(account_service, demo=demo)
        self.account_controls.hide()
        layout.addWidget(self.account_controls)
        self.create_card, creation = _card("Name this SIM")
        creation.addWidget(_text_label("This SIM has no saved profile. Add one when you are ready.", muted=True))
        create_form = QFormLayout()
        create_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.create_name_input = QLineEdit()
        self.create_name_input.setAccessibleName("SIM profile name")
        self.create_name_input.setMaxLength(80)
        self.create_phone_input = QLineEdit()
        self.create_phone_input.setAccessibleName("SIM phone number")
        self.create_phone_input.setPlaceholderText("Optional")
        self.create_phone_input.setMaxLength(32)
        self.create_carrier_combo = QComboBox()
        self.create_carrier_combo.setAccessibleName("SIM carrier label")
        self.create_carrier_combo.addItem("Unknown", SimCarrier.UNKNOWN)
        self.create_carrier_combo.addItem("DITO", SimCarrier.DITO)
        create_form.addRow(_text_label("Name", muted=True), self.create_name_input)
        create_form.addRow(_text_label("Phone number", muted=True), self.create_phone_input)
        create_form.addRow(_text_label("Carrier label", muted=True), self.create_carrier_combo)
        creation.addLayout(create_form)
        self.create_button = QPushButton("Create profile")
        self.create_button.clicked.connect(self._create_profile)
        creation.addWidget(self.create_button)
        self.create_card.hide()
        layout.addWidget(self.create_card)
        layout.addStretch()
        self._select_profile(-1)

    @property
    def selected_profile(self) -> SimProfile | None:
        row = self.profile_list.currentRow()
        return self._profiles[row] if 0 <= row < len(self._profiles) else None

    def render_profiles(self, profiles: tuple[SimProfile, ...], active_profile: SimProfile | None,
                        *, can_create: bool, current_sim: bool, notice: str = "",
                        current_phone_number: str | None = None) -> None:
        selected = self.selected_profile
        selected_id = selected.profile_id if selected is not None else None
        self._profiles = tuple(profile for profile in profiles if isinstance(profile, SimProfile))
        self._active_profile = active_profile if isinstance(active_profile, SimProfile) else None
        self._current_sim = current_sim is True
        active_id = self._active_profile.profile_id if self._active_profile is not None else None
        self.profile_list.blockSignals(True)
        self.profile_list.clear()
        for profile in self._profiles:
            name = profile.name if type(profile.name) is str else "Unnamed SIM"
            phone = profile.phone_number if type(profile.phone_number) is str and profile.phone_number else "Number not provided"
            carrier = "DITO" if profile.carrier is SimCarrier.DITO else "Unknown"
            active = self._current_sim and profile.profile_id == active_id
            item = QListWidgetItem(f"{'Active · ' if active else ''}{name}\n{carrier} · {phone}")
            item.setData(Qt.ItemDataRole.UserRole, profile.profile_id)
            self.profile_list.addItem(item)
        preferred = active_id if active_id != self._last_active_id or selected_id is None else selected_id
        row = next((index for index, profile in enumerate(self._profiles) if profile.profile_id == preferred), 0 if self._profiles else -1)
        self.profile_list.setCurrentRow(row)
        self.profile_list.blockSignals(False)
        self._last_active_id = active_id
        # Keep the active profile and its actions close to a short saved list.
        self.profile_list.setFixedHeight(min(220, max(76, len(self._profiles) * 66 + 4)))
        self.empty_label.setVisible(not self._profiles)
        self.profile_list.setVisible(bool(self._profiles))
        self.create_card.setVisible(can_create is True)
        self.create_button.setEnabled(can_create is True)
        form_context = (active_id, self._current_sim, can_create is True)
        if can_create is True and form_context != self._form_context:
            self.create_name_input.clear()
            self.create_phone_input.setText(current_phone_number if type(current_phone_number) is str else "")
            self.create_carrier_combo.setCurrentIndex(0)
        self._form_context = form_context
        allowed_notices = {
            "", "Saved SIM profiles are unavailable.", "Current SIM is unavailable.",
            "Create a profile for the current SIM.",
            "SIM identity is unverified. This profile will not match automatically.",
            "SIM profile could not be saved. Check the name and number, then try again.",
            "SIM profile could not be renamed. Check the name and try again.",
        }
        safe_notice = notice if type(notice) is str and notice in allowed_notices else "Saved SIM profiles are unavailable."
        self.notice_label.setText(safe_notice)
        self.notice_label.setVisible(bool(safe_notice))
        if can_create is not True:
            self.create_name_input.clear()
            self.create_phone_input.clear()
            self.create_carrier_combo.setCurrentIndex(0)
        self._select_profile(row)

    def reset_create_form(self) -> None:
        """Let the service owner mark a genuine SIM change without phone matching."""
        self._form_context = None
        self.create_name_input.clear()
        self.create_phone_input.clear()
        self.create_carrier_combo.setCurrentIndex(0)

    def _select_profile(self, row: int) -> None:
        selected = self.selected_profile
        self.profile_card.setVisible(selected is not None)
        self.rename_button.setEnabled(selected is not None)
        self.rename_name_input.setEnabled(selected is not None)
        active = (selected is not None and self._active_profile is not None and self._current_sim
                  and selected.profile_id == self._active_profile.profile_id)
        self.account_controls.setVisible(active and self._active_profile.carrier is SimCarrier.DITO)
        if selected is None:
            for label in (self.profile_name_label, self.profile_number_label, self.profile_carrier_label, self.profile_state_label):
                label.clear()
            self.rename_name_input.clear()
            self._rename_profile_id = None
            self._rename_source_name = None
            return
        name = selected.name if type(selected.name) is str else "Unnamed SIM"
        self.profile_name_label.setText(name)
        self.profile_number_label.setText(selected.phone_number if type(selected.phone_number) is str and selected.phone_number else "Not provided")
        self.profile_carrier_label.setText("DITO" if selected.carrier is SimCarrier.DITO else "Unknown")
        self.profile_state_label.setText("Active · Inserted SIM" if active else "Saved profile · SIM not active")
        if selected.profile_id != self._rename_profile_id or name != self._rename_source_name:
            self.rename_name_input.setText(name)
        self._rename_profile_id = selected.profile_id
        self._rename_source_name = name

    def _create_profile(self) -> None:
        if not self.create_button.isEnabled():
            return
        name = self.create_name_input.text()
        if not name.strip():
            self.notice_label.setText("Enter a SIM name.")
            self.notice_label.show()
            self.create_name_input.setFocus()
            return
        carrier = self.create_carrier_combo.currentData()
        if type(carrier) is str and carrier in {SimCarrier.UNKNOWN.value, SimCarrier.DITO.value}:
            carrier = SimCarrier(carrier)
        if type(carrier) is not SimCarrier:
            carrier = SimCarrier.UNKNOWN
        self.create_requested.emit(name, self.create_phone_input.text(), carrier)

    def _rename_selected(self) -> None:
        selected = self.selected_profile
        if selected is None:
            return
        name = self.rename_name_input.text()
        if not name.strip():
            self.notice_label.setText("Enter a SIM name.")
            self.notice_label.show()
            self.rename_name_input.setFocus()
            return
        self.rename_requested.emit(selected.profile_id, name)

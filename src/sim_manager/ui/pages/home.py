"""Home-only visual dashboard over existing normalized SIM/account state."""

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

from sim_manager.account_models import AccountData, AccountDataIssue, AccountPhase, AccountState, SessionValidity
from sim_manager.services.accounts import AccountService
from sim_manager.services.presentation import DeviceView
from sim_manager.sim_models import SimCarrier, SimProfile
from sim_manager.ui.home_display import (
    connection_icon, format_last_updated, format_promo_expiry, format_reported_date,
)
from sim_manager.ui.accounts import AccountControls
from sim_manager.ui.theme import HOME_STYLESHEET


class HomePage(QWidget):
    messages_requested = Signal()
    account_refresh_requested = Signal()
    account_sign_in_requested = Signal()

    @staticmethod
    def _plain_label(text: str = "", *, role: str = "homeMuted") -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setObjectName(role)
        label.setWordWrap(True)
        policy = label.sizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        label.setSizePolicy(policy)
        return label

    def _value(self, key: str, title: str, *, role: str = "homeDetail") -> QLabel:
        value = self._plain_label("Not available", role=role)
        value.setAccessibleName(title)
        self.profile_values[key] = value
        return value

    def _profile_field(self, title: str, key: str) -> QWidget:
        widget = QWidget()
        field = QVBoxLayout(widget)
        field.setContentsMargins(0, 0, 0, 0)
        field.setSpacing(4)
        field.addWidget(self._plain_label(title))
        field.addWidget(self._value(key, title))
        self._field_widgets[key] = widget
        return widget

    def __init__(self, account_service: AccountService | None = None, *, demo: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("homeDashboard")
        self.setStyleSheet(HOME_STYLESHEET)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.profile_values: dict[str, QLabel] = {}
        self._field_widgets: dict[str, QWidget] = {}
        self.values: dict[str, QLabel] = {}
        self.connection_values = self.values
        self._account_service = account_service
        self._demo = demo
        self._account_available = account_service is not None
        self._account_state = AccountState(is_demo=demo)
        self._account_context = False
        self._current_sim = False
        self._number_context = None
        self.profile_card = self._sim_card()
        self.account_card = self._account_card()
        self.account_controls = AccountControls(account_service, demo=demo)
        self.account_sign_in_button = self.account_controls.connect_button
        self.account_disconnect_button.clicked.connect(self.account_controls.disconnect_button.click)
        self.account_section = QWidget()
        section = QVBoxLayout(self.account_section)
        section.setContentsMargins(0, 0, 0, 0)
        section.setSpacing(0)
        section.addWidget(self.account_controls)
        section.addWidget(self.account_card)
        self.connection_strip = self._connection_card()
        layout.addWidget(self.profile_card)
        layout.addWidget(self.account_section)
        layout.addWidget(self.connection_strip)
        layout.addStretch(1)
        self.render(None)
        self.render_profile(None)

    def _sim_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("homeSimCard")
        content = QHBoxLayout(card)
        content.setContentsMargins(20, 14, 20, 14)
        content.setSpacing(18)
        identity = QVBoxLayout()
        identity.setSpacing(4)
        self.profile_note = self._plain_label("Active SIM", role="homeCaption")
        identity.addWidget(self.profile_note)
        identity.addWidget(self._value("name", "Active SIM name", role="homeSimName"))
        self.profile_status = self._plain_label("● Unknown", role="homeStatus")
        self.profile_status.setAccessibleName("Active SIM network status")
        identity.addWidget(self.profile_status)
        number = self._value("phone_number", "Active SIM phone number")
        number.hide()
        identity.addWidget(number)
        # Retain the existing normalized carrier value; the visible caption
        # combines it with Active SIM instead of adding another identity row.
        carrier = self._value("carrier", "Active SIM carrier")
        carrier.setParent(card)
        carrier.hide()
        content.addLayout(identity, 1)
        actions = QVBoxLayout()
        actions.setSpacing(4)
        self.messages_button = QPushButton("Open Messages")
        self.messages_button.setObjectName("homeAction")
        self.messages_button.setAccessibleName("Open active SIM messages")
        self.messages_button.clicked.connect(self.messages_requested)
        self.phone_toggle = QPushButton("Show number")
        self.phone_toggle.setObjectName("homePhoneToggle")
        self.phone_toggle.setCheckable(True)
        self.phone_toggle.setAccessibleName("Show active SIM phone number")
        self.phone_toggle.toggled.connect(self._show_number)
        actions.addWidget(self.messages_button)
        actions.addWidget(self.phone_toggle)
        content.addLayout(actions)
        return card

    def _show_number(self, checked: bool) -> None:
        self.profile_values["phone_number"].setVisible(checked and not self.phone_toggle.isHidden())
        self.phone_toggle.setText("Hide number" if checked else "Show number")
        self.phone_toggle.setAccessibleName(
            "Hide active SIM phone number" if checked else "Show active SIM phone number"
        )

    def _account_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("homeDataCard")
        content = QVBoxLayout(card)
        content.setContentsMargins(22, 16, 22, 16)
        content.setSpacing(10)
        heading = QHBoxLayout()
        heading.addWidget(self._plain_label("Data remaining", role="homeCaption"), 1)
        self.account_refresh_button = QPushButton("Refresh account")
        self.account_refresh_button.setObjectName("homeRefresh")
        self.account_refresh_button.setAccessibleName("Refresh active SIM account data")
        self.account_refresh_button.clicked.connect(self.account_refresh_requested)
        heading.addWidget(self.account_refresh_button)
        self.account_disconnect_button = QPushButton("Disconnect")
        self.account_disconnect_button.setObjectName("homeTextAction")
        self.account_disconnect_button.setAccessibleName("Disconnect MyDITO account")
        heading.addWidget(self.account_disconnect_button)
        content.addLayout(heading)
        self.account_notice = self._plain_label()
        content.addWidget(self.account_notice)
        self.account_details = QWidget()
        details = QVBoxLayout(self.account_details)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(12)
        details.addWidget(self._value("data_remaining", "Data remaining", role="homeDataValue"))
        self.data_progress = QProgressBar()
        self.data_progress.setObjectName("homeProgress")
        self.data_progress.setAccessibleName("Reported data allowance remaining")
        self.data_progress.setRange(0, 100)
        self.data_progress.setTextVisible(False)
        self.data_progress.setFixedHeight(6)
        self.data_progress.reset()
        self.data_progress.hide()
        details.addWidget(self.data_progress)
        promo_row = QHBoxLayout()
        promo_row.setSpacing(24)
        promo = QWidget()
        promo_content = QVBoxLayout(promo)
        promo_content.setContentsMargins(0, 0, 0, 0)
        promo_content.setSpacing(5)
        self.promo_caption = self._plain_label("Active promo", role="homeCaption")
        promo_content.addWidget(self.promo_caption)
        promo_content.addWidget(self._value("promo", "Reported promo or bucket names", role="homePromoName"))
        self._field_widgets["promo"] = promo
        promo_row.addWidget(promo, 1, Qt.AlignmentFlag.AlignTop)
        expiry = QVBoxLayout()
        expiry.setSpacing(5)
        expiry_title = self._plain_label("Expires", role="homeCaption")
        expiry_title.setAlignment(Qt.AlignmentFlag.AlignRight)
        expiry.addWidget(expiry_title)
        expiry_value = self._value("promo_expiry", "Promo or data bucket expiry", role="homeExpiry")
        expiry_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        expiry.addWidget(expiry_value)
        promo_row.addLayout(expiry, 1)
        details.addLayout(promo_row)
        divider = QFrame()
        divider.setObjectName("homeDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        details.addWidget(divider)
        footer = QHBoxLayout()
        footer.setSpacing(20)
        load = QVBoxLayout()
        load.setSpacing(3)
        load.addWidget(self._plain_label("Load balance", role="homeCaption"))
        load_value_row = QHBoxLayout()
        load_value_row.setSpacing(7)
        load_value_row.addWidget(self._value("load_balance", "Load balance", role="homeLoadValue"), 1)
        load.addLayout(load_value_row)
        footer.addLayout(load, 1)
        self.account_updated = self._plain_label()
        self.account_updated.setAccessibleName("Last successful account update")
        self.account_updated.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        footer.addWidget(self.account_updated, 1)
        details.addLayout(footer)
        self.details_toggle = QPushButton("Account details")
        self.details_toggle.setObjectName("homeTextAction")
        self.details_toggle.setCheckable(True)
        self.details_toggle.setAccessibleName("Show additional reported account details")
        self.details_toggle.toggled.connect(self._show_details)
        load_value_row.addWidget(self.details_toggle)
        self.additional_details = QWidget()
        additional = QVBoxLayout(self.additional_details)
        additional.setContentsMargins(0, 0, 0, 0)
        additional.setSpacing(10)
        additional.addWidget(self._profile_field("Load expiry", "load_expiry"))
        self.allowance_row = QWidget()
        allowances = QHBoxLayout(self.allowance_row)
        allowances.setContentsMargins(0, 0, 0, 0)
        allowances.setSpacing(20)
        allowances.addWidget(self._profile_field("SMS allowance", "sms_allowance"), 1)
        allowances.addWidget(self._profile_field("Call allowance", "call_allowance"), 1)
        additional.addWidget(self.allowance_row)
        self.buckets_title = self._plain_label("Balance / promo details", role="homeCaption")
        additional.addWidget(self.buckets_title)
        self.buckets_value = self._plain_label(role="homeDetail")
        self.buckets_value.setAccessibleName("Carrier-reported balance and promo details")
        additional.addWidget(self.buckets_value)
        self.additional_details.hide()
        details.addWidget(self.additional_details)
        content.addWidget(self.account_details)
        return card

    def _show_details(self, checked: bool) -> None:
        self.additional_details.setVisible(checked)
        self.details_toggle.setText("Hide account details" if checked else "Account details")

    def _connection_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("homeConnectionCard")
        content = QHBoxLayout(card)
        content.setContentsMargins(20, 12, 20, 12)
        content.setSpacing(15)
        self.connection_image = self._plain_label(role="homeIcon")
        self.connection_image.setFixedSize(44, 44)
        self.connection_image.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.connection_image.setAccessibleName("Connection icon")
        self.connection_image.setAccessibleDescription("Decorative radio icon; no signal strength is measured.")
        content.addWidget(self.connection_image)
        summary = QVBoxLayout()
        summary.setSpacing(5)
        self.connection_title = self._plain_label(role="homeConnectionTitle")
        self.connection_subtitle = self._plain_label()
        summary.addWidget(self.connection_title)
        summary.addWidget(self.connection_subtitle)
        content.addLayout(summary, 1)
        self.network_badge = self._plain_label("—", role="homeNetworkBadge")
        self.network_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.network_badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self.network_badge.setMinimumWidth(48)
        content.addWidget(self.network_badge)
        # These three neutral labels preserve the existing public presentation
        # bindings. The condensed visible summary exposes them through its
        # accessible description instead of drawing a second status row.
        for title, key in (("Connection", "network_status"), ("Network", "network_mode"), ("SIM", "sim_state")):
            value = self._plain_label("Unknown")
            value.setAccessibleName(title)
            value.setParent(card)
            value.hide()
            self.values[key] = value
        return card

    @staticmethod
    def _polish_level(widget: QWidget, level: str) -> None:
        widget.setProperty("level", level)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def render(self, view: DeviceView | None) -> None:
        valid = isinstance(view, DeviceView)
        connection = view.network_status if valid and view.network_status in ("Connected", "Disconnected") else "Unknown"
        network = view.network_mode if valid and type(view.network_mode) is str and view.network_mode else "Unknown"
        sim = view.sim_state if valid and view.sim_state in ("Ready", "Not Ready") else "Unknown"
        for key, value in (("network_status", connection), ("network_mode", network), ("sim_state", sim)):
            self.values[key].setText(value)
        prefix = network + " " if network != "Unknown" else ""
        if connection == "Disconnected":
            title, level = prefix + "Disconnected", "error"
        elif sim == "Not Ready":
            title, level = "SIM not ready", "warning"
        elif connection == "Connected" and sim == "Ready":
            title, level = prefix + "Connected", "ok"
        elif connection == "Connected":
            title, level = prefix + "Connection reported", "warning"
        else:
            title, level = prefix + "Connection unknown", "error" if valid and view.level == "error" else "info"
        router = "Router online" if valid and view.router_status == "Status available" else (
            "Router data partial" if valid and view.router_status == "Partial data" else "Router status unknown"
        )
        sim_description = {"Ready": "SIM ready", "Not Ready": "SIM not ready"}.get(sim, "SIM unknown")
        self.connection_title.setText(title)
        self.connection_title.setAccessibleDescription(
            "Connection: " + connection + ". Network: " + network + ". SIM: " + sim + "."
        )
        self.connection_subtitle.setText(router + " · " + sim_description)
        self.network_badge.setText("4G" if network == "LTE" else "5G" if network in ("5G", "NR5G") else "—")
        self.network_badge.setAccessibleName("Reported network: " + network)
        colors = {"ok": "#55D7C4", "warning": "#E5B86B", "error": "#E58C99", "info": "#A2B6CA"}
        self.connection_image.setPixmap(connection_icon(colors[level]).pixmap(28, 28))
        self._polish_level(self.connection_strip, level)
        self._polish_level(self.network_badge, level)
        self._polish_level(self.connection_image, level)
        self._polish_level(self.profile_status, level)
        self.profile_status.setText("● " + title)

    def set_account_available(self, available: bool) -> None:
        self._account_available = available is True and self._account_service is not None
        self._render_account(self._account_state)

    def _render_account(self, state: AccountState) -> None:
        self._account_state = state if isinstance(state, AccountState) else AccountState()
        state = self._account_state
        eligible = self._account_context and self._account_available
        self.account_controls.set_context(eligible)
        connected = (eligible and state.phase is AccountPhase.CONNECTED
                     and state.validity is SessionValidity.VALIDATED)
        self.account_card.setVisible(connected)
        self.account_controls.setVisible(not connected)
        self.account_disconnect_button.setVisible(connected)
        self.account_disconnect_button.setEnabled(connected and self.account_controls.disconnect_button.isEnabled())
        data = state.data if connected and isinstance(state.data, AccountData) else None
        for key in ("load_balance", "data_remaining", "promo", "promo_expiry", "load_expiry", "sms_allowance", "call_allowance"):
            self.profile_values[key].setText("Not available")
        self.buckets_value.clear()
        self.account_updated.clear()
        self.account_updated.setToolTip("")
        # No verified original total is available in AccountData. Keep the
        # visual component reset and hidden rather than inventing a ratio.
        self.data_progress.reset()
        self.data_progress.hide()
        self.account_details.setVisible(data is not None)
        if data is None:
            self.details_toggle.setChecked(False)
        self.allowance_row.setVisible(data is not None and bool(data.sms_allowance or data.call_allowance))
        for key in ("sms_allowance", "call_allowance", "load_expiry", "promo"):
            value = getattr(data, key, None) if data is not None else None
            if key == "load_expiry":
                value = data.expiry if data is not None else None
            elif key == "promo":
                value = (data.active_promos or data.data_buckets) if data is not None else None
            self._field_widgets[key].setVisible(bool(value))
        self.buckets_title.setVisible(data is not None and bool(data.data_buckets))
        self.buckets_value.setVisible(data is not None and bool(data.data_buckets))
        if data is not None:
            for key, value in (
                ("load_balance", data.load_balance), ("data_remaining", data.data_remaining),
                ("load_expiry", format_reported_date(data.expiry)), ("sms_allowance", data.sms_allowance),
                ("call_allowance", data.call_allowance),
            ):
                self.profile_values[key].setText(value if type(value) is str and value else "Not available")
            self.profile_values["promo_expiry"].setText(format_promo_expiry(data))
            names = tuple(promo.name for promo in data.active_promos) or tuple(bucket.name for bucket in data.data_buckets)
            self.promo_caption.setText("Active promo" if data.active_promos else "Reported bucket" if len(names) == 1 else "Reported buckets")
            self.profile_values["promo"].setText("\n".join(names) or "Not available")
            buckets = []
            for bucket in data.data_buckets:
                label = (bucket.name or "Unnamed bucket") + ": " + (bucket.remaining or "Not available")
                if bucket.expiry:
                    label += " · Expires " + format_reported_date(bucket.expiry)
                buckets.append(label)
            self.buckets_value.setText("\n".join(buckets))
            self.details_toggle.setVisible(bool(data.expiry or data.sms_allowance or data.call_allowance or data.data_buckets))
            if isinstance(data.updated_at, datetime) and data.updated_at.tzinfo is not None:
                self.account_updated.setText(format_last_updated(data.updated_at))
                self.account_updated.setToolTip(data.updated_at.isoformat(timespec="seconds"))
        refreshing = connected and state.data_refreshing is True
        self.account_refresh_button.setVisible(connected)
        self.account_refresh_button.setEnabled(self._account_available and connected and not refreshing)
        self.account_refresh_button.setText("Refreshing..." if refreshing else "Refresh account")
        expired = self._account_context and state.phase is AccountPhase.EXPIRED
        mismatch = (self._account_context and state.phase is AccountPhase.ERROR
                    and state.data_issue is AccountDataIssue.ACCOUNT_MISMATCH)
        if expired or mismatch:
            self.account_controls.connect_button.setText("Reconnect DITO" if expired else "Sign in again")
        if not self._account_context:
            notice = "Account data belongs to the active SIM."
        elif expired:
            notice = "Session expired. Reconnect DITO to refresh account data."
        elif mismatch:
            notice = "The signed-in account does not match the active SIM. Sign in again with this SIM's account."
        elif refreshing:
            notice = "Refreshing account data…" + (" Previous values are stale." if state.data_stale is True and data is not None else "")
        elif connected and state.data_issue is AccountDataIssue.RATE_LIMITED:
            notice = ("Rate limited. Refresh paused. Showing last successful values (stale)."
                      if data is not None else "Rate limited. Refresh paused. Try again later.")
        elif connected and state.data_issue in (AccountDataIssue.UNAVAILABLE, AccountDataIssue.UNSUPPORTED):
            notice = ("Account refresh failed. Showing last successful values (stale). Try again."
                      if data is not None else "Account refresh failed. Try again.")
        elif connected and data is not None and state.data_stale is True:
            notice = "Account data is stale. Refresh to try again."
        elif connected and data is not None:
            notice = "Verified account data from " + data.source + "."
        elif connected:
            notice = "Account data is unavailable. Refresh to try again."
        elif state.phase is AccountPhase.CONNECTING:
            notice = "Complete sign-in in the official carrier window."
        else:
            notice = "Connect your MyDITO account to view your data balance, load and promos."
        self.account_notice.setText(notice)
        self.account_notice.setVisible(not (connected and data is not None and not refreshing
                                           and state.data_stale is not True and state.data_issue is None))
        self.account_card.setAccessibleDescription(notice)
        if not connected:
            if not self._current_sim:
                self.account_controls.detail_label.setText("Insert a SIM and refresh router status to connect its account.")
            elif not self._account_context:
                self.account_controls.detail_label.setText("Create a DITO profile for the inserted SIM in SIMs to connect its account.")
            elif not self._account_available:
                self.account_controls.detail_label.setText("Account connection is unavailable. Please try again later.")
            elif expired or mismatch:
                self.account_controls.detail_label.setText(notice)

    def render_profile(self, profile: SimProfile | None, current_sim: bool = False,
                       phone_number: str | None = None) -> None:
        if not isinstance(profile, SimProfile):
            profile = None
        self.profile_values["name"].setText(
            profile.name if profile is not None and type(profile.name) is str
            else "Unnamed SIM" if current_sim else "No active SIM"
        )
        self.profile_values["phone_number"].setText(
            profile.phone_number if profile is not None and type(profile.phone_number) is str and profile.phone_number
            else phone_number if profile is None and current_sim and type(phone_number) is str and phone_number
            else "Not provided"
        )
        self.profile_values["carrier"].setText("DITO" if profile is not None and profile.carrier is SimCarrier.DITO else "Unknown")
        self.profile_note.setText("Active SIM · " + self.profile_values["carrier"].text())
        number = self.profile_values["phone_number"].text()
        number_context = (profile.profile_id if profile is not None else None, current_sim is True, number)
        if number_context != self._number_context:
            self.phone_toggle.setChecked(False)
            self.profile_values["phone_number"].hide()
        self._number_context = number_context
        self.phone_toggle.setVisible(number != "Not provided")
        self._current_sim = current_sim is True
        self._account_context = profile is not None and current_sim is True and profile.carrier is SimCarrier.DITO
        self._render_account(profile.account_state if self._account_context else AccountState())

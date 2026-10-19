"""Compact account controls consuming only normalized service state."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout

from sim_manager.account_models import AccountIssue, AccountPhase, AccountState
from sim_manager.services.accounts import AccountService
from sim_manager.message_models import Message, MessageInbox


class AccountControls(QFrame):
    state_changed = Signal(object)

    def __init__(self, service: AccountService | None, *, demo: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._service = service
        self._demo = demo
        self._closed = False
        self._context_enabled = True
        self._copied_otp: str | None = None
        self.setObjectName("homeAccountPrompt")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        title = QLabel("MyDITO Account")
        title.setObjectName("homeAccountTitle")
        heading.addWidget(title, 1)
        self.status_label = QLabel("Not connected")
        self.status_label.setObjectName("homeAccountStatus")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        heading.addWidget(self.status_label)
        layout.addLayout(heading)
        self.detail_label = QLabel()
        self.detail_label.setTextFormat(Qt.TextFormat.PlainText)
        self.detail_label.setWordWrap(True)
        self.detail_label.setObjectName("homeAccountDescription")
        self.detail_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.detail_label)
        self.connect_button = QPushButton("Connect DITO")
        self.connect_button.setObjectName("homeConnectAction")
        layout.addWidget(self.connect_button)
        actions = QHBoxLayout()
        self.disconnect_button = QPushButton("Disconnect")
        self.disconnect_button.setObjectName("homeAction")
        self.otp_copy_button = QPushButton("Copy OTP")
        self.otp_copy_button.setObjectName("homeAction")
        actions.addWidget(self.disconnect_button)
        actions.addWidget(self.otp_copy_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.otp_label = QLabel()
        self.otp_label.setWordWrap(True)
        self.otp_label.setTextFormat(Qt.TextFormat.PlainText)
        self.otp_label.setObjectName("homeAccountDescription")
        layout.addWidget(self.otp_label)
        self.state_changed.connect(self._render_service_state)
        self.connect_button.clicked.connect(self._connect)
        self.disconnect_button.clicked.connect(self._disconnect)
        self.otp_copy_button.clicked.connect(self._copy_otp)
        self.render_state(AccountState(is_demo=demo))
        if service is not None:
            service.set_listener(self.state_changed.emit)
        else:
            self.connect_button.setEnabled(False)
            self.detail_label.setText("Account connection is unavailable in this view.")

    def _render_service_state(self, state: AccountState) -> None:
        # A queued signal from a disposed SIM session cannot overwrite the
        # current profile's state after switching SIMs.
        if self._context_enabled and (self._service is None or state is self._service.state):
            self.render_state(state)

    def render_state(self, state: AccountState) -> None:
        if self._closed:
            return
        if (not isinstance(state, AccountState)
                or type(state.phase) is not AccountPhase
                or (state.issue is not None and type(state.issue) is not AccountIssue)):
            state = AccountState(phase=AccountPhase.ERROR, issue=AccountIssue.UNAVAILABLE)
        phase = state.phase
        self.status_label.setText({
            AccountPhase.DISCONNECTED: "Not connected",
            AccountPhase.CONNECTING: "Sign in with DITO",
            AccountPhase.CONNECTED: "Connected",
            AccountPhase.EXPIRED: "Session expired",
            AccountPhase.ERROR: "Connection unavailable",
        }.get(phase, "Not connected"))
        details = {
            AccountIssue.CANCELLED: "Sign-in cancelled. Connect when you are ready.",
            AccountIssue.REJECTED: "Sign-in was not accepted. Check the official login page and try again there.",
            AccountIssue.UNAVAILABLE: "The DITO sign-in page could not be opened. Try Connect again.",
            AccountIssue.UNSUPPORTED_RESPONSE: "This DITO login response is not supported yet.",
            AccountIssue.EXPIRED: "Connect again to sign in with DITO.",
        }
        detail = details.get(state.issue, "Connect your MyDITO account to view your data balance, load and promos.")
        if self._demo:
            detail = "DEMO account state. No DITO connection or credentials."
        elif phase == AccountPhase.CONNECTING and state.issue is None:
            detail = "Complete sign-in in the official DITO window. Refresh Messages to check for a likely OTP."
        elif phase == AccountPhase.CONNECTED:
            detail = "Sign-in verified. Disconnect clears this app's isolated session."
        self.detail_label.setText(detail)
        level = {
            AccountPhase.CONNECTED: "ok", AccountPhase.CONNECTING: "warning",
            AccountPhase.EXPIRED: "warning", AccountPhase.ERROR: "error",
        }.get(phase, "info")
        self.status_label.setProperty("level", level)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.connect_button.setText("Show sign-in" if phase == AccountPhase.CONNECTING else "Connect DITO")
        self.connect_button.setEnabled(self._context_enabled and self._service is not None and phase != AccountPhase.CONNECTED)
        self.disconnect_button.setText("Cancel" if phase == AccountPhase.CONNECTING else "Disconnect")
        self.disconnect_button.setEnabled(self._context_enabled and phase in (AccountPhase.CONNECTING, AccountPhase.CONNECTED))
        self.disconnect_button.setVisible(self._context_enabled and phase in (AccountPhase.CONNECTING, AccountPhase.CONNECTED))
        available = self._context_enabled and phase == AccountPhase.CONNECTING and state.otp_available is True
        self.otp_copy_button.setVisible(available)
        self.otp_copy_button.setEnabled(available)
        self.otp_label.setVisible(available)
        self.otp_label.setText("Likely OTP found in Messages. Confirm it belongs to this sign-in." if available else "")
        if not available:
            self._clear_copied_otp()

    def _connect(self) -> None:
        if not self._closed and self._context_enabled and self._service is not None:
            self._service.connect()

    def _disconnect(self) -> None:
        if not self._closed and self._context_enabled and self._service is not None:
            if self._service.state.phase == AccountPhase.CONNECTING:
                self._service.cancel()
            else:
                self._service.disconnect()

    def _copy_otp(self) -> None:
        if self._closed or not self._context_enabled or self._service is None:
            return
        code = self._service.otp_for_copy()
        if type(code) is str and code:
            QApplication.clipboard().setText(code)
            self._copied_otp = code
            self.otp_label.setText("OTP copied. Paste it into the official DITO login page and submit there.")

    def _clear_copied_otp(self) -> None:
        if self._copied_otp is not None:
            clipboard = QApplication.clipboard()
            if clipboard.text() == self._copied_otp:
                clipboard.clear()
            self._copied_otp = None

    def set_context(self, enabled: bool) -> None:
        """Only the currently inserted DITO profile may use these controls."""
        self._context_enabled = enabled is True
        if self._context_enabled and self._service is not None:
            self.render_state(self._service.state)
        else:
            self.render_state(AccountState(is_demo=self._demo))

    def offer_otp(self, inbox) -> None:
        if not self._closed and self._context_enabled and self._service is not None:
            self._service.offer_otp(inbox)

    def offer_selected_message(self, message) -> None:
        if isinstance(message, Message):
            self.offer_otp(MessageInbox((message,)))

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._clear_copied_otp()
        if self._service is not None:
            self._service.set_listener(None)
            self._service.shutdown()
        self.otp_label.clear()
        self.otp_copy_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(False)

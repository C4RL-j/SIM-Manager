"""Native shell for normalized device state, with no device protocol knowledge."""

from time import monotonic

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from sim_manager.models import DeviceState
from sim_manager.account_models import AccountIssue, AccountPhase, AccountState
from sim_manager.sim_models import SimCarrier
from sim_manager.services.sim_profiles import SimProfileService
from sim_manager.services.device import SnapshotProvider
from sim_manager.services.presentation import present_device
from sim_manager.services.messages import MessageProvider
from sim_manager.services.accounts import AccountService
from sim_manager.services.router_login import D2LoginService, LoginStorageIssue

from .authentication import RouterSignInDialog
from .icons import navigation_icon
from .messages_refresh import MESSAGE_FAILURES, MessagesRefreshController
from .pages.messages import MessagesPage
from .pages.home import HomePage
from .pages.sims import SimsPage
from .pages.history import HistoryPage
from .pages.settings import SettingsPage
from .refresh import AUTHENTICATION_MESSAGES, RefreshController


class MainWindow(QMainWindow):
    def __init__(
        self, provider: SnapshotProvider, *, demo: bool = False,
        message_provider: MessageProvider | None = None,
        account_service: AccountService | None = None,
        router_login_service: D2LoginService | None = None,
        sim_profiles: SimProfileService | None = None,
    ) -> None:
        super().__init__()
        if getattr(provider, "is_demo", False) is True and not demo:
            raise ValueError("Demo providers require explicit demo mode.")
        if message_provider is not None and getattr(message_provider, "is_demo", False) is True and not demo:
            raise ValueError("Demo message providers require explicit demo mode.")
        if message_provider is not None and demo and getattr(message_provider, "is_demo", False) is not True:
            raise ValueError("Demo mode requires a demo message provider.")
        if account_service is not None and bool(getattr(account_service, "is_demo", False)) != demo:
            raise ValueError("Account provider must match the explicit demo mode.")
        if sim_profiles is not None and bool(getattr(sim_profiles, "is_demo", False)) != demo:
            raise ValueError("SIM profiles must match the explicit demo mode.")
        self._demo = demo
        self._closed = False
        self._authentication_required = False
        self._can_authenticate = not demo and callable(getattr(provider, "authenticate", None))
        self._sign_in_dialog: RouterSignInDialog | None = None
        self._router_login = router_login_service if not demo else None
        self._startup_started = False
        self._automatic_sign_in = False
        self.sim_profiles = sim_profiles if sim_profiles is not None else SimProfileService(demo=demo)
        self._account_service = account_service
        self._account_context_failed = False
        self._switching_sim = False
        self._profile_notice = ""
        self._sim_generation = 0
        self._messages_generation = 0
        # This is the service's safe configured address, never a response field.
        router_address = getattr(provider, "router_address", None)
        self._router_address = router_address if type(router_address) is str and len(router_address) <= 256 else None
        self.setWindowTitle("SIM Manager" + (" · DEMO" if demo else ""))
        self.setMinimumSize(840, 600)
        self.resize(self.minimumSize())
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 28, 18, 24)
        side.setSpacing(10)
        mark = QLabel("SM")
        mark.setObjectName("brandMark")
        mark.setFixedSize(42, 42)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand = QLabel("SIM Manager")
        brand.setObjectName("brand")
        subtitle = QLabel("Your SIM workspace")
        subtitle.setObjectName("muted")
        side.addWidget(mark)
        side.addWidget(brand)
        side.addWidget(subtitle)
        side.addSpacing(25)
        self.navigation = QListWidget()
        self.navigation.setIconSize(QSize(18, 18))
        for page in ("Home", "SIMs", "Messages", "History", "Settings"):
            self.navigation.addItem(QListWidgetItem(navigation_icon(page), page))
        self.navigation.setAccessibleName("Pages")
        side.addWidget(self.navigation, 1)
        self.demo_note = QLabel("Offline fixture data\nRouter not connected")
        self.demo_note.setObjectName("demoNotice")
        self.demo_note.setWordWrap(True)
        self.demo_note.setVisible(demo)
        side.addWidget(self.demo_note)
        footer = QLabel("LOCAL DESKTOP")
        footer.setObjectName("eyebrow")
        side.addWidget(footer)
        shell.addWidget(sidebar)

        workspace = QWidget()
        content = QVBoxLayout(workspace)
        content.setContentsMargins(24, 22, 24, 20)
        content.setSpacing(12)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(5)
        self.title_label = QLabel("Home")
        self.title_label.setObjectName("pageTitle")
        self.subtitle_label = QLabel("SIM and connection status")
        self.subtitle_label.setObjectName("muted")
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        header.addLayout(titles, 1)
        self.demo_label = QLabel("DEMO")
        self.demo_label.setObjectName("demoBadge")
        self.demo_label.setFixedHeight(28)
        self.demo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.demo_label.setVisible(demo)
        self.demo_label.setToolTip("Offline sample data; not live router information.")
        header.addWidget(self.demo_label)
        self.live_label = QLabel("LIVE")
        self.live_label.setObjectName("liveBadge")
        self.live_label.setFixedHeight(28)
        self.live_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.live_label.setToolTip("Data retrieved from the router.")
        self.live_label.setVisible(False)
        header.addWidget(self.live_label)
        self.sign_in_button = QPushButton("Sign in")
        self.sign_in_button.setVisible(False)
        header.addWidget(self.sign_in_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setVisible(False)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("refresh")
        header.addWidget(self.cancel_button)
        header.addWidget(self.refresh_button)
        content.addLayout(header)
        self.status_surface = QFrame()
        self.status_surface.setObjectName("statusSurface")
        self.status_surface.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._status_layout = QVBoxLayout(self.status_surface)
        self._status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_label = QLabel("Unknown")
        self.status_label.setObjectName("status")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._status_layout.addWidget(self.status_label)
        content.addWidget(self.status_surface)

        self.pages = QStackedWidget()
        self.home_page = HomePage()
        self.overview_page = self.home_page
        self.sims_page = SimsPage(account_service=account_service, demo=demo)
        self.history_page = HistoryPage()
        message_limit = getattr(message_provider, "read_limit", 3)
        if type(message_limit) is not int or not 1 <= message_limit <= 100:
            message_limit = 3
        self.messages_page = MessagesPage(demo=demo, read_limit=message_limit)
        self.settings_page = SettingsPage(router_address=self._router_address)
        self.messages_page.message_selected.connect(self.sims_page.account_controls.offer_selected_message)
        self.sims_page.account_controls.state_changed.connect(self._record_account_state)
        self.sims_page.create_requested.connect(self._create_profile)
        self.sims_page.rename_requested.connect(self._rename_profile)
        self.home_page.messages_requested.connect(lambda: self.navigation.setCurrentRow(2))
        for page in (self.home_page, self.sims_page, self.messages_page, self.history_page, self.settings_page):
            scroller = QScrollArea()
            scroller.setWidgetResizable(True)
            scroller.setWidget(page)
            self.pages.addWidget(scroller)
        content.addWidget(self.pages, 1)
        shell.addWidget(workspace, 1)
        self.refresh_controller = RefreshController(provider, self, allow_authentication=not demo)
        self.refresh_controller.snapshot_ready.connect(self.render_snapshot)
        self.refresh_controller.failed.connect(self._show_refresh_error)
        self.refresh_controller.authentication_failed.connect(self._show_authentication_error)
        self.refresh_controller.busy_changed.connect(self._set_busy)
        self.messages_controller = (
            MessagesRefreshController(message_provider, self) if message_provider is not None else None
        )
        self._messages_requested = False
        self.messages_page.set_available(self.messages_controller is not None)
        if self.messages_controller is not None:
            self.messages_controller.inbox_ready.connect(self._render_inbox)
            self.messages_controller.failed.connect(self._show_messages_error)
            self.messages_controller.busy_changed.connect(self._set_messages_busy)
        self.messages_page.refresh_requested.connect(self.start_messages_refresh)
        self.messages_page.cancel_requested.connect(self._cancel_messages_refresh)
        self.refresh_button.clicked.connect(self.start_refresh)
        self.cancel_button.clicked.connect(self._cancel_refresh)
        self.sign_in_button.clicked.connect(self.open_sign_in)
        self.settings_page.forget_login_button.clicked.connect(self.forget_saved_login)
        self.navigation.currentRowChanged.connect(self._change_page)
        self.navigation.setCurrentRow(0)
        self.render_snapshot(DeviceState())

    def _change_page(self, index: int) -> None:
        if not 0 <= index < 5:
            return
        self.pages.setCurrentIndex(index)
        # This action reads device state, never messages or application settings.
        self.refresh_button.setVisible(index == 0)
        self.title_label.setText(("Home", "SIMs", "Messages", "History", "Settings")[index])
        self.subtitle_label.setText((
            "Your active SIM and connection", "Saved SIM profiles", "Read-only SIM inbox",
            "History is coming later", "Router and application settings",
        )[index])
        if index == 2 and not self._messages_requested:
            self.start_messages_refresh()

    def start_messages_refresh(self) -> bool:
        if self._closed or self.messages_controller is None:
            return False
        started = self.messages_controller.start()
        if started:
            self._messages_requested = True
            self._messages_generation = self._sim_generation
        return started

    def _render_inbox(self, inbox) -> None:
        if self._closed or self._messages_generation != self._sim_generation:
            return
        self.messages_page.render(inbox)
        self.sims_page.account_controls.offer_otp(inbox)

    def _set_messages_busy(self, busy: bool) -> None:
        self.messages_page.set_busy(busy)
        if not busy and not self._closed and not self._messages_requested and self.navigation.currentRow() == 2:
            QTimer.singleShot(0, self.start_messages_refresh)

    def _cancel_messages_refresh(self) -> None:
        if self.messages_controller is not None and self.messages_controller.busy:
            self.messages_controller.cancel()
            self.messages_page.set_cancelling()

    def _show_messages_error(self, message: str) -> None:
        if self._messages_generation != self._sim_generation:
            return
        allowed = set(MESSAGE_FAILURES.values())
        message = message if type(message) is str and message in allowed else "SMS service unavailable"
        self.messages_page.set_notice(
            message, "warning" if message == "Messages refresh cancelled" else "error",
        )

    def _set_status(self, text: str, level: str = "info") -> None:
        if level == "ok":
            text = "● Demo data • Router not connected" if self._demo else "● Router data available"
        self.status_label.setText(text)
        self.status_label.setProperty("level", level)
        banner = level in ("warning", "error")
        self.status_label.setProperty("banner", banner)
        self.status_surface.setProperty("level", level)
        margins = (13, 10, 13, 10) if banner else (0, 0, 0, 0)
        self._status_layout.setContentsMargins(*margins)
        for widget in (self.status_label, self.status_surface):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.status_label.updateGeometry()

    def render_snapshot(self, state: DeviceState) -> None:
        if isinstance(state, DeviceState) and isinstance(state.source, str) and state.source.startswith("demo:") and not self._demo:
            self._show_refresh_error("Router status unavailable")
            return
        view = present_device(state)
        if self.sim_profiles.observe(state):
            self._switching_sim = True
            try:
                if self._account_service is not None:
                    try:
                        self._account_service.disconnect()
                    except Exception:
                        # An injected service must not leak raw exceptions
                        # through a Qt slot or remain usable for a new SIM.
                        self._account_context_failed = True
            finally:
                self._switching_sim = False
            self._sim_generation += 1
            self._messages_requested = False
            if self.messages_controller is not None:
                self.messages_controller.cancel()
            self.messages_page.reset_inbox()
            self.sims_page.reset_create_form()
            if self.navigation.currentRow() == 2 and (self.messages_controller is None or not self.messages_controller.busy):
                QTimer.singleShot(0, self.start_messages_refresh)
        self.home_page.render(view)
        self._refresh_profile_views()
        self.settings_page.connection_label.setText(view.router_status)
        self._authentication_required = view.notice == "Authentication required"
        self._automatic_sign_in = False
        self.live_label.setVisible(
            not self._demo and not self._authentication_required
            and view.router_status in ("Status available", "Partial data")
        )
        self._update_sign_in()
        self._set_status(view.notice or view.router_status, view.level)

    def _refresh_profile_views(self) -> None:
        active = self.sim_profiles.active_profile
        current = self.sim_profiles.current_sim
        self.home_page.render_profile(active, current_sim=current,
                                      phone_number=self.sim_profiles.current_phone_number)
        self.sims_page.render_profiles(
            self.sim_profiles.profiles, active, can_create=self.sim_profiles.can_create,
            current_sim=current, notice=self._profile_notice or self.sim_profiles.notice,
            current_phone_number=self.sim_profiles.current_phone_number,
        )
        self.messages_page.set_sim_context(active, current_sim=current)
        self.sims_page.account_controls.set_context(
            not self._account_context_failed and active is not None and current and active.carrier is SimCarrier.DITO,
        )
        if self._account_context_failed:
            self.sims_page.account_controls.render_state(
                AccountState(phase=AccountPhase.ERROR, issue=AccountIssue.UNAVAILABLE, is_demo=self._demo),
            )

    def _create_profile(self, name: str, phone_number: str, carrier: SimCarrier) -> None:
        if self._closed:
            return
        try:
            self.sim_profiles.create_profile(name, phone_number, carrier)
            self._profile_notice = ""
        except Exception:
            self._profile_notice = "SIM profile could not be saved. Check the name and number, then try again."
        self._refresh_profile_views()

    def _rename_profile(self, profile_id: str, name: str) -> None:
        if self._closed:
            return
        try:
            self.sim_profiles.rename_profile(profile_id, name)
            self._profile_notice = ""
        except Exception:
            self._profile_notice = "SIM profile could not be renamed. Check the name and try again."
        self._refresh_profile_views()

    def _record_account_state(self, state) -> None:
        if (self._closed or self._switching_sim or self._account_context_failed or self._account_service is None
                or state is not self._account_service.state):
            return
        self.sim_profiles.set_account_state(state)
        # No state_changed signal is emitted by this profile render.
        active = self.sim_profiles.active_profile
        self.home_page.render_profile(active, current_sim=self.sim_profiles.current_sim,
                                      phone_number=self.sim_profiles.current_phone_number)
        self.sims_page.render_profiles(
            self.sim_profiles.profiles, active, can_create=self.sim_profiles.can_create,
            current_sim=self.sim_profiles.current_sim,
            notice=self._profile_notice or self.sim_profiles.notice,
            current_phone_number=self.sim_profiles.current_phone_number,
        )

    def start_refresh(self) -> bool:
        if self._sign_in_dialog is not None:
            return False
        return self.refresh_controller.start()

    def start_initial_load(self) -> bool:
        """One startup attempt; automatic failure never schedules another."""
        if self._closed or self._startup_started:
            return False
        self._startup_started = True
        record = None
        if self._router_login is not None:
            record = self._router_login.load_remembered_login()
        self._update_saved_login_controls()
        if record is None:
            return self.start_refresh()
        try:
            self._automatic_sign_in = True
            return self.refresh_controller.authenticate(record.password, username=record.username)
        finally:
            record = None

    def _update_saved_login_controls(self) -> None:
        service = self._router_login
        saved = service is not None and service.saved_login_available
        issue = service.storage_issue if service is not None else None
        self.settings_page.forget_login_button.setVisible(saved or issue in (LoginStorageIssue.LOAD, LoginStorageIssue.DELETE))
        self.settings_page.forget_login_button.setEnabled(not self._closed and not self.refresh_controller.busy)
        notices = {
            LoginStorageIssue.LOAD: "Saved D2 login is unavailable. Sign in manually.",
            LoginStorageIssue.SAVE: "D2 sign-in succeeded, but the login could not be saved securely.",
            LoginStorageIssue.DELETE: "Saved D2 login could not be removed. Try Forget again.",
        }
        text = notices.get(issue, "D2 login is saved for this Windows account." if saved else "")
        self.settings_page.saved_login_note.setText(text)
        self.settings_page.saved_login_note.setVisible(bool(text))

    def forget_saved_login(self) -> bool:
        if self._closed or self._router_login is None:
            return False
        self._automatic_sign_in = False
        self.refresh_controller.cancel()
        if self._sign_in_dialog is not None:
            self._sign_in_dialog.clear_autofill()
        removed = self._router_login.forget_saved_login()
        self._show_authentication_error("Authentication required")
        self._update_saved_login_controls()
        if self._sign_in_dialog is not None:
            self._sign_in_dialog.set_storage_notice(
                "Saved router login was forgotten." if removed else "Saved router login could not be forgotten. Try again later.")
        return removed

    def _update_sign_in(self) -> None:
        self.sign_in_button.setVisible(self._can_authenticate and self._authentication_required)
        self.sign_in_button.setEnabled(
            not self._closed and not self.refresh_controller.busy and self._sign_in_dialog is None
        )
        self._update_saved_login_controls()

    def open_sign_in(self) -> bool:
        if (
            self._closed or not self._can_authenticate or not self._authentication_required
            or self.refresh_controller.busy or self._sign_in_dialog is not None
        ):
            return False
        record = self._router_login.load_remembered_login() if self._router_login is not None else None
        try:
            dialog = RouterSignInDialog(self._router_address or "Local router", self,
                                        remembered_login=record, remember_available=self._router_login is not None)
        finally:
            record = None
        if self._router_login is not None and self._router_login.storage_issue is LoginStorageIssue.LOAD:
            dialog.set_storage_notice("Saved router login is unavailable. Enter credentials for this session.")
        self._sign_in_dialog = dialog
        dialog.credentials_submitted.connect(self._submit_credentials)
        dialog.forget_requested.connect(self.forget_saved_login)
        dialog.finished.connect(self._sign_in_finished)
        self._update_sign_in()
        dialog.open()
        return True

    def _submit_credentials(self, username: str, password: str) -> None:
        try:
            remember = (self._sign_in_dialog.remember_requested
                        if self._router_login is not None and self._sign_in_dialog is not None else None)
            self.refresh_controller.authenticate(password, username=username, remember=remember)
        finally:
            username = None
            password = None

    def _sign_in_finished(self, result: int) -> None:
        dialog = self._sign_in_dialog
        self._sign_in_dialog = None
        if dialog is not None:
            dialog.deleteLater()
        self._update_sign_in()

    def _set_busy(self, busy: bool) -> None:
        self.refresh_button.setEnabled(not busy)
        signing_in = busy and self.refresh_controller.authenticating
        self.refresh_button.setText(("Signing in…" if signing_in else "Refreshing…") if busy else "Refresh")
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self._update_sign_in()
        if busy:
            self._set_status("Signing in…" if signing_in else "Refreshing…")

    def _cancel_refresh(self) -> None:
        self.refresh_controller.cancel()
        self.cancel_button.setEnabled(False)
        self._set_status("Cancelling…")

    def _show_refresh_error(self, message: str) -> None:
        # Closed messages only. Never render raw provider exception text.
        allowed = {"Authentication required", "Router status unavailable", "Malformed response", "Refresh cancelled", "Unknown error"}
        message = message if type(message) is str and message in allowed else "Unknown error"
        self.render_snapshot(DeviceState())
        self.settings_page.connection_label.setText(message)
        self._authentication_required = message == "Authentication required"
        self._update_sign_in()
        self._set_status(message, "warning" if message in ("Authentication required", "Refresh cancelled") else "error")

    def _show_authentication_error(self, message: str) -> None:
        automatic = self._automatic_sign_in
        self._automatic_sign_in = False
        allowed = set(AUTHENTICATION_MESSAGES.values()) | {
            "Authentication required", "Router status unavailable", "Malformed response", "Unknown error",
        }
        message = message if type(message) is str and message in allowed else "Unknown error"
        self.render_snapshot(DeviceState())
        self.settings_page.connection_label.setText(message)
        self._authentication_required = True
        self._update_sign_in()
        self._set_status(message, "warning" if message in ("Authentication rejected", "Sign-in cancelled", "Authentication required") else "error")
        if automatic and not self._closed:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.open_sign_in)

    def shutdown(self) -> bool:
        """Cancel both independent reads before one shared bounded join budget."""
        self._closed = True
        self.sims_page.account_controls.shutdown()
        self.sim_profiles.close()
        if self._sign_in_dialog is not None:
            self._sign_in_dialog.reject()
        self.refresh_controller.cancel()
        if self.messages_controller is not None:
            self.messages_controller.cancel()
        deadline = monotonic() + 1.0
        status_stopped = self.refresh_controller.shutdown(timeout=max(0.0, deadline - monotonic()))
        messages_stopped = (
            self.messages_controller.shutdown(timeout=max(0.0, deadline - monotonic()))
            if self.messages_controller is not None else True
        )
        self.messages_page.clear_private_content()
        return status_stopped and messages_stopped

    def closeEvent(self, event: QCloseEvent) -> None:
        self.shutdown()
        event.accept()

"""Native shell for normalized device state, with no device protocol knowledge."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from sim_manager.models import DeviceState
from sim_manager.services.device import SnapshotProvider
from sim_manager.services.presentation import present_device

from .authentication import RouterSignInDialog
from .icons import navigation_icon
from .pages.messages import MessagesPage
from .pages.overview import OverviewPage
from .pages.settings import SettingsPage
from .refresh import AUTHENTICATION_MESSAGES, RefreshController


class MainWindow(QMainWindow):
    def __init__(self, provider: SnapshotProvider, *, demo: bool = False) -> None:
        super().__init__()
        if getattr(provider, "is_demo", False) is True and not demo:
            raise ValueError("Demo providers require explicit demo mode.")
        self._demo = demo
        self._closed = False
        self._authentication_required = False
        self._can_authenticate = not demo and callable(getattr(provider, "authenticate", None))
        self._sign_in_dialog: RouterSignInDialog | None = None
        # This is the service's safe configured address, never a response field.
        router_address = getattr(provider, "router_address", None)
        self._router_address = router_address if type(router_address) is str and len(router_address) <= 256 else None
        self.setWindowTitle("SIM Manager" + (" · DEMO" if demo else ""))
        self.setMinimumSize(840, 600)
        self.resize(1120, 760)
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
        subtitle = QLabel("Device workspace")
        subtitle.setObjectName("muted")
        side.addWidget(mark)
        side.addWidget(brand)
        side.addWidget(subtitle)
        side.addSpacing(25)
        self.navigation = QListWidget()
        self.navigation.setIconSize(QSize(18, 18))
        for page in ("Overview", "Messages", "Settings"):
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
        self.title_label = QLabel("Overview")
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
        self.overview_page = OverviewPage()
        self.messages_page = MessagesPage()
        self.settings_page = SettingsPage(router_address=self._router_address)
        for page in (self.overview_page, self.messages_page, self.settings_page):
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
        self.refresh_button.clicked.connect(self.start_refresh)
        self.cancel_button.clicked.connect(self._cancel_refresh)
        self.sign_in_button.clicked.connect(self.open_sign_in)
        self.navigation.currentRowChanged.connect(self._change_page)
        self.navigation.setCurrentRow(0)
        self.render_snapshot(DeviceState())

    def _change_page(self, index: int) -> None:
        if not 0 <= index < 3:
            return
        self.pages.setCurrentIndex(index)
        # This action reads device state, never messages or application settings.
        self.refresh_button.setVisible(index == 0)
        self.title_label.setText(("Overview", "Messages", "Settings")[index])
        self.subtitle_label.setText((
            "SIM and connection status", "Read-only message workspace", "Application and connection information",
        )[index])

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
        self.overview_page.render(view)
        self.settings_page.connection_label.setText(view.router_status)
        self._authentication_required = view.notice == "Authentication required"
        self.live_label.setVisible(
            not self._demo and not self._authentication_required
            and view.router_status in ("Status available", "Partial data")
        )
        self._update_sign_in()
        self._set_status(view.notice or view.router_status, view.level)

    def start_refresh(self) -> bool:
        if self._sign_in_dialog is not None:
            return False
        return self.refresh_controller.start()

    def _update_sign_in(self) -> None:
        self.sign_in_button.setVisible(self._can_authenticate and self._authentication_required)
        self.sign_in_button.setEnabled(
            not self._closed and not self.refresh_controller.busy and self._sign_in_dialog is None
        )

    def open_sign_in(self) -> bool:
        if (
            self._closed or not self._can_authenticate or not self._authentication_required
            or self.refresh_controller.busy or self._sign_in_dialog is not None
        ):
            return False
        dialog = RouterSignInDialog(self._router_address or "Local router", self)
        self._sign_in_dialog = dialog
        dialog.credentials_submitted.connect(self._submit_credentials)
        dialog.finished.connect(self._sign_in_finished)
        self._update_sign_in()
        dialog.open()
        return True

    def _submit_credentials(self, username: str, password: str) -> None:
        try:
            self.refresh_controller.authenticate(password, username=username)
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
        allowed = set(AUTHENTICATION_MESSAGES.values()) | {
            "Authentication required", "Router status unavailable", "Malformed response", "Unknown error",
        }
        message = message if type(message) is str and message in allowed else "Unknown error"
        self.render_snapshot(DeviceState())
        self.settings_page.connection_label.setText(message)
        self._authentication_required = True
        self._update_sign_in()
        self._set_status(message, "warning" if message in ("Authentication rejected", "Sign-in cancelled", "Authentication required") else "error")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closed = True
        if self._sign_in_dialog is not None:
            self._sign_in_dialog.reject()
        self.refresh_controller.shutdown()
        event.accept()

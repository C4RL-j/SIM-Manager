"""One native tray surface rendering the same normalized state as Home."""

from time import monotonic

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMenu, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from sim_manager.account_models import AccountData, AccountPhase, AccountState, SessionValidity
from sim_manager.services.presentation import DeviceView
from sim_manager.sim_models import SimCarrier, SimProfile
from sim_manager.ui.home_display import format_last_updated, format_promo_expiry
from sim_manager.ui.icons import application_icon
from sim_manager.ui.theme import TRAY_STYLESHEET


def _label(text: str = "", role: str = "trayMuted") -> QLabel:
    label = QLabel(text)
    label.setObjectName(role)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    return label


def _popup_geometry(anchor: QRect, available: QRect, desired: QSize) -> QRect:
    """Qt already supplies logical pixels; never apply a second DPI scale."""
    margin = min(8, max(0, min(available.width(), available.height()) // 8))
    width = min(desired.width(), max(1, available.width() - 2 * margin))
    height = min(desired.height(), max(1, available.height() - 2 * margin))
    top = available.top() + margin
    right = available.right() - width + 1
    bottom = available.bottom() - margin - height + 1
    y = anchor.top() - height - margin if not anchor.isEmpty() else bottom
    if y < top and not anchor.isEmpty():
        y = anchor.bottom() + margin + 1
    return QRect(right, min(max(y, top), bottom), width, height)


class _TrayPopup(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("trayDashboard")
        self.setStyleSheet(TRAY_STYLESHEET)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setWindowTitle("SIM Manager")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setFixedWidth(324)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        self.body = QScrollArea()
        self.body.setObjectName("trayBody")
        self.body.setFrameShape(QFrame.Shape.NoFrame)
        self.body.setWidgetResizable(True)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        content = QVBoxLayout(self.content)
        content.setContentsMargins(0, 0, 3, 0)
        content.setSpacing(8)
        self.carrier_label = _label("Active SIM · Unknown")
        self.name_label = _label("No active SIM", "trayName")
        self.data_label = _label("Unavailable", "trayData")
        self.data_label.setAccessibleName("Verified data remaining")
        self.promo_caption = _label("Reported account details")
        self.promo_label = _label("Not available", "trayDetail")
        self.expiry_label = _label("Not available")
        self.updated_label = _label()
        self.account_status_label = _label("Account not connected", "trayStatus")
        self.network_status_label = _label("Network unknown")
        self.schedule_label = _label("Auto refresh off")
        for label in (self.carrier_label, self.name_label):
            content.addWidget(label)
        self.balance_card = QFrame()
        self.balance_card.setObjectName("trayBalanceCard")
        balance = QVBoxLayout(self.balance_card)
        balance.setContentsMargins(12, 10, 12, 10)
        balance.setSpacing(5)
        balance.addWidget(_label("Data remaining"))
        balance.addWidget(self.data_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.reset()
        self.progress_bar.hide()
        balance.addWidget(self.progress_bar)
        for label in (self.promo_caption, self.promo_label, self.expiry_label):
            balance.addWidget(label)
        content.addWidget(self.balance_card)
        for label in (self.updated_label, self.account_status_label,
                      self.network_status_label, self.schedule_label):
            content.addWidget(label)
        self.body.setWidget(self.content)
        layout.addWidget(self.body)
        self.refresh_button = QPushButton("Refresh now")
        self.refresh_button.setObjectName("trayRefresh")
        layout.addWidget(self.refresh_button)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.open_button = QPushButton("Open SIM Manager")
        self.open_button.setObjectName("trayAction")
        self.exit_button = QPushButton("Exit")
        self.exit_button.setObjectName("trayAction")
        actions.addWidget(self.open_button, 1)
        actions.addWidget(self.exit_button)
        layout.addLayout(actions)
        self.fit_content(440)

    def fit_content(self, maximum_height: int) -> None:
        width = max(1, self.width() - 36)
        hint = self.content.layout().totalHeightForWidth(width)
        if hint < 0:
            hint = self.content.sizeHint().height()
        self.body.setFixedHeight(min(max(80, hint + 4), max(80, maximum_height - 116)))
        self.adjustSize()

    def clear_private_content(self) -> None:
        for label in self.content.findChildren(QLabel):
            label.clear()
            label.setToolTip("")
        self.progress_bar.reset()
        self.progress_bar.hide()
        for button in (self.refresh_button, self.open_button, self.exit_button):
            button.setEnabled(False)

    def closeEvent(self, event) -> None:
        # Closing this tool only dismisses it; Exit belongs to the controller.
        self.hide()
        event.ignore()


class TrayDashboard(QObject):
    refresh_requested = Signal()
    open_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent=None, *, enabled: bool = True, icon_factory=None) -> None:
        super().__init__(parent)
        self._closed = False
        self._generation = 0
        self._deactivated_at: float | None = None
        self._hiding = False
        self._owner = parent if isinstance(parent, QWidget) else None
        self.available = False
        self.icon = None
        self.popup = _TrayPopup(self._owner)
        self.menu = QMenu(self._owner)
        self.refresh_action = self.menu.addAction("Refresh now")
        self.open_action = self.menu.addAction("Open SIM Manager")
        self.menu.addSeparator()
        self.exit_action = self.menu.addAction("Exit")
        for signal in (self.popup.refresh_button.clicked, self.refresh_action.triggered):
            signal.connect(self._request_refresh)
        for signal in (self.popup.open_button.clicked, self.open_action.triggered):
            signal.connect(self._open_owner)
        for signal in (self.popup.exit_button.clicked, self.exit_action.triggered):
            signal.connect(self._exit_owner)
        application = QApplication.instance()
        if application is not None:
            application.installEventFilter(self)
        if enabled:
            try:
                factory = icon_factory if icon_factory is not None else QSystemTrayIcon
                self.icon = factory(self)
                if self.icon.isSystemTrayAvailable():
                    branding = application_icon()
                    if branding.isNull():
                        raise ValueError
                    self.icon.setIcon(branding)
                    self.icon.setToolTip("SIM Manager")
                    self.icon.setContextMenu(self.menu)
                    self.icon.activated.connect(self._activated)
                    self.icon.show()
                    self.available = True
            except Exception:
                # Native/fake icon errors must not escape a Qt startup slot.
                if self.icon is not None:
                    try:
                        self.icon.hide()
                    except Exception:
                        pass
                self.available = False
        self.render(None, AccountState(), None, auto_refresh=False, can_refresh=False)

    def _request_refresh(self) -> None:
        if not self._closed:
            self.refresh_requested.emit()

    def _open_owner(self) -> None:
        self.hide_popup()
        if not self._closed:
            self.open_requested.emit()

    def _exit_owner(self) -> None:
        self.hide_popup()
        if not self._closed:
            self.exit_requested.emit()

    def _activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_popup()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            self.hide_popup()

    def _anchor(self) -> QRect:
        if self.icon is not None:
            try:
                value = self.icon.geometry()
                if isinstance(value, QRect):
                    return value
            except Exception:
                pass
        return QRect()

    def _screen(self, anchor: QRect):
        point = anchor.center() if not anchor.isEmpty() else QCursor.pos()
        screen = QGuiApplication.screenAt(point)
        if screen is None and self._owner is not None:
            screen = self._owner.screen()
        return screen or QGuiApplication.primaryScreen()

    def _place_popup(self) -> None:
        anchor = self._anchor()
        screen = self._screen(anchor)
        if screen is None:
            return
        available = screen.availableGeometry()
        self.popup.setFixedWidth(min(324, max(1, available.width() - 16)))
        self.popup.fit_content(min(440, max(160, available.height() - 16)))
        rect = _popup_geometry(anchor, available, QSize(self.popup.width(), self.popup.sizeHint().height()))
        self.popup.setGeometry(rect)

    def toggle_popup(self) -> bool:
        if self._closed or not self.available:
            return False
        # Native tray clicks can deactivate the tool before emitting Trigger.
        # Remember that one dismissal briefly, then consume it exactly once.
        recently_deactivated = (self._deactivated_at is not None
                                and monotonic() - self._deactivated_at < .25)
        self._deactivated_at = None
        self._generation += 1
        if self.popup.isVisible() or recently_deactivated:
            self._hide_window()
            return False
        self._place_popup()
        self.popup.show()
        self.popup.activateWindow()
        return True

    def hide_popup(self) -> None:
        self._generation += 1
        self._deactivated_at = None
        if not self._closed:
            self._hide_window()

    def _hide_window(self) -> None:
        self._hiding = True
        try:
            self.popup.hide()
        finally:
            self._hiding = False

    def eventFilter(self, watched, event) -> bool:
        if self._closed or self._hiding or not self.popup.isVisible():
            return False
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.hide_popup()
            return True
        if event.type() == QEvent.Type.MouseButtonPress:
            point = event.globalPosition().toPoint()
            if not self.popup.frameGeometry().contains(point):
                self.hide_popup()
        elif watched is self.popup and event.type() == QEvent.Type.WindowDeactivate:
            self._deactivated_at = monotonic()
            generation = self._generation
            QTimer.singleShot(0, lambda: self._finish_deactivation(generation))
        return False

    def _finish_deactivation(self, generation: int) -> None:
        if not self._closed and generation == self._generation:
            self._hide_window()

    def render(self, profile: SimProfile | None, state: AccountState, device_view: DeviceView | None,
               *, auto_refresh: bool, can_refresh: bool, schedule_status: str = "") -> None:
        if self._closed:
            return
        profile = profile if isinstance(profile, SimProfile) else None
        state = state if isinstance(state, AccountState) else AccountState()
        eligible = profile is not None and profile.active is True and profile.carrier is SimCarrier.DITO
        connected = eligible and state.phase is AccountPhase.CONNECTED and state.validity is SessionValidity.VALIDATED
        data = state.data if connected and isinstance(state.data, AccountData) else None
        self.popup.carrier_label.setText("Active SIM · " + ("DITO" if profile is not None and profile.carrier is SimCarrier.DITO else "Unknown"))
        self.popup.name_label.setText(profile.name if profile is not None else "No active SIM")
        remaining = data.data_remaining if data is not None and data.data_remaining else "Unavailable"
        self.popup.data_label.setText(remaining)
        names = (tuple(item.name for item in data.active_promos) or tuple(item.name for item in data.data_buckets)) if data is not None else ()
        self.popup.promo_caption.setText("Active promo" if data is not None and data.active_promos else "Reported buckets")
        self.popup.promo_label.setText("\n".join(names) or "Not available")
        self.popup.expiry_label.setText("Expires: " + format_promo_expiry(data))
        self.popup.updated_label.setText(format_last_updated(data.updated_at) if data is not None else "")
        self.popup.progress_bar.reset()
        self.popup.progress_bar.hide()
        issue = getattr(state.data_issue, "value", "")
        if state.phase is AccountPhase.EXPIRED:
            account = "Reconnect DITO"
        elif state.phase is AccountPhase.CONNECTING:
            account = "Complete DITO sign-in in SIM Manager"
        elif issue == "rate_limited":
            account = "MyDITO rate limited" + (" · Values are stale" if data is not None else "")
        elif connected and state.data_refreshing:
            account = "Refreshing MyDITO…" + (" · Previous values are stale" if state.data_stale and data is not None else "")
        elif connected and state.data_stale:
            account = "MyDITO values are stale · Try refresh again"
        elif connected and data is not None:
            account = "MyDITO connected"
        elif connected:
            account = "MyDITO connected · Account data unavailable"
        else:
            account = "MyDITO not connected"
        self.popup.account_status_label.setText(account)
        network = device_view.network_mode if isinstance(device_view, DeviceView) else "Unknown"
        connection = device_view.network_status if isinstance(device_view, DeviceView) else "Unknown"
        sim = device_view.sim_state if isinstance(device_view, DeviceView) else "Unknown"
        description = (network + " · " if network != "Unknown" else "") + (
            "Connected" if connection == "Connected" and sim == "Ready" else
            "Disconnected" if connection == "Disconnected" else
            "SIM not ready" if sim == "Not Ready" else "Network unknown"
        )
        self.popup.network_status_label.setText("Router network: " + description)
        self.popup.schedule_label.setText(schedule_status if type(schedule_status) is str and schedule_status else
                                           "Auto refresh on" if auto_refresh else "Auto refresh off")
        enabled = can_refresh is True and not state.data_refreshing
        self.popup.refresh_button.setEnabled(enabled)
        self.refresh_action.setEnabled(enabled)
        self.popup.refresh_button.setText("Refreshing…" if state.data_refreshing else "Refresh now")
        if self.icon is not None:
            try:
                summary = remaining if len(remaining) <= 90 else remaining[:89] + "…"
                self.icon.setToolTip("SIM Manager\nData remaining: " + summary)
            except Exception:
                pass
        if self.popup.isVisible():
            self._place_popup()

    def shutdown(self) -> None:
        if self._closed:
            return
        self.hide_popup()
        self._closed = True
        self.available = False
        application = QApplication.instance()
        if application is not None:
            application.removeEventFilter(self)
        self.popup.clear_private_content()
        if self.icon is not None:
            for operation in (lambda: self.icon.setToolTip(""), lambda: self.icon.setContextMenu(None), self.icon.hide):
                try:
                    operation()
                except Exception:
                    pass
            self.icon.deleteLater()
        self.menu.clear()
        self.menu.deleteLater()
        self.popup.deleteLater()

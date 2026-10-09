"""Runtime D2 administrator inputs; persistence is owned by the application."""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from sim_manager.storage.windows_credentials import RememberedD2Login


def _password_visibility_icon(revealed: bool) -> QIcon:
    """A small vector eye using the shell's existing monochrome Qt style."""
    icon = QIcon()
    for mode, color in ((QIcon.Mode.Normal, "#97a8ba"), (QIcon.Mode.Active, "#91efda")):
        for ratio in (1, 2, 3):
            pixmap = QPixmap(20 * ratio, 20 * ratio)
            pixmap.setDevicePixelRatio(ratio)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor(color), 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            outline = QPainterPath()
            outline.moveTo(3, 10)
            outline.cubicTo(7, 3, 13, 3, 17, 10)
            outline.cubicTo(13, 17, 7, 17, 3, 10)
            painter.drawPath(outline)
            painter.drawEllipse(QRectF(8, 8, 4, 4))
            if revealed:
                painter.drawLine(3, 3, 17, 17)
            painter.end()
            icon.addPixmap(pixmap, mode)
    return icon


class RouterSignInDialog(QDialog):
    credentials_submitted = Signal(str, str)
    forget_requested = Signal()

    def __init__(
        self, router_address: str, parent: QWidget | None = None, *,
        remembered_login: RememberedD2Login | None = None,
        remember_available: bool = True,
    ) -> None:
        super().__init__(parent)
        self._remember_requested = False
        self.setWindowTitle("Sign in to router")
        self.setMinimumWidth(360)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        heading = QLabel("D2 router administrator sign-in")
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setObjectName("cardTitle")
        layout.addWidget(heading)
        identity_note = QLabel("This is the D2 router admin login, separate from your DITO account.")
        identity_note.setTextFormat(Qt.TextFormat.PlainText)
        identity_note.setObjectName("muted")
        identity_note.setWordWrap(True)
        layout.addWidget(identity_note)
        address = QLabel(router_address)
        address.setTextFormat(Qt.TextFormat.PlainText)
        address.setObjectName("muted")
        address.setWordWrap(True)
        layout.addWidget(address)
        username_label = QLabel("Router username")
        self.username_input = QLineEdit()
        self.username_input.setAccessibleName("Router username")
        self.username_input.setInputMethodHints(
            Qt.InputMethodHint.ImhSensitiveData | Qt.InputMethodHint.ImhNoPredictiveText
            | Qt.InputMethodHint.ImhNoAutoUppercase
        )
        username_label.setBuddy(self.username_input)
        layout.addWidget(username_label)
        layout.addWidget(self.username_input)
        label = QLabel("Router password")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setAccessibleName("Router password")
        self.password_input.setInputMethodHints(
            Qt.InputMethodHint.ImhHiddenText | Qt.InputMethodHint.ImhSensitiveData
            | Qt.InputMethodHint.ImhNoPredictiveText | Qt.InputMethodHint.ImhNoAutoUppercase
        )
        self.password_visibility_action = QAction(_password_visibility_icon(False), "Show password", self.password_input)
        self.password_visibility_action.setCheckable(True)
        self.password_visibility_action.toggled.connect(self._set_password_visibility)
        self.password_input.addAction(self.password_visibility_action, QLineEdit.ActionPosition.TrailingPosition)
        self._set_password_visibility(False)
        label.setBuddy(self.password_input)
        layout.addWidget(label)
        layout.addWidget(self.password_input)
        self.validation_label = QLabel("")
        self.validation_label.setTextFormat(Qt.TextFormat.PlainText)
        self.validation_label.setObjectName("status")
        self.validation_label.setProperty("level", "warning")
        layout.addWidget(self.validation_label)
        self.remember_checkbox = QCheckBox("Remember D2 router login on this PC")
        self.remember_checkbox.setAccessibleName("Remember D2 router login")
        self.remember_checkbox.setChecked(False)
        self.remember_checkbox.setEnabled(remember_available is True)
        layout.addWidget(self.remember_checkbox)
        self.storage_note = QLabel("Remember saves this router login with Windows protection only after a successful sign-in.")
        self.storage_note.setTextFormat(Qt.TextFormat.PlainText)
        self.storage_note.setObjectName("muted")
        self.storage_note.setWordWrap(True)
        layout.addWidget(self.storage_note)
        self.forget_button = QPushButton("Forget saved D2 login")
        self.forget_button.setAccessibleName("Forget saved D2 router login")
        self.forget_button.setVisible(False)
        self.forget_button.clicked.connect(self._forget_saved_login)
        layout.addWidget(self.forget_button)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Sign in")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.password_input.textChanged.connect(lambda: self.validation_label.setText(""))
        self.username_input.textChanged.connect(lambda: self.validation_label.setText(""))
        layout.addWidget(self.buttons)
        if isinstance(remembered_login, RememberedD2Login) and type(remembered_login.username) is str and type(remembered_login.password) is str:
            self.username_input.setText(remembered_login.username)
            self.password_input.setText(remembered_login.password)
            self.remember_checkbox.setChecked(remember_available is True)
            self.forget_button.setVisible(True)
        if remember_available is not True:
            self.set_storage_notice("Saved router login is unavailable. Enter credentials for this session.")
        self.username_input.setFocus()

    @property
    def remember_requested(self) -> bool:
        return self._remember_requested

    def _set_password_visibility(self, revealed: bool) -> None:
        self.password_input.setEchoMode(QLineEdit.EchoMode.Normal if revealed else QLineEdit.EchoMode.Password)
        label = "Hide password" if revealed else "Show password"
        self.password_visibility_action.setText(label)
        self.password_visibility_action.setToolTip(label)
        self.password_visibility_action.setIcon(_password_visibility_icon(revealed))
        for button in self.password_input.findChildren(QToolButton):
            if button.defaultAction() is self.password_visibility_action:
                button.setAccessibleName(label)

    def set_storage_notice(self, message: str) -> None:
        # Only application-owned, fixed notices may be displayed here. Exception
        # or credential text from an injected store is never formatted.
        allowed = {
            "Saved router login is unavailable. Enter credentials for this session.",
            "Saved router login was forgotten.",
            "Saved router login could not be forgotten. Try again later.",
        }
        self.storage_note.setText(message if type(message) is str and message in allowed else "Saved router login is unavailable. Enter credentials for this session.")

    def clear_autofill(self) -> None:
        """Discard saved-input presentation without issuing another store action."""
        self.username_input.setText("")
        self.password_input.setText("")
        self.password_visibility_action.setChecked(False)
        self.remember_checkbox.setChecked(False)
        self._remember_requested = False
        self.forget_button.hide()

    def _forget_saved_login(self) -> None:
        self.clear_autofill()
        self.forget_requested.emit()

    def accept(self) -> None:
        username = self.username_input.text()
        if not username.strip():
            self.validation_label.setText("Enter the router username.")
            self.username_input.setFocus()
            return
        password = self.password_input.text()
        if not password:
            self.validation_label.setText("Enter the router password.")
            self.password_input.setFocus()
            return
        self._remember_requested = self.remember_checkbox.isEnabled() and self.remember_checkbox.isChecked()
        # setText also discards edit history; clearing must not leave an undo
        # action capable of restoring a submitted or dismissed password.
        self.username_input.setText("")
        self.password_input.setText("")
        self.password_visibility_action.setChecked(False)
        try:
            self.credentials_submitted.emit(username, password)
        finally:
            username = None
            password = None
        super().accept()

    def done(self, result: int) -> None:
        self.username_input.setText("")
        self.password_input.setText("")
        self.password_visibility_action.setChecked(False)
        if result != QDialog.DialogCode.Accepted:
            self._remember_requested = False
        super().done(result)

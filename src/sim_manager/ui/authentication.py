"""Runtime router sign-in input, without credential persistence."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout, QWidget,
)


class RouterSignInDialog(QDialog):
    credentials_submitted = Signal(str, str)

    def __init__(self, router_address: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sign in to router")
        self.setMinimumWidth(360)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)
        heading = QLabel("Router authentication required")
        heading.setObjectName("cardTitle")
        layout.addWidget(heading)
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
        label.setBuddy(self.password_input)
        layout.addWidget(label)
        layout.addWidget(self.password_input)
        self.validation_label = QLabel("")
        self.validation_label.setObjectName("status")
        self.validation_label.setProperty("level", "warning")
        layout.addWidget(self.validation_label)
        note = QLabel("Used for this session only. Sign-in details are not saved.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Sign in")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.password_input.textChanged.connect(lambda: self.validation_label.setText(""))
        self.username_input.textChanged.connect(lambda: self.validation_label.setText(""))
        layout.addWidget(self.buttons)
        self.username_input.setFocus()

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
        # setText also discards edit history; clearing must not leave an undo
        # action capable of restoring a submitted or dismissed password.
        self.username_input.setText("")
        self.password_input.setText("")
        try:
            self.credentials_submitted.emit(username, password)
        finally:
            username = None
            password = None
        super().accept()

    def done(self, result: int) -> None:
        self.username_input.setText("")
        self.password_input.setText("")
        super().done(result)

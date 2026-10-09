"""Router and application settings, independent of SIM account controls."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

class SettingsPage(QWidget):
    def __init__(self, parent: QWidget | None = None, *, router_address: str | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
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
        layout.addWidget(self._group("Application information", (
            ("Name", QLabel("SIM Manager")), ("Version", QLabel("0.1.0")),
        )))
        note = QLabel("Router settings are read-only in this version.")
        note.setObjectName("muted")
        layout.addWidget(note)
        layout.addStretch()

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
        for name, value in rows:
            label = QLabel(name)
            label.setObjectName("muted")
            form.addRow(label, value)
        content.addLayout(form)
        return card

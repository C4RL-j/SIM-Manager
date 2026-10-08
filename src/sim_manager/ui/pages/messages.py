"""Messages shell; SMS normalization and read service remain future work."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class MessagesPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        card = QFrame()
        card.setObjectName("card")
        content = QVBoxLayout(card)
        content.setContentsMargins(28, 36, 28, 36)
        content.setSpacing(10)
        title = QLabel("Your messages, in one place")
        title.setObjectName("cardTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description = QLabel("Message reading is not connected yet.")
        description.setObjectName("muted")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        content.addWidget(title)
        content.addWidget(description)
        layout.addWidget(card)
        layout.addStretch()

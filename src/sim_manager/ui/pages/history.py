"""History placeholder; no history collection or backend is implemented."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class HistoryPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        heading = QLabel("History is not available yet.")
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setObjectName("cardTitle")
        heading.setWordWrap(True)
        layout.addWidget(heading)
        note = QLabel("SIM Manager does not collect history in this version.")
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

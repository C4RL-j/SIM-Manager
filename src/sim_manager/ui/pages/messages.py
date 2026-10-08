"""Read-only normalized inbox; private content is rendered only in widgets."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from sim_manager.message_models import Message, MessageInbox


class MessagesPage(QWidget):
    refresh_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None, *, demo: bool = False) -> None:
        super().__init__(parent)
        self._demo = demo
        self._messages: tuple[Message, ...] = ()
        self._loaded = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        toolbar = QHBoxLayout()
        description = QLabel("Read-only inbox • Up to 3 messages per refresh")
        description.setObjectName("muted")
        description.setWordWrap(True)
        toolbar.addWidget(description, 1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setAccessibleName("Cancel messages refresh")
        self.cancel_button.setVisible(False)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("refresh")
        self.refresh_button.setAccessibleName("Refresh messages")
        toolbar.addWidget(self.cancel_button)
        toolbar.addWidget(self.refresh_button)
        layout.addLayout(toolbar)
        self.status_label = QLabel("Open Messages to load the inbox.")
        self.status_label.setObjectName("messageStatus")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.empty_label = QLabel("No messages loaded")
        self.empty_label.setObjectName("muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)
        card = QFrame()
        card.setObjectName("card")
        content = QVBoxLayout(card)
        content.setContentsMargins(12, 10, 12, 12)
        content.setSpacing(8)
        self.message_list = QListWidget()
        self.message_list.setObjectName("messageList")
        self.message_list.setAccessibleName("Messages")
        self.message_list.setMinimumHeight(110)
        self.message_list.setMaximumHeight(230)
        self.message_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.message_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        content.addWidget(self.message_list)
        self.sender_label = QLabel("Select a message")
        self.sender_label.setObjectName("cardTitle")
        self.timestamp_label = QLabel("")
        self.timestamp_label.setObjectName("muted")
        for label in (self.sender_label, self.timestamp_label):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
        content.addWidget(self.sender_label)
        content.addWidget(self.timestamp_label)
        self.content_view = QPlainTextEdit()
        self.content_view.setReadOnly(True)
        self.content_view.setAccessibleName("Message content")
        self.content_view.setPlaceholderText("Select a message to read its content.")
        self.content_view.setMinimumHeight(125)
        self.content_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content.addWidget(self.content_view, 1)
        layout.addWidget(card, 1)
        self.refresh_button.clicked.connect(self.refresh_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.message_list.currentRowChanged.connect(self._select_message)

    @property
    def loaded(self) -> bool:
        return self._loaded

    def set_available(self, available: bool) -> None:
        self.refresh_button.setEnabled(available)
        if not available:
            self.set_notice("SMS service unavailable", "warning")

    def set_notice(self, message: str, level: str = "info") -> None:
        self.status_label.setText(message)
        self.status_label.setProperty("level", level)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def set_busy(self, busy: bool) -> None:
        self.refresh_button.setEnabled(not busy)
        self.refresh_button.setText("Refreshing…" if busy else "Refresh")
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        if busy:
            self.set_notice("Refreshing messages…")

    def set_cancelling(self) -> None:
        self.cancel_button.setEnabled(False)
        self.set_notice("Cancelling messages refresh…")

    def render(self, inbox: MessageInbox) -> None:
        """Replace the visible inbox only after a usable normalized read."""
        messages = tuple(message for message in inbox.messages if isinstance(message, Message))
        # An unreadable partial result cannot establish that the inbox is empty.
        if inbox.partial and not messages:
            self.set_notice("Some messages could not be read", "warning")
            return
        old_row = self.message_list.currentRow()
        self._messages = messages
        self._loaded = True
        self.message_list.clear()
        for message in self._messages:
            sender = message.sender if type(message.sender) is str and message.sender else "Unknown sender"
            timestamp = message.timestamp if type(message.timestamp) is str and message.timestamp else "Unknown time"
            body = message.body if type(message.body) is str else ""
            preview = " ".join(body.split())
            if len(preview) > 110:
                preview = preview[:109] + "…"
            item = QListWidgetItem(f"{sender}  ·  {timestamp}\n{preview or '(Empty message)'}")
            self.message_list.addItem(item)
        self.empty_label.setVisible(not self._messages)
        self.empty_label.setText("No messages")
        if self._messages:
            self.message_list.setCurrentRow(min(max(old_row, 0), len(self._messages) - 1))
        else:
            self._select_message(-1)
        if inbox.partial:
            self.set_notice("Some messages could not be read", "warning")
        elif self._demo:
            self.set_notice("Demo messages • Router not connected")
        else:
            count = len(self._messages)
            self.set_notice(f"{count} message{'s' if count != 1 else ''}" if count else "No messages")

    def _select_message(self, row: int) -> None:
        if not 0 <= row < len(self._messages):
            self.sender_label.setText("Select a message")
            self.timestamp_label.clear()
            self.content_view.clear()
            return
        message = self._messages[row]
        self.sender_label.setText(message.sender if type(message.sender) is str and message.sender else "Unknown sender")
        self.timestamp_label.setText(message.timestamp if type(message.timestamp) is str and message.timestamp else "Unknown time")
        # Plain-text widgets neither interpret HTML nor open links in SMS.
        self.content_view.setPlainText(message.body if type(message.body) is str else "")

    def clear_private_content(self) -> None:
        """Drop in-memory widget/model references when the window closes."""
        self._messages = ()
        self.message_list.clear()
        self._select_message(-1)

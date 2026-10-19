"""Owned, read-only message details with explicit body copying."""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)
from PySide6.QtGui import QTextOption

from sim_manager.message_models import Message
from sim_manager.ui.home_display import format_reported_date
from sim_manager.ui.theme import MESSAGES_STYLESHEET


class MessageDetailsDialog(QDialog):
    def __init__(self, message: Message, parent: QWidget) -> None:
        super().__init__(parent)
        self._message = message if isinstance(message, Message) else None
        self._cleared = False
        self._placed = False
        self.setObjectName("messageDetailsDialog")
        self.setWindowTitle("Message Details")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(MESSAGES_STYLESHEET)
        self.resize(640, 300)
        self.setMinimumSize(400, 240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        card = QFrame()
        card.setObjectName("messageDetailsCard")
        content = QVBoxLayout(card)
        content.setContentsMargins(14, 12, 14, 14)
        content.setSpacing(10)
        header = QVBoxLayout()
        header.setSpacing(4)
        self.sender_label = QLabel()
        self.sender_label.setObjectName("messageDetailsSender")
        self.sender_label.setAccessibleName("Message sender")
        self.timestamp_label = QLabel()
        self.timestamp_label.setObjectName("messageDetailsTimestamp")
        self.timestamp_label.setAccessibleName("Router-reported message time")
        for label in (self.sender_label, self.timestamp_label):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse
                                          | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            header.addWidget(label)
        content.addLayout(header)
        self.content_view = QPlainTextEdit()
        self.content_view.setObjectName("messageDetailsContent")
        self.content_view.setAccessibleName("Full message content")
        self.content_view.setReadOnly(True)
        self.content_view.setUndoRedoEnabled(False)
        self.content_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.content_view.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.content_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content_view.setMinimumHeight(60)
        content.addWidget(self.content_view, 1)
        layout.addWidget(card, 1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch()
        self.copy_button = QPushButton("Copy Message")
        self.copy_button.setObjectName("messageCopy")
        self.copy_button.setAccessibleName("Copy full message body")
        self.copy_button.setAutoDefault(False)
        self.close_button = QPushButton("Close")
        self.close_button.setObjectName("messageClose")
        self.close_button.setDefault(True)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.close_button)
        layout.addLayout(actions)

        sender = message.sender if self._message is not None and type(message.sender) is str and message.sender else "Unknown sender"
        timestamp = message.timestamp if self._message is not None and type(message.timestamp) is str and message.timestamp else "Unknown time"
        body = message.body if self._message is not None and type(message.body) is str else ""
        self.sender_label.setText(sender)
        formatted_time = format_reported_date(timestamp)
        self.timestamp_label.setText(formatted_time)
        if formatted_time != timestamp:
            self.timestamp_label.setToolTip(timestamp)
        self.content_view.setPlainText(body)
        self.copy_button.setEnabled(self._message is not None and type(message.body) is str)
        self.copy_button.clicked.connect(self._copy_message)
        self.close_button.clicked.connect(self.accept)
        self.finished.connect(self.clear_private_content)
        parent.destroyed.connect(self.clear_private_content)

    def __repr__(self) -> str:
        return "MessageDetailsDialog(<details omitted>)"

    def _copy_message(self) -> None:
        if self._cleared or self._message is None or type(self._message.body) is not str:
            return
        try:
            QApplication.clipboard().setText(self._message.body)
        except Exception:
            # Clipboard errors may contain private text; never publish them.
            pass

    def clear_private_content(self, *_unused) -> None:
        """Clear before disposal; unrelated clipboard contents are never read."""
        if self._cleared:
            return
        self._cleared = True
        self._message = None
        self.sender_label.clear()
        self.timestamp_label.clear()
        self.timestamp_label.setToolTip("")
        self.content_view.clear()
        self.copy_button.setEnabled(False)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._placed:
            self._placed = True
            self._place_with_owner()

    def _place_with_owner(self) -> None:
        owner = self.parentWidget().window()
        screen = owner.screen() or self.screen()
        if screen is None:
            return
        available = screen.availableGeometry()
        handle = self.windowHandle()
        margins = handle.frameMargins() if handle is not None else self.contentsMargins()
        max_width = max(1, available.width() - margins.left() - margins.right())
        max_height = max(1, available.height() - margins.top() - margins.bottom())
        if max_width < self.minimumWidth() or max_height < self.minimumHeight():
            self.setMinimumSize(min(self.minimumWidth(), max_width), min(self.minimumHeight(), max_height))
        self.resize(min(self.width(), max_width), min(self.height(), max_height))
        frame = self.frameGeometry()
        center = owner.frameGeometry().center() if owner.isVisible() else available.center()
        left = max(available.left(), min(center.x() - frame.width() // 2,
                                         available.right() - frame.width() + 1))
        top = max(available.top(), min(center.y() - frame.height() // 2,
                                      available.bottom() - frame.height() + 1))
        self.move(QPoint(left, top))

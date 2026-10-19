"""Read-only inbox rows and explicit native details over private normalized SMS."""

from datetime import datetime, timezone
import re

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QTextLayout, QTextOption
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QSizePolicy, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout, QWidget,
)

from sim_manager.message_models import Message, MessageInbox
from sim_manager.sim_models import SimProfile
from sim_manager.ui.home_display import format_last_updated, format_reported_date
from sim_manager.ui.message_details import MessageDetailsDialog
from sim_manager.ui.theme import MESSAGES_STYLESHEET


_SENDER_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_TIMESTAMP_ROLE = _SENDER_ROLE + 1
_PREVIEW_ROLE = _SENDER_ROLE + 2
_ISO_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}"
    r"(?::[0-9]{2}(?:\.[0-9]{1,6})?)?"
    r"(?:Z|[+-](?P<zone_hour>[0-9]{2}):?(?P<zone_minute>[0-9]{2}))?\Z"
)


def _ordered_messages(messages: tuple[Message, ...]) -> tuple[Message, ...]:
    """Sort only a fully recognized, mutually comparable timestamp window."""
    parsed = []
    for message in messages:
        timestamp = message.timestamp
        if type(timestamp) is not str:
            return messages
        match = _ISO_TIMESTAMP.fullmatch(timestamp)
        if (match is None or re.search(r"-00:?00\Z", timestamp)
                or match.group("zone_hour") is not None and (
                    int(match.group("zone_hour")) > 23 or int(match.group("zone_minute")) > 59)):
            return messages
        try:
            value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except (ValueError, OverflowError):
            return messages
        parsed.append(value)
    if not parsed or len({value.utcoffset() is not None for value in parsed}) != 1:
        return messages
    return tuple(message for _, message in sorted(
        zip(parsed, messages), key=lambda pair: pair[0], reverse=True,
    ))


def _compact(value: str, limit: int) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


class _MessageRowDelegate(QStyledItemDelegate):
    """Paint plain text directly; SMS never becomes HTML or a link widget."""

    def sizeHint(self, option, index) -> QSize:
        metrics = QFontMetrics(option.font)
        return QSize(0, metrics.height() + 2 * metrics.lineSpacing() + 30)

    def paint(self, painter, option, index) -> None:
        base = QStyleOptionViewItem(option)
        self.initStyleOption(base, index)
        base.text = ""
        style = base.widget.style() if base.widget is not None else self.parent().style()
        painter.save()
        painter.setClipRect(base.rect)
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, base, painter, base.widget)
        selected = bool(base.state & QStyle.StateFlag.State_Selected)
        foreground = base.palette.highlightedText().color() if selected else base.palette.text().color()
        muted = foreground if selected else QColor("#A2B6CA")
        bounds = base.rect.adjusted(14, 10, -14, -10)
        sender = index.data(_SENDER_ROLE) or "Unknown sender"
        timestamp = index.data(_TIMESTAMP_ROLE) or "Unknown time"
        preview = index.data(_PREVIEW_ROLE) or "(Empty message)"
        sender_font = QFont(base.font)
        sender_font.setBold(True)
        date_font = QFont(base.font)
        date_font.setBold(False)
        if date_font.pixelSize() > 0:
            date_font.setPixelSize(max(10, date_font.pixelSize() - 1))
        elif date_font.pointSizeF() > 0:
            date_font.setPointSizeF(max(8, date_font.pointSizeF() - 1))
        sender_metrics = QFontMetrics(sender_font)
        date_metrics = QFontMetrics(date_font)
        header_height = max(sender_metrics.height(), date_metrics.height())
        date_width = min(date_metrics.horizontalAdvance(timestamp), max(0, int(bounds.width() * .48)))
        sender_width = max(0, bounds.width() - date_width - 18)
        painter.setFont(sender_font)
        painter.setPen(foreground)
        painter.drawText(
            QRectF(bounds.x(), bounds.y(), sender_width, header_height),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            sender_metrics.elidedText(sender, Qt.TextElideMode.ElideRight, sender_width),
        )
        painter.setFont(date_font)
        painter.setPen(muted)
        painter.drawText(
            QRectF(bounds.right() - date_width, bounds.y(), date_width, header_height),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            date_metrics.elidedText(timestamp, Qt.TextElideMode.ElideRight, date_width),
        )
        preview_font = QFont(base.font)
        preview_font.setBold(False)
        preview_metrics = QFontMetrics(preview_font)
        text_layout = QTextLayout(preview, preview_font)
        text_option = QTextOption()
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        text_layout.setTextOption(text_option)
        text_layout.beginLayout()
        first = text_layout.createLine()
        if first.isValid() and bounds.width() > 0:
            first.setLineWidth(bounds.width())
            first.setPosition(QPointF(0, 0))
            painter.setPen(muted)
            first.draw(painter, QPointF(bounds.x(), bounds.y() + header_height + 7))
            # QTextLine offsets count UTF-16 units, while Python slices count
            # code points. Keep emoji/surrogate-pair boundaries intact.
            remainder = preview.encode("utf-16-le", errors="replace")[first.textLength() * 2:].decode(
                "utf-16-le", errors="replace",
            ).lstrip()
            if remainder:
                painter.setFont(preview_font)
                painter.drawText(
                    QRectF(bounds.x(), bounds.y() + header_height + 7 + preview_metrics.lineSpacing(),
                           bounds.width(), preview_metrics.lineSpacing()),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    preview_metrics.elidedText(remainder, Qt.TextElideMode.ElideRight, bounds.width()),
                )
        text_layout.endLayout()
        painter.restore()


class MessagesPage(QWidget):
    refresh_requested = Signal()
    cancel_requested = Signal()
    message_selected = Signal(object)

    def __init__(self, parent: QWidget | None = None, *, demo: bool = False,
                 read_limit: int = 3) -> None:
        super().__init__(parent)
        self.setObjectName("messagesPage")
        self.setStyleSheet(MESSAGES_STYLESHEET)
        self._demo = demo
        self._messages: tuple[Message, ...] = ()
        self._loaded = False
        self._closed = False
        self._revision = 0
        self._details_dialog: MessageDetailsDialog | None = None
        self._dialog_message: Message | None = None
        self.last_refreshed_at: datetime | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.sim_context_label = QLabel()
        self.sim_context_label.setObjectName("messagesMuted")
        self.sim_context_label.setTextFormat(Qt.TextFormat.PlainText)
        self.sim_context_label.setWordWrap(True)
        self.sim_context_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.sim_context_label)
        self.set_sim_context(None)
        toolbar = QHBoxLayout()
        if type(read_limit) is not int or not 1 <= read_limit <= 100:
            read_limit = 3
        description = QLabel(f"Read-only inbox · Up to {read_limit} messages per refresh")
        description.setObjectName("messagesMuted")
        description.setWordWrap(True)
        description.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(description, 1)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("messagesCancel")
        self.cancel_button.setAccessibleName("Cancel messages refresh")
        self.cancel_button.setVisible(False)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("messagesRefresh")
        self.refresh_button.setAccessibleName("Refresh messages")
        toolbar.addWidget(self.cancel_button)
        toolbar.addWidget(self.refresh_button)
        layout.addLayout(toolbar)
        self.status_label = QLabel("Open Messages to load the inbox.")
        self.status_label.setObjectName("messageStatus")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.last_refresh_label = QLabel()
        self.last_refresh_label.setObjectName("messagesLastRefresh")
        self.last_refresh_label.setTextFormat(Qt.TextFormat.PlainText)
        self.last_refresh_label.setWordWrap(True)
        layout.addWidget(self.last_refresh_label)
        self.empty_label = QLabel("No messages loaded")
        self.empty_label.setObjectName("messagesMuted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)
        card = QFrame()
        card.setObjectName("messagesInboxCard")
        content = QVBoxLayout(card)
        content.setContentsMargins(8, 6, 8, 6)
        self.message_list = QListWidget()
        self.message_list.setObjectName("messagesInboxList")
        self.message_list.setAccessibleName("Messages")
        self.message_list.setMinimumHeight(110)
        self.message_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.message_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.message_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.message_list.setUniformItemSizes(True)
        self.message_list.setEditTriggers(QListWidget.EditTrigger.NoEditTriggers)
        self.message_list.setItemDelegate(_MessageRowDelegate(self.message_list))
        self.message_list.installEventFilter(self)
        content.addWidget(self.message_list, 1)
        layout.addWidget(card, 1)
        self.refresh_button.clicked.connect(self.refresh_requested)
        self.cancel_button.clicked.connect(self.cancel_requested)
        self.message_list.currentRowChanged.connect(self._select_message)
        self.message_list.itemDoubleClicked.connect(lambda _item: self.open_selected_message())

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def details_dialog(self) -> MessageDetailsDialog | None:
        return self._details_dialog

    def eventFilter(self, watched, event) -> bool:
        if (watched is self.message_list and event.type() == QEvent.Type.KeyPress
                and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)):
            self.open_selected_message()
            return True
        return super().eventFilter(watched, event)

    def set_sim_context(self, profile: SimProfile | None, current_sim: bool = False) -> None:
        if isinstance(profile, SimProfile) and current_sim:
            name = profile.name if type(profile.name) is str else "Unnamed SIM"
            phone = profile.phone_number if type(profile.phone_number) is str and profile.phone_number else "Number not provided"
            text = f"Inbox for {name} · {phone}"
        elif current_sim:
            text = "Inbox for the inserted SIM · No saved profile"
        else:
            text = "Inbox for the router's SIM · Current SIM not identified"
        self.sim_context_label.setText(text)

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
        """Commit rows and completion time only after a usable normalized read."""
        if self._closed:
            return
        if not isinstance(inbox, MessageInbox) or inbox.available is not True or type(inbox.messages) is not tuple:
            self.set_notice("SMS service unavailable", "warning")
            return
        messages = tuple(message for message in inbox.messages if isinstance(message, Message))
        if inbox.partial and not messages:
            self.set_notice("Some messages could not be read", "warning")
            return
        self._revision += 1
        revision = self._revision
        self._close_details_dialog()
        old_row = self.message_list.currentRow()
        self._messages = _ordered_messages(messages)
        self._loaded = True
        self.message_list.blockSignals(True)
        self.message_list.clear()
        for message in self._messages:
            sender = _compact(message.sender, 512) if type(message.sender) is str and message.sender else "Unknown sender"
            timestamp = _compact(format_reported_date(message.timestamp), 512) if type(message.timestamp) is str and message.timestamp else "Unknown time"
            body = message.body if type(message.body) is str else ""
            preview = _compact(body, 512) or "(Empty message)"
            item = QListWidgetItem(f"{sender} · {timestamp}\n{preview}")
            item.setData(_SENDER_ROLE, sender)
            item.setData(_TIMESTAMP_ROLE, timestamp)
            item.setData(_PREVIEW_ROLE, preview)
            self.message_list.addItem(item)
        self.empty_label.setVisible(not self._messages)
        self.empty_label.setText("No messages")
        self.message_list.setCurrentRow(
            min(max(old_row, 0), len(self._messages) - 1) if self._messages else -1,
        )
        self.message_list.blockSignals(False)
        self._select_message(self.message_list.currentRow())
        if self._closed or revision != self._revision:
            return
        self.last_refreshed_at = datetime.now(timezone.utc)
        self.last_refresh_label.setText(
            format_last_updated(self.last_refreshed_at).replace("Last updated:", "Last refreshed:", 1),
        )
        self.last_refresh_label.setToolTip(self.last_refreshed_at.isoformat(timespec="seconds"))
        if inbox.partial:
            self.set_notice("Some messages could not be read", "warning")
        elif self._demo:
            self.set_notice("Demo messages • Router not connected")
        else:
            count = len(self._messages)
            count_text = f"{count} message{'s' if count != 1 else ''}" if count else "No messages"
            self.set_notice(count_text + " · Inbox loaded from router")

    def _select_message(self, row: int) -> None:
        self.message_selected.emit(self._messages[row] if 0 <= row < len(self._messages) else None)

    def open_selected_message(self) -> bool:
        row = self.message_list.currentRow()
        if self._closed or not 0 <= row < len(self._messages):
            return False
        message = self._messages[row]
        if self._details_dialog is not None and self._dialog_message is message:
            self._details_dialog.show()
            self._details_dialog.activateWindow()
            return True
        self._close_details_dialog()
        dialog = MessageDetailsDialog(message, parent=self.window())
        self._details_dialog = dialog
        self._dialog_message = message
        dialog.finished.connect(lambda _result, owner=dialog: self._details_finished(owner))
        dialog.destroyed.connect(lambda _object=None, owner=dialog: self._details_finished(owner))
        dialog.show()
        return True

    def _details_finished(self, dialog) -> None:
        if self._details_dialog is dialog:
            self._details_dialog = None
            self._dialog_message = None

    def _close_details_dialog(self) -> None:
        dialog, self._details_dialog = self._details_dialog, None
        self._dialog_message = None
        if dialog is not None:
            dialog.clear_private_content()
            dialog.close()

    def clear_private_content(self) -> None:
        """Drop inbox/dialog metadata without retaining another SIM's history."""
        self._revision += 1
        self._close_details_dialog()
        self._messages = ()
        self._loaded = False
        self.message_list.clear()
        self.last_refreshed_at = None
        self.last_refresh_label.clear()
        self.last_refresh_label.setToolTip("")
        self._select_message(-1)
        self.empty_label.setText("No messages loaded")
        self.empty_label.show()
        self.set_notice("Messages not loaded.")

    def reset_inbox(self) -> None:
        """A new SIM cannot inherit the previous SIM's rows/count/read time."""
        self.clear_private_content()
        self.set_notice("Open Messages to load this SIM's inbox.")

    def closeEvent(self, event) -> None:
        self._closed = True
        self.clear_private_content()
        event.accept()

"""Independent cancellable inbox worker, without transport or session knowledge."""

from queue import Empty, Queue
from threading import Event, Thread

from PySide6.QtCore import QObject, QTimer, Signal

from sim_manager.message_models import Message, MessageInbox, MessageIssueCode
from sim_manager.services.messages import MessageProvider


MESSAGE_FAILURES = {
    MessageIssueCode.CANCELLED: "Messages refresh cancelled",
    MessageIssueCode.TIMEOUT: "Messages request timed out",
    MessageIssueCode.UNREACHABLE: "Router unavailable",
    MessageIssueCode.AUTHENTICATION_REQUIRED: "SMS authentication required",
    MessageIssueCode.UNAVAILABLE: "SMS service unavailable",
    MessageIssueCode.MALFORMED_RESPONSE: "Messages response could not be read",
    MessageIssueCode.UNSUPPORTED_RESPONSE: "SMS response is not supported",
}


def _collect_messages(provider: MessageProvider, stop: Event, output: Queue) -> None:
    try:
        if stop.is_set():
            result = ("error", "Messages refresh cancelled")
        else:
            inbox = provider.get_messages(stop_event=stop)
            if (
                not isinstance(inbox, MessageInbox)
                or type(inbox.messages) is not tuple
                or any(not isinstance(message, Message) for message in inbox.messages)
            ):
                result = ("error", "Messages response could not be read")
            elif inbox.available is not True:
                message = "SMS service unavailable"
                for code in inbox.issues:
                    if type(code) is MessageIssueCode and code in MESSAGE_FAILURES:
                        message = MESSAGE_FAILURES[code]
                        break
                result = ("error", message)
            else:
                result = ("inbox", inbox)
    except TimeoutError:
        result = ("error", "Messages request timed out")
    except PermissionError:
        result = ("error", "SMS authentication required")
    except BaseException:
        # Never pass exception objects or strings through Qt/Python diagnostics.
        result = ("error", "SMS service unavailable")
    if stop.is_set():
        result = ("error", "Messages refresh cancelled")
    output.put(result)


class MessagesRefreshController(QObject):
    inbox_ready = Signal(object)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, provider: MessageProvider, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._provider = provider
        self._thread: Thread | None = None
        self._stop: Event | None = None
        self._output: Queue = Queue(maxsize=1)
        self._closed = False
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._poll)

    @property
    def busy(self) -> bool:
        return self._thread is not None

    def start(self) -> bool:
        if self._closed or self.busy:
            return False
        self._stop = Event()
        self._output = Queue(maxsize=1)
        self._thread = Thread(
            target=_collect_messages, args=(self._provider, self._stop, self._output),
            name="sim-manager-messages", daemon=True,
        )
        try:
            self._thread.start()
        except Exception:
            self._thread = None
            self._stop = None
            self.failed.emit("SMS service unavailable")
            return False
        self.busy_changed.emit(True)
        self._timer.start()
        return True

    def cancel(self) -> None:
        if self._stop is not None:
            self._stop.set()

    def _poll(self) -> None:
        worker = self._thread
        if worker is None or worker.is_alive():
            return
        worker.join(timeout=0)
        try:
            kind, value = self._output.get_nowait()
        except Empty:
            kind, value = "error", "SMS service unavailable"
        if self._stop is not None and self._stop.is_set():
            kind, value = "error", "Messages refresh cancelled"
        self._thread = None
        self._stop = None
        self._timer.stop()
        if self._closed:
            return
        self.busy_changed.emit(False)
        if kind == "inbox":
            self.inbox_ready.emit(value)
        else:
            self.failed.emit(value)

    def shutdown(self, timeout: float = 1.0) -> bool:
        """Cancel and bound the join; providers own their request deadlines."""
        already_closed = self._closed
        self._closed = True
        self.cancel()
        self._timer.stop()
        worker = self._thread
        if worker is not None:
            worker.join(timeout=0.0 if already_closed else max(0.0, min(timeout, 1.0)))
        # Detach output even when an injected daemon ignores cancellation. Its
        # late result cannot keep inbox content reachable from this controller.
        output, self._output = self._output, Queue(maxsize=1)
        while True:
            try:
                output.get_nowait()
            except Empty:
                break
        if worker is not None and worker.is_alive():
            return False
        self._thread = None
        self._stop = None
        return True

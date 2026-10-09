"""One cancellable sign-in/snapshot worker; widgets stay on Qt's thread."""

from __future__ import annotations

from queue import Empty, Queue
from threading import Event, Thread

from PySide6.QtCore import QObject, QTimer, Signal

from sim_manager.models import DeviceState
from sim_manager.services.device import (
    AuthenticationError, AuthenticationFailure, RefreshCancelled, SnapshotProvider,
)


AUTHENTICATION_MESSAGES = {
    AuthenticationFailure.REJECTED: "Authentication rejected",
    AuthenticationFailure.MALFORMED: "Malformed authentication response",
    AuthenticationFailure.TIMEOUT: "Router timed out",
    AuthenticationFailure.UNREACHABLE: "Router unreachable",
    AuthenticationFailure.CONNECTION: "Router connection problem",
    AuthenticationFailure.CANCELLED: "Sign-in cancelled",
}


class _RuntimeCredentials:
    """A one-use handoff; worker arguments never retain the submitted string."""

    __slots__ = ("_password", "_username", "remember")

    def __init__(self, username: str, password: str, remember: bool | None = None) -> None:
        self._username = username
        self._password = password
        self.remember = remember

    def take(self) -> tuple[str, str]:
        username, password = self._username, self._password
        self.clear()
        return username, password

    def clear(self) -> None:
        self._username = ""
        self._password = ""
        self.remember = None

    def __repr__(self) -> str:
        return "RuntimeCredentials(<omitted>)"


def _collect_snapshot(
    provider: SnapshotProvider, stop: Event, output: Queue,
    credential: _RuntimeCredentials | None = None,
) -> None:
    # Keep Qt objects out of the worker, including an abandoned non-cooperative
    # injected provider. Never pass an exception object/text to the GUI or hook.
    authenticating = credential is not None
    cancelled = "Sign-in cancelled" if authenticating else "Refresh cancelled"
    error_kind = "authentication_error" if authenticating else "error"
    try:
        if stop.is_set():
            raise RefreshCancelled()
        if credential is not None:
            remember = credential.remember
            username, password = credential.take()
            try:
                # The service authenticates and reads the current snapshot in
                # this single operation; the UI never handles a session/token.
                options = {"username": username, "stop_event": stop}
                if remember is not None:
                    options["remember"] = remember
                state = provider.authenticate(password, **options)
            finally:
                username = None
                password = None
                options = None
        else:
            state = provider.get_device_state(stop_event=stop)
        if stop.is_set():
            result = (error_kind, cancelled)
        elif isinstance(state, DeviceState):
            result = ("snapshot", state)
        else:
            result = (error_kind, "Malformed response")
    except AuthenticationError as error:
        code = error.code
        message = AUTHENTICATION_MESSAGES.get(code, "Unknown error") if type(code) is AuthenticationFailure else "Unknown error"
        result = (error_kind, message)
    except RefreshCancelled:
        result = (error_kind, cancelled)
    except PermissionError:
        result = (error_kind, "Authentication required")
    except TimeoutError:
        result = (error_kind, "Router status unavailable")
    except ValueError:
        result = (error_kind, "Malformed response")
    except BaseException:
        # Interrupts on this background thread must not trigger Python's raw
        # thread exception printer. Main-thread interrupts remain unaffected.
        result = (error_kind, "Unknown error")
    finally:
        if credential is not None:
            credential.clear()
    if stop.is_set():
        result = (error_kind, cancelled)
    output.put(result)


class RefreshController(QObject):
    snapshot_ready = Signal(object)
    failed = Signal(str)
    authentication_failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(
        self, provider: SnapshotProvider, parent: QObject | None = None,
        *, allow_authentication: bool = True,
    ) -> None:
        super().__init__(parent)
        self._provider = provider
        self._allow_authentication = allow_authentication and getattr(provider, "is_demo", False) is not True
        self._authenticating = False
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
        return self._start()

    @property
    def authenticating(self) -> bool:
        return self.busy and self._authenticating

    def authenticate(self, password: str, *, username: str, remember: bool | None = None) -> bool:
        if not self._allow_authentication or not callable(getattr(self._provider, "authenticate", None)):
            return False
        if type(password) is not str or not password or type(username) is not str or not username.strip():
            return False
        if remember is not None and type(remember) is not bool:
            return False
        credential = _RuntimeCredentials(username, password, remember)
        try:
            return self._start(credential)
        finally:
            username = None
            password = None
            if not self.busy or not self._authenticating:
                credential.clear()

    def _start(self, credential: _RuntimeCredentials | None = None) -> bool:
        if self._closed or self.busy:
            if credential is not None:
                credential.clear()
            return False
        self._authenticating = credential is not None
        self._stop = Event()
        self._output = Queue(maxsize=1)
        self._thread = Thread(
            target=_collect_snapshot,
            args=(self._provider, self._stop, self._output, credential),
            name="sim-manager-refresh",
            daemon=True,
        )
        try:
            self._thread.start()
        except Exception:
            if credential is not None:
                credential.clear()
            authenticating = self._authenticating
            self._authenticating = False
            self._thread = None
            self._stop = None
            (self.authentication_failed if authenticating else self.failed).emit("Unknown error")
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
            kind, value = "error", "Unknown error"
        if self._stop is not None and self._stop.is_set():
            kind, value = ("authentication_error", "Sign-in cancelled") if self._authenticating else ("error", "Refresh cancelled")
        self._thread = None
        self._stop = None
        self._authenticating = False
        self._timer.stop()
        if self._closed:
            return
        self.busy_changed.emit(False)
        if kind == "snapshot":
            self.snapshot_ready.emit(value)
        elif kind == "authentication_error":
            self.authentication_failed.emit(value)
        else:
            self.failed.emit(value)

    def shutdown(self, timeout: float = 1.0) -> bool:
        """Cancel, stop Qt polling, and wait at most one second by default.

        Built-in providers are bounded/cooperative and leave no workers. A
        future injected provider must honor cancellation; Python cannot kill
        arbitrary blocked code. Its daemon cannot hold application exit open.
        """
        already_closed = self._closed
        self._closed = True
        self.cancel()
        self._timer.stop()
        if not already_closed:
            try:
                close_provider = getattr(self._provider, "close", None)
                if callable(close_provider):
                    close_provider()
            except Exception:
                # Optional service cleanup must never reveal exception text
                # or prevent the bounded worker join below.
                pass
        worker = self._thread
        if worker is not None:
            worker.join(timeout=0.0 if already_closed else max(0.0, min(timeout, 1.0)))
            if worker.is_alive():
                return False
        self._thread = None
        self._stop = None
        self._authenticating = False
        return True

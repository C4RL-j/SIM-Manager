"""One desktop instance per current user, with a private activation channel."""

from hashlib import sha256

from PySide6.QtCore import QDir, QLockFile, QObject, QStandardPaths, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstanceGuard(QObject):
    activation_requested = Signal()

    def __init__(self, parent=None, *, name: str = "SIMManager.Desktop", lock_directory: str | None = None) -> None:
        super().__init__(parent)
        self._name = name
        directory = lock_directory or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation)
        self._directory = directory
        # Windows named pipes permit multiple listening instances. A separate
        # current-user process lock must claim ownership before opening one.
        self._lock = QLockFile(QDir(directory).filePath("desktop-" + sha256(name.encode()).hexdigest()[:24] + ".lock"))
        self._lock.setStaleLockTime(0)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self._server.newConnection.connect(self._accept_connections)
        self._clients: dict[QLocalSocket, bytes] = {}
        self._owns_server = False
        self.notified_existing = False

    def acquire_or_notify(self) -> bool:
        if self._owns_server:
            return True
        if QDir().mkpath(self._directory) and self._lock.tryLock(0):
            if self._server.listen(self._name):
                self._owns_server = True
                return True
            self._lock.unlock()
        client = QLocalSocket()
        try:
            client.connectToServer(self._name)
            if not client.waitForConnected(1500):
                return False
            written = client.write(b"activate\n")
            self.notified_existing = written == 9 and (client.bytesToWrite() == 0 or client.waitForBytesWritten(1500))
            return False
        finally:
            client.disconnectFromServer()
            client.close()

    def _accept_connections(self) -> None:
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            self._clients[client] = b""
            client.readyRead.connect(lambda owner=client: self._read_activation(owner))
            client.disconnected.connect(lambda owner=client: self._release_client(owner))
            self._read_activation(client)

    def _read_activation(self, client: QLocalSocket) -> None:
        if client not in self._clients or not client.bytesAvailable():
            return
        # Only a fixed local activation message is accepted; no account data
        # or command execution crosses this channel.
        payload = self._clients[client] + bytes(client.read(64))
        if len(payload) < 9 and b"activate\n".startswith(payload):
            self._clients[client] = payload
            return
        if payload == b"activate\n" and not client.bytesAvailable():
            self.activation_requested.emit()
        client.disconnectFromServer()
        if client.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            self._release_client(client)

    def _release_client(self, client: QLocalSocket) -> None:
        if client in self._clients:
            del self._clients[client]
            client.deleteLater()

    def shutdown(self) -> None:
        for client in tuple(self._clients):
            del self._clients[client]
            client.abort()
            client.deleteLater()
        self._server.close()
        self._lock.unlock()
        self._owns_server = False

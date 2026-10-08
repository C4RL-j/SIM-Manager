"""Overview widgets consume safe presentation fields, never router payloads."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from sim_manager.services.presentation import DeviceView


class OverviewPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.values: dict[str, QLabel] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._identity_card())
        layout.addWidget(self._card("Signal", (
            ("RSRP", "rsrp"), ("Secondary RSRP", "secondary_rsrp"), ("RSRQ", "rsrq"),
            ("RSSI", "rssi"), ("SINR", "sinr"), ("Reported bands", "bands"),
        ), note="Units unverified"))
        layout.addWidget(self._card("Connection", (
            ("WAN state", "wan_state"), ("Address availability", "address"),
            ("Router status", "router_status"),
        ), compact=True))
        layout.addStretch(1)

    def _field(self, name: str, key: str, *, primary: bool = False, compact: bool = False) -> QVBoxLayout:
        cell = QVBoxLayout()
        cell.setSpacing(4)
        label, value = QLabel(name), QLabel("Unknown")
        label.setObjectName("muted")
        label.setWordWrap(True)
        value.setObjectName("identity" if primary else "detail" if compact else "metric")
        value.setTextFormat(Qt.TextFormat.PlainText)
        value.setWordWrap(True)
        value.setAccessibleName(name)
        self.values[key] = value
        cell.addWidget(label)
        cell.addWidget(value)
        return cell

    def _identity_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(18, 14, 18, 16)
        outer.setSpacing(12)
        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(12)
        grid.addLayout(self._field("Carrier", "carrier", primary=True), 0, 0, 2, 1, Qt.AlignmentFlag.AlignTop)
        grid.addLayout(self._field("Network", "network_mode"), 0, 1)
        grid.addLayout(self._field("SIM", "sim_state"), 0, 2)
        grid.addLayout(self._field("Network status", "network_status", compact=True), 1, 1)
        grid.addLayout(self._field("PIN check", "pin", compact=True), 1, 2)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        outer.addLayout(grid)
        return card

    def _card(self, title: str, fields: tuple, *, note: str = "", compact: bool = False) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(18, 14, 18, 16)
        outer.setSpacing(12)
        header = QHBoxLayout()
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        header.addWidget(heading)
        if note:
            label = QLabel(note)
            label.setObjectName("muted")
            header.addStretch()
            header.addWidget(label)
        outer.addLayout(header)
        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(14)
        for index, (name, key) in enumerate(fields):
            grid.addLayout(self._field(name, key, compact=compact), index // 3, index % 3)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        outer.addLayout(grid)
        return card

    def render(self, view: DeviceView) -> None:
        for key, label in self.values.items():
            label.setText(getattr(view, key))

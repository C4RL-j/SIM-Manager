"""SIM-oriented home presentation over the existing normalized device view."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout

from sim_manager.sim_models import SimCarrier, SimProfile

from .overview import OverviewPage


class HomePage(OverviewPage):
    messages_requested = Signal()

    def _field(self, name: str, key: str, *, primary: bool = False, compact: bool = False):
        if key == "carrier":
            name = "Router carrier"
        return super()._field(name, key, primary=primary, compact=compact)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.profile_values: dict[str, QLabel] = {}
        card = QFrame()
        card.setObjectName("card")
        content = QVBoxLayout(card)
        content.setContentsMargins(18, 14, 18, 16)
        content.setSpacing(12)
        heading = QHBoxLayout()
        title = QLabel("Active SIM")
        title.setObjectName("cardTitle")
        heading.addWidget(title, 1)
        self.messages_button = QPushButton("Open Messages")
        self.messages_button.setAccessibleName("Open active SIM messages")
        self.messages_button.clicked.connect(self.messages_requested)
        heading.addWidget(self.messages_button)
        content.addLayout(heading)
        self.profile_note = QLabel()
        self.profile_note.setTextFormat(Qt.TextFormat.PlainText)
        self.profile_note.setObjectName("muted")
        self.profile_note.setWordWrap(True)
        content.addWidget(self.profile_note)
        grid = QGridLayout()
        grid.setHorizontalSpacing(22)
        grid.setVerticalSpacing(10)
        for index, (title, key) in enumerate((
            ("Name", "name"), ("Phone number", "phone_number"), ("Carrier label", "carrier"),
            ("Load balance", "load_balance"), ("Data remaining", "data_remaining"),
            ("Promo", "promo"), ("Promo expiry", "promo_expiry"),
        )):
            field = QVBoxLayout()
            field.setSpacing(4)
            label = QLabel(title)
            label.setObjectName("muted")
            label.setWordWrap(True)
            value = QLabel()
            value.setObjectName("detail")
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            policy = value.sizePolicy()
            policy.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
            value.setSizePolicy(policy)
            value.setAccessibleName(title)
            field.addWidget(label)
            field.addWidget(value)
            grid.addLayout(field, index // 3, index % 3)
            self.profile_values[key] = value
        for column in range(3):
            grid.setColumnStretch(column, 1)
        content.addLayout(grid)
        self.layout().insertWidget(0, card)
        self.render_profile(None)

    def render_profile(self, profile: SimProfile | None, current_sim: bool = False,
                       phone_number: str | None = None) -> None:
        if not isinstance(profile, SimProfile):
            profile = None
        self.profile_values["name"].setText(
            profile.name if profile is not None and type(profile.name) is str
            else "Unnamed SIM" if current_sim else "No active SIM"
        )
        self.profile_values["phone_number"].setText(
            profile.phone_number if profile is not None and type(profile.phone_number) is str and profile.phone_number
            else phone_number if profile is None and current_sim and type(phone_number) is str and phone_number
            else "Not provided"
        )
        self.profile_values["carrier"].setText("DITO" if profile is not None and profile.carrier is SimCarrier.DITO else "Unknown")
        for key in ("load_balance", "data_remaining", "promo", "promo_expiry"):
            self.profile_values[key].setText("Not available")
        self.profile_note.setText(
            "Profile for the inserted SIM." if profile is not None and current_sim
            else "Create a profile in SIMs to name this SIM." if current_sim
            else "Insert a SIM and refresh router status."
        )

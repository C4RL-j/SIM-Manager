"""Explicit native number/OTP actions over the existing SIM and inbox services."""

from __future__ import annotations

from html import escape
import time
from typing import Callable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QPalette
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

from sim_manager.services.sign_in_helpers import NewMessageOtpWatch, mydito_number
from sim_manager.services.sim_profiles import SimProfileService
from sim_manager.sim_models import SimCarrier
from sim_manager.ui.messages_refresh import MessagesRefreshController


class SignInHelpers(QFrame):
    """A compact helper, never an authentication form or a second SMS worker.

    The popup binds once to its inserted SIM. A physical context change revokes
    actions even if that same profile later becomes current again. Only reads
    started by this helper after the user's SMS request feed its OTP watch.
    """

    fill_requested = Signal(str)

    def __init__(
        self, profiles: SimProfileService,
        controller: MessagesRefreshController | None,
        refresh: Callable[[], bool] | None,
    ) -> None:
        super().__init__()
        self._profiles: SimProfileService | None = profiles
        self._controller = controller
        self._refresh = refresh
        self._closed = False
        self._watch = NewMessageOtpWatch()
        self._context = self._current_context()
        self._display_snapshot: tuple = ()
        self._last_sequence = 0
        self._generation = 0
        self._owned_generation: int | None = None
        self._next_read = 0.0
        self._starting_read = False
        self._fillable = False
        self._fill_pending = False
        self._copied: str | None = None
        self.setObjectName("signInHelpers")
        self.setFixedHeight(94)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.profile_combo = QComboBox()
        self.profile_combo.setAccessibleName("Saved SIM profiles; inserted SIM selected")
        self.profile_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.profile_combo.setMinimumContentsLength(12)
        self.profile_combo.setMinimumWidth(0)
        self.profile_combo.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed,
        )
        self.copy_number_button = QPushButton("Copy Number")
        row.addWidget(self.profile_combo, 1)
        row.addWidget(self.copy_number_button)
        layout.addLayout(row)
        self.number_label = QLabel()
        self.number_label.setTextFormat(Qt.TextFormat.PlainText)
        self.number_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(self.number_label)

        actions = QWidget()
        actions.setFixedHeight(30)
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)
        self.status_label = QLabel("Get SMS Code on MyDITO to check for a new OTP.")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred,
        )
        self.fill_otp_button = QPushButton("Fill OTP")
        self.copy_otp_button = QPushButton("Copy OTP")
        action_layout.addWidget(self.status_label, 1)
        action_layout.addWidget(self.fill_otp_button)
        action_layout.addWidget(self.copy_otp_button)
        layout.addWidget(actions)
        self.copy_number_button.clicked.connect(self._copy_number)
        self.copy_otp_button.clicked.connect(self._copy_otp)
        self.fill_otp_button.clicked.connect(self._fill_otp)

        self._read_timer = QTimer(self)
        self._read_timer.setInterval(2000)
        self._read_timer.timeout.connect(self._poll)
        self._context_timer = QTimer(self)
        self._context_timer.setInterval(250)
        self._context_timer.timeout.connect(self._sync_profiles)
        if controller is not None:
            controller.inbox_ready.connect(self._inbox_ready)
            controller.failed.connect(self._read_failed)
            controller.busy_changed.connect(self._busy_changed)
        self._sync_profiles()
        self._context_timer.start()

    def _current_context(self) -> tuple[int, str | None]:
        profiles = self._profiles
        active = profiles.active_profile if profiles is not None else None
        return (
            profiles.context_token if profiles is not None else -1,
            active.profile_id if active is not None else None,
        )

    def _context_valid(self) -> bool:
        profiles = self._profiles
        active = profiles.active_profile if profiles is not None else None
        return (
            not self._closed and profiles is not None and profiles.current_sim
            and active is not None and active.carrier is SimCarrier.DITO
            and self._context == self._current_context()
        )

    def _notice(self, text: str) -> None:
        # This method receives only closed, static presentation strings.
        self.status_label.setText(text)
        self.status_label.setToolTip(text)

    def _sync_profiles(self) -> None:
        if self._closed or self._profiles is None:
            return
        profiles = self._profiles
        if self._context != self._current_context():
            self.stop()
            self._notice("SIM changed. Start a new sign-in.")
        snapshot = tuple(
            (profile.profile_id, profile.name, profile.phone_number,
             profile.carrier, profile.active)
            for profile in profiles.profiles
        )
        if snapshot != self._display_snapshot or not self.profile_combo.count():
            self._display_snapshot = snapshot
            self.profile_combo.clear()
            active_index = -1
            for index, profile in enumerate(profiles.profiles):
                carrier = "DITO" if profile.carrier is SimCarrier.DITO else "Unknown"
                number = profile.phone_number or "Number not provided"
                current = profile.active and profiles.current_sim
                prefix = "Current · " if current else ""
                text = f"{prefix}{profile.name} · {carrier} · {number}"
                self.profile_combo.addItem(text, profile.profile_id)
                # Qt guesses rich text in tooltips; profile names are plain
                # user metadata, never markup or an external image/link.
                self.profile_combo.setItemData(
                    index, f"<qt>{escape(text)}</qt>", Qt.ItemDataRole.ToolTipRole,
                )
                item = self.profile_combo.model().item(index)
                item.setEnabled(current)
                item.setSelectable(current)
                if current:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setBackground(QBrush(self.palette().highlight()))
                    item.setForeground(QBrush(self.palette().highlightedText()))
                    active_index = index
                else:
                    item.setForeground(QBrush(self.palette().color(
                        QPalette.ColorGroup.Disabled,
                        QPalette.ColorRole.Text,
                    )))
            if not self.profile_combo.count():
                self.profile_combo.addItem("No saved SIM profiles")
                self.profile_combo.model().item(0).setEnabled(False)
            self.profile_combo.setCurrentIndex(active_index)
        active = profiles.active_profile
        self.number_label.setText(
            f"Inserted SIM number: {active.phone_number or 'Number not provided'}"
            if active is not None and profiles.current_sim
            else "Inserted SIM has no saved profile."
        )
        self.copy_number_button.setEnabled(
            self._context_valid() and active is not None
            and bool(active.phone_number),
        )
        if self._read_timer.isActive() and not self._watch.active:
            self.stop()
            self._notice("OTP check ended. Get SMS Code again to restart.")
        self._render_actions()

    def _render_actions(self) -> None:
        available = self._context_valid() and self._watch.available
        self.fill_otp_button.setVisible(available)
        self.copy_otp_button.setVisible(available)
        self.fill_otp_button.setEnabled(available and self._fillable and not self._fill_pending)
        self.copy_otp_button.setEnabled(available)

    def request_sms_code(self, sequence: int) -> None:
        if (not self._context_valid() or type(sequence) is not int
                or sequence <= self._last_sequence):
            return
        self._last_sequence = sequence
        self._generation += 1
        self._fill_pending = False
        self._clear_copied()
        self._watch.start_request()
        self._next_read = 0.0
        self._render_actions()
        if self._controller is None or self._refresh is None:
            self._watch.cancel()
            self._notice("Inbox helper unavailable. Check Messages manually.")
            return
        self._notice("Checking for a new DITO OTP…")
        self._read_timer.start()
        self._poll()

    def _poll(self) -> None:
        if not self._context_valid():
            self.stop()
            return
        if not self._watch.active:
            self._sync_profiles()
            return
        controller = self._controller
        if (controller is None or self._refresh is None or controller.busy
                or self._owned_generation is not None or self._starting_read
                or time.monotonic() < self._next_read):
            return
        generation = self._generation
        self._owned_generation = generation
        self._next_read = time.monotonic() + 2.0
        self._starting_read = True
        started = False
        try:
            started = self._refresh() is True
        except Exception:
            # The callback could contain raw transport details. Drop it here.
            pass
        finally:
            self._starting_read = False
        if not started and self._owned_generation == generation:
            self._owned_generation = None
            self._notice("Inbox unavailable; waiting for a new OTP…")

    def _busy_changed(self, busy: bool) -> None:
        if busy is False and not self._closed and self._watch.active:
            # Completion dispatches busy=False before the old result. Wait one
            # event turn so that result cannot be attributed to a new read.
            QTimer.singleShot(0, self._poll)

    def _inbox_ready(self, inbox) -> None:
        generation, self._owned_generation = self._owned_generation, None
        if (generation != self._generation or not self._context_valid()
                or not self._watch.active):
            return
        self._watch.observe(inbox)
        self._notice(
            "New likely OTP found. Confirm it is for this sign-in."
            if self._watch.available else "Waiting for a new DITO OTP…",
        )
        self._render_actions()

    def _read_failed(self, _reason: str) -> None:
        generation, self._owned_generation = self._owned_generation, None
        if (generation == self._generation and self._context_valid()
                and self._watch.active):
            self._notice("Inbox unavailable; waiting for a new OTP…")

    def set_fillable(self, fillable: bool) -> None:
        if not self._closed:
            self._fillable = fillable is True
            self._render_actions()

    def _copy_number(self) -> None:
        if not self._context_valid() or self._profiles is None:
            return
        profile = self._profiles.active_profile
        if profile is None or not profile.phone_number:
            return
        number = mydito_number(profile.phone_number)
        try:
            QApplication.clipboard().setText(number)
        except Exception:
            self._notice("Number could not be copied. Try again.")
            return
        self._copied = number
        self._notice("Number copied. Paste it into MyDITO.")

    def _copy_otp(self) -> None:
        if not self._context_valid():
            return
        value = self._watch.value()
        if value is not None:
            try:
                QApplication.clipboard().setText(value)
            except Exception:
                self._notice("OTP could not be copied. Try again.")
                return
            self._copied = value
            self._notice("OTP copied. Paste it into MyDITO.")

    def _fill_otp(self) -> None:
        if not self._context_valid() or not self._fillable or self._fill_pending:
            return
        value = self._watch.value()
        if value is not None:
            self._fill_pending = True
            self._render_actions()
            self.fill_requested.emit(value)

    def fill_result(self, filled: bool) -> None:
        if not self._context_valid() or not self._fill_pending:
            return
        self._fill_pending = False
        self._notice(
            "OTP filled. Click Sign In on MyDITO when ready."
            if filled is True else "Cannot fill here. Copy OTP and paste it into MyDITO.",
        )
        self._render_actions()

    def _clear_copied(self) -> None:
        if self._copied is not None:
            try:
                clipboard = QApplication.clipboard()
                if clipboard.text() == self._copied:
                    clipboard.clear()
            except Exception:
                # Platform exceptions could include clipboard contents. A
                # failed cleanup never keeps another private Python copy.
                pass
            finally:
                self._copied = None

    def stop(self) -> None:
        """Revoke temporary helpers, leaving the shared inbox controller alive."""
        self._generation += 1
        self._read_timer.stop()
        if self._owned_generation is not None and self._controller is not None:
            self._controller.cancel()
        self._owned_generation = None
        self._watch.cancel()
        self._fill_pending = False
        self._clear_copied()
        self._render_actions()

    def shutdown(self) -> None:
        if self._closed:
            return
        self.stop()
        self._closed = True
        self._context_timer.stop()
        controller = self._controller
        if controller is not None:
            for signal, slot in (
                (controller.inbox_ready, self._inbox_ready),
                (controller.failed, self._read_failed),
                (controller.busy_changed, self._busy_changed),
            ):
                try:
                    signal.disconnect(slot)
                except (RuntimeError, TypeError):
                    pass
        self._controller = None
        self._refresh = None
        self._profiles = None
        self._display_snapshot = ()
        self.profile_combo.clear()
        self.number_label.clear()
        self.status_label.clear()
        self.setEnabled(False)

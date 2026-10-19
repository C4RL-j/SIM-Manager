"""One shared account refresh schedule; authentication remains user controlled."""

from math import ceil
from time import monotonic
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from sim_manager.account_models import (
    AccountDataIssue, AccountPhase, AccountState, SessionValidity,
)


class AccountRefreshController(QObject):
    changed = Signal()

    def __init__(self, refresh_callback: Callable[[], bool], parent=None, *, clock=monotonic):
        super().__init__(parent)
        self._refresh = refresh_callback
        self._clock = clock
        self._enabled = True
        self._interval = 30
        self._closed = False
        self._context = None
        self._last_state = None
        self._eligible = False
        self._busy = False
        self._requesting = False
        self._observations = 0
        self._failures = 0
        self._hold_until = 0.0
        self._hold_issue = None
        self._due = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._wake)

    def __repr__(self):
        return "AccountRefreshController(<details omitted>)"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def interval_seconds(self) -> int:
        return self._interval

    @property
    def can_refresh_now(self) -> bool:
        return (not self._closed and self._eligible and not self._busy
                and not self._requesting
                and (self._hold_issue is not AccountDataIssue.RATE_LIMITED
                     or self._clock() >= self._hold_until))

    @property
    def status_text(self) -> str:
        if self._closed:
            return ""
        if not self._eligible:
            return "Sign in to refresh account data."
        if self._busy or self._requesting:
            return "Refreshing account data..."
        remaining = max(0, ceil(self._hold_until - self._clock()))
        if remaining:
            if self._hold_issue is AccountDataIssue.RATE_LIMITED:
                return f"Rate limited. Retry in {remaining}s."
            return f"Automatic retry in {remaining}s." if self._enabled else "Refresh failed. Try Refresh again."
        return f"Automatic refresh every {self._interval}s." if self._enabled else "Automatic refresh off."

    def configure(self, enabled: bool, interval_seconds: int) -> None:
        if type(enabled) is not bool or type(interval_seconds) is not int or interval_seconds not in (15, 30, 60):
            raise ValueError("Account refresh settings are invalid.")
        if self._closed or (enabled == self._enabled and interval_seconds == self._interval):
            return
        was_enabled = self._enabled
        self._enabled, self._interval = enabled, interval_seconds
        if self._eligible and not self._busy and not self._requesting:
            self._due = self._clock() if enabled and not was_enabled else self._clock() + self._interval
        self._arm()
        self.changed.emit()

    def observe(self, state: AccountState, context: object | None) -> None:
        if self._closed:
            return
        eligible = (context is not None and isinstance(state, AccountState)
                    and state.phase is AccountPhase.CONNECTED
                    and state.validity is SessionValidity.VALIDATED
                    and state.is_demo is False
                    and state.data_issue not in (AccountDataIssue.EXPIRED, AccountDataIssue.ACCOUNT_MISMATCH))
        context_changed = context != self._context
        if eligible and not context_changed and state is self._last_state:
            return
        previous_busy = self._busy or self._requesting
        new_session = eligible and (context_changed or not self._eligible)
        self._observations += 1
        self._context = context
        if not eligible:
            self._eligible = self._busy = self._requesting = False
            self._last_state = None
            self._failures = 0
            self._hold_until, self._hold_issue, self._due = 0.0, None, None
            self._timer.stop()
            self.changed.emit()
            return
        if new_session:
            self._failures = 0
            self._hold_until, self._hold_issue = 0.0, None
            self._requesting = False
        self._eligible = True
        self._last_state = state
        self._busy = state.data_refreshing is True
        if self._busy:
            self._requesting = True
            self._due = None
        elif new_session or previous_busy:
            self._requesting = False
            if state.data_issue in (AccountDataIssue.UNAVAILABLE, AccountDataIssue.UNSUPPORTED, AccountDataIssue.RATE_LIMITED):
                self._failed(state.data_issue, state.retry_after_seconds)
            else:
                self._failures = 0
                self._hold_until, self._hold_issue = 0.0, None
                self._due = self._clock() if new_session else self._clock() + self._interval
        elif state.data_issue is AccountDataIssue.RATE_LIMITED:
            # Direct service calls may report the remaining existing cooldown.
            # They must not count as another failed network cycle.
            if self._hold_until <= self._clock():
                self._failed(state.data_issue, state.retry_after_seconds)
            elif type(state.retry_after_seconds) is int:
                self._hold_until = max(self._hold_until, self._clock() + state.retry_after_seconds)
                self._due = self._hold_until
        self._arm()
        self.changed.emit()

    def _failed(self, issue, retry=None) -> None:
        self._failures = min(self._failures + 1, 7)
        delay = min(600, self._interval * 2 ** (self._failures - 1))
        if issue is AccountDataIssue.RATE_LIMITED:
            delay = max(delay, retry if type(retry) is int and 1 <= retry <= 3600 else 60)
        self._hold_until = self._clock() + delay
        self._hold_issue = issue
        self._due = self._hold_until

    def request_now(self) -> bool:
        if not self.can_refresh_now:
            return False
        self._timer.stop()
        self._due = None
        self._hold_until, self._hold_issue = 0.0, None
        self._requesting = True
        observation = self._observations
        self.changed.emit()
        try:
            started = self._refresh() is True
        except Exception:
            # Private provider errors never become GUI text or diagnostics.
            started = False
        if not started and observation == self._observations and self._eligible:
            self._requesting = False
            self._failed(AccountDataIssue.UNAVAILABLE)
        self._arm()
        self.changed.emit()
        return started

    def _arm(self) -> None:
        self._timer.stop()
        if self._closed or not self._eligible or self._busy or self._requesting:
            return
        now = self._clock()
        waiting = self._hold_until > now and (self._enabled or self._hold_issue is AccountDataIssue.RATE_LIMITED)
        target = self._hold_until if waiting else self._due if self._enabled else None
        if target is not None:
            self._timer.start(max(0, ceil((target - now) * 1000)))

    def _wake(self) -> None:
        if self._closed or not self._eligible or self._busy or self._requesting:
            return
        now = self._clock()
        if self._hold_until > now or self._enabled and self._due is not None and self._due > now:
            self._arm()
            return
        if self._enabled:
            self.request_now()
        else:
            self._timer.stop()
            self.changed.emit()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        self._refresh = None
        self._last_state = self._context = self._due = None
        self._eligible = self._busy = self._requesting = False
        self.changed.emit()

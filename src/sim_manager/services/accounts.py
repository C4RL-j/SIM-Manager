"""Authentication lifecycle over an injected, isolated carrier browser.

The browser retains its own private in-memory session. This service stores only
closed state and, while connecting, one temporary likely OTP. It performs no
HTTP, SMS retrieval, persistence, automatic fill or automatic submission.
"""

from __future__ import annotations

from dataclasses import replace
from threading import RLock
from typing import Callable, Protocol

from sim_manager.account_models import (
    AccountIssue, AccountPhase, AccountState, AuthEvent, SessionValidity,
)
from sim_manager.carriers.dito import DitoOtpCandidate, match_otp
from sim_manager.message_models import MessageInbox


class AccountBrowser(Protocol):
    def open(self, callback: Callable[[AuthEvent], None]) -> None:
        ...

    def show(self) -> None:
        ...

    def close(self) -> None:
        ...


class AccountService(Protocol):
    is_demo: bool

    @property
    def state(self) -> AccountState:
        ...

    def set_listener(self, callback: Callable[[AccountState], None] | None) -> None:
        ...

    def connect(self) -> bool:
        ...

    def disconnect(self) -> None:
        ...

    def cancel(self) -> None:
        ...

    def shutdown(self) -> None:
        ...

    def offer_otp(self, inbox: MessageInbox) -> None:
        ...

    def otp_for_copy(self) -> str | None:
        ...


class DitoAccountService:
    """One explicit login attempt; stale callbacks cannot restore a session.

    Browser operations and listeners must be nonblocking; a native browser
    adapter owns its event loop. The service imports no GUI framework. A missing
    factory fails closed and never launches a browser implicitly.
    """

    def __init__(
        self, browser_factory: Callable[[], AccountBrowser] | None = None,
        *, is_demo: bool = False,
    ) -> None:
        self.is_demo = bool(is_demo)
        self._factory = browser_factory
        self._browser: AccountBrowser | None = None
        self._listener: Callable[[AccountState], None] | None = None
        self._state = AccountState(is_demo=self.is_demo)
        self._otp: DitoOtpCandidate | None = None
        self._generation = 0
        self._closed = False
        self._lock = RLock()

    def __repr__(self) -> str:
        return "DitoAccountService(<details omitted>)"

    @property
    def state(self) -> AccountState:
        with self._lock:
            return self._state

    def set_listener(self, callback: Callable[[AccountState], None] | None) -> None:
        with self._lock:
            self._listener = callback if not self._closed else None
        self._notify()

    def _notify(self) -> None:
        # Never forward listener errors, tracebacks, or private callback reprs.
        with self._lock:
            callback, state = self._listener, self._state
        if callback is not None:
            try:
                callback(state)
            except Exception:
                pass

    @staticmethod
    def _close_browser(browser: AccountBrowser | None) -> None:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass

    def connect(self) -> bool:
        with self._lock:
            if self._closed or self._state.phase is AccountPhase.CONNECTED:
                return False
            if self._state.phase is AccountPhase.CONNECTING:
                existing_browser = self._browser
                generation = self._generation
                connecting = True
            else:
                existing_browser = None
                connecting = False
                self._generation += 1
                generation = self._generation
                self._otp = None
                self._state = AccountState(
                    phase=AccountPhase.CONNECTING, is_demo=self.is_demo,
                )
        if connecting:
            if existing_browser is not None:
                try:
                    existing_browser.show()
                except Exception:
                    self._receive(AuthEvent.UNAVAILABLE, generation)
            return False
        self._notify()
        with self._lock:
            if generation != self._generation or self._closed:
                return False
        if self._factory is None or self.is_demo:
            self._receive(AuthEvent.UNAVAILABLE, generation)
            return False
        browser: AccountBrowser | None = None
        try:
            browser = self._factory()
            if browser is None:
                raise TypeError
            with self._lock:
                if generation != self._generation or self._closed:
                    stale = True
                else:
                    stale = False
                    self._browser = browser
            if stale:
                self._close_browser(browser)
                return False
            browser.open(lambda event: self._receive(event, generation))
        except Exception:
            # Raw factory/browser errors may contain credentials or URLs.
            self._receive(AuthEvent.UNAVAILABLE, generation)
            return False
        return True

    def _receive(self, event: AuthEvent, generation: int) -> None:
        browser: AccountBrowser | None = None
        with self._lock:
            if self._closed or generation != self._generation:
                return
            if not isinstance(event, AuthEvent):
                event = AuthEvent.UNSUPPORTED
            if event is AuthEvent.REJECTED:
                if self._state.phase is not AccountPhase.CONNECTING:
                    return
                self._otp = None
                self._state = AccountState(
                    phase=AccountPhase.CONNECTING,
                    issue=AccountIssue.REJECTED, is_demo=self.is_demo,
                )
            elif event is AuthEvent.AUTHENTICATED:
                self._otp = None
                self._state = AccountState(
                    phase=AccountPhase.CONNECTED,
                    validity=SessionValidity.VALIDATED, is_demo=self.is_demo,
                )
            else:
                self._generation += 1
                self._otp = None
                browser, self._browser = self._browser, None
                if event is AuthEvent.EXPIRED:
                    self._state = AccountState(
                        phase=AccountPhase.EXPIRED,
                        validity=SessionValidity.EXPIRED,
                        issue=AccountIssue.EXPIRED, is_demo=self.is_demo,
                    )
                elif event is AuthEvent.DISCONNECTED:
                    self._state = AccountState(is_demo=self.is_demo)
                else:
                    self._state = AccountState(
                        phase=AccountPhase.ERROR,
                        issue=(AccountIssue.UNSUPPORTED_RESPONSE
                               if event is AuthEvent.UNSUPPORTED
                               else AccountIssue.UNAVAILABLE),
                        is_demo=self.is_demo,
                    )
        self._close_browser(browser)
        self._notify()

    def _disconnect(self, issue: AccountIssue | None = None) -> None:
        with self._lock:
            self._generation += 1
            browser, self._browser = self._browser, None
            self._otp = None
            self._state = AccountState(issue=issue, is_demo=self.is_demo)
        self._close_browser(browser)
        self._notify()

    def disconnect(self) -> None:
        self._disconnect()

    def cancel(self) -> None:
        self._disconnect(AccountIssue.CANCELLED)

    def shutdown(self) -> None:
        with self._lock:
            self._closed = True
            self._listener = None
            self._factory = None
        self._disconnect()

    def offer_otp(self, inbox: MessageInbox) -> None:
        # No message, sender, identifier or timestamp is retained here.
        with self._lock:
            if self._closed or self._state.phase is not AccountPhase.CONNECTING:
                return
            generation = self._generation
        if not isinstance(inbox, MessageInbox) or inbox.available is not True:
            return
        if type(inbox.messages) is not tuple:
            return
        candidate: DitoOtpCandidate | None = None
        ambiguous = False
        for message in inbox.messages:
            found = match_otp(message)
            if found is None:
                continue
            if candidate is None:
                candidate = found
            elif found.copy_value() != candidate.copy_value():
                ambiguous = True
                break
        with self._lock:
            if (self._closed or generation != self._generation
                    or self._state.phase is not AccountPhase.CONNECTING):
                return
            self._otp = None if ambiguous else candidate
            self._state = replace(self._state, otp_available=self._otp is not None)
        self._notify()

    def otp_for_copy(self) -> str | None:
        with self._lock:
            if (self._closed or self._state.phase is not AccountPhase.CONNECTING
                    or self._otp is None):
                return None
            return self._otp.copy_value()


class DemoAccountService:
    """Explicit synthetic lifecycle without browser, network, OTP or storage."""

    is_demo = True

    def __init__(self) -> None:
        self._state = AccountState(is_demo=True)
        self._listener: Callable[[AccountState], None] | None = None
        self._closed = False

    def __repr__(self) -> str:
        return "DemoAccountService(<details omitted>)"

    @property
    def state(self) -> AccountState:
        return self._state

    def set_listener(self, callback: Callable[[AccountState], None] | None) -> None:
        self._listener = callback if not self._closed else None
        self._notify()

    def _notify(self) -> None:
        if self._listener is not None:
            try:
                self._listener(self._state)
            except Exception:
                pass

    def connect(self) -> bool:
        if self._closed or self._state.phase is AccountPhase.CONNECTED:
            return False
        self._state = AccountState(
            phase=AccountPhase.CONNECTED,
            validity=SessionValidity.VALIDATED, is_demo=True,
        )
        self._notify()
        return True

    def disconnect(self) -> None:
        self._state = AccountState(is_demo=True)
        self._notify()

    def cancel(self) -> None:
        self._state = AccountState(issue=AccountIssue.CANCELLED, is_demo=True)
        self._notify()

    def shutdown(self) -> None:
        self._closed = True
        self._listener = None
        self.disconnect()

    def offer_otp(self, inbox: MessageInbox) -> None:
        pass

    def otp_for_copy(self) -> str | None:
        return None

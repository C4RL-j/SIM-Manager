"""Account lifecycle over an injected, isolated carrier browser.

The browser retains its own private in-memory session. This service stores only
normalized account data and, while connecting, one temporary likely OTP. It
performs no HTTP, SMS retrieval, persistence, fill or automatic submission.
"""

from __future__ import annotations

from dataclasses import replace
from math import ceil
from threading import RLock
from time import monotonic
from typing import Callable, Protocol

from sim_manager.account_models import (
    AccountData, AccountDataIssue, AccountDataResult, AccountIssue, AccountPhase,
    AccountState, AuthEvent, SessionValidity, MAX_ACCOUNT_RETRY_SECONDS,
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

    def refresh_account(self) -> bool:
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
        *, is_demo: bool = False, clock: Callable[[], float] = monotonic,
    ) -> None:
        self.is_demo = bool(is_demo)
        self._factory = browser_factory
        self._browser: AccountBrowser | None = None
        self._listener: Callable[[AccountState], None] | None = None
        self._state = AccountState(is_demo=self.is_demo)
        self._otp: DitoOtpCandidate | None = None
        self._generation = 0
        self._data_request = 0
        self._clock = clock
        self._cooldown_until = 0.0
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
        refresh_data = False
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
                # A duplicate observer event must not clear data or start a loop.
                if self._state.phase is not AccountPhase.CONNECTING:
                    return
                self._otp = None
                self._state = AccountState(
                    phase=AccountPhase.CONNECTED,
                    validity=SessionValidity.VALIDATED, is_demo=self.is_demo,
                )
                refresh_data = True
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
        if refresh_data:
            self.refresh_account()

    def refresh_account(self) -> bool:
        """Start one asynchronous read through the current browser session.

        Legacy authentication-only browsers may omit the read method. Their
        successful authentication state remains unchanged. Request/session
        revisions also protect against synchronous callbacks and cancellation.
        """
        with self._lock:
            if (self._closed or self._state.phase is not AccountPhase.CONNECTED
                    or self._state.data_refreshing or self._browser is None
                    or self.is_demo):
                return False
            browser = self._browser
            generation = self._generation
            remaining = ceil(self._cooldown_until - self._clock())
            if remaining > 0:
                self._state = replace(
                    self._state, data_issue=AccountDataIssue.RATE_LIMITED,
                    data_stale=self._state.data is not None,
                    retry_after_seconds=min(remaining, MAX_ACCOUNT_RETRY_SECONDS),
                )
        if remaining > 0:
            self._notify()
            return False
        try:
            refresh = getattr(browser, "refresh_account", None)
        except Exception:
            refresh = None
        if not callable(refresh):
            return False
        with self._lock:
            if (self._closed or generation != self._generation
                    or browser is not self._browser
                    or self._state.phase is not AccountPhase.CONNECTED
                    or self._state.data_refreshing or self._clock() < self._cooldown_until):
                return False
            self._data_request += 1
            request = self._data_request
            self._state = replace(self._state, data_refreshing=True, data_issue=None,
                                  retry_after_seconds=None)
        self._notify()
        with self._lock:
            if (self._closed or generation != self._generation
                    or browser is not self._browser
                    or request != self._data_request
                    or not self._state.data_refreshing):
                return False
        try:
            started = refresh(
                lambda result: self._receive_data(result, generation, request, browser),
            )
        except Exception:
            # Browser exceptions can contain private URLs, tokens or payloads.
            self._receive_data(
                AccountDataResult(issue=AccountDataIssue.UNAVAILABLE),
                generation, request, browser,
            )
            return False
        if started is not True:
            self._receive_data(
                AccountDataResult(issue=AccountDataIssue.UNAVAILABLE),
                generation, request, browser,
            )
            return False
        return True

    def _receive_data(
        self, result: AccountDataResult, generation: int, request: int,
        owner: AccountBrowser,
    ) -> None:
        browser: AccountBrowser | None = None
        with self._lock:
            if (self._closed or generation != self._generation
                    or request != self._data_request or owner is not self._browser
                    or self._state.phase is not AccountPhase.CONNECTED
                    or not self._state.data_refreshing):
                return
            if type(result) is not AccountDataResult:
                result = AccountDataResult(issue=AccountDataIssue.UNSUPPORTED)
            data, issue = result.data, result.issue
            if (data is not None and type(data) is not AccountData
                    or issue is not None and not isinstance(issue, AccountDataIssue)
                    or (data is None) == (issue is None)):
                data, issue = None, AccountDataIssue.UNSUPPORTED
            if issue in (AccountDataIssue.EXPIRED, AccountDataIssue.ACCOUNT_MISMATCH):
                # Revoke both callback families before profile disposal. No old
                # value may survive expiry or belong to another SIM/account.
                self._generation += 1
                self._otp = None
                browser, self._browser = self._browser, None
                if issue is AccountDataIssue.EXPIRED:
                    self._state = AccountState(
                        phase=AccountPhase.EXPIRED, validity=SessionValidity.EXPIRED,
                        issue=AccountIssue.EXPIRED, is_demo=self.is_demo,
                        data_issue=issue,
                    )
                else:
                    self._state = AccountState(
                        phase=AccountPhase.ERROR, issue=AccountIssue.UNSUPPORTED_RESPONSE,
                        is_demo=self.is_demo, data_issue=issue,
                    )
            elif data is not None:
                self._state = replace(
                    self._state, data=data, data_refreshing=False,
                    data_stale=False, data_issue=None,
                    retry_after_seconds=None,
                )
            else:
                retry = result.retry_after_seconds if issue is AccountDataIssue.RATE_LIMITED else None
                if issue is AccountDataIssue.RATE_LIMITED:
                    self._cooldown_until = self._clock() + (retry or 60)
                self._state = replace(
                    self._state, data_refreshing=False, data_stale=self._state.data is not None,
                    data_issue=issue, retry_after_seconds=retry,
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

    def refresh_account(self) -> bool:
        # Demo never reads a live carrier account or fabricates balances.
        return False

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

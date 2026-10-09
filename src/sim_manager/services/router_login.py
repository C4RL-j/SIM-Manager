"""D2 admin login with opt-in Windows storage; no carrier account state."""

from enum import Enum
from threading import Event, Lock, RLock
from typing import Protocol

from sim_manager.models import DeviceState
from sim_manager.services.device import AuthenticationError, AuthenticationFailure
from sim_manager.storage.windows_credentials import RememberedD2Login


class D2LoginStore(Protocol):
    def load(self) -> RememberedD2Login | None: ...
    def save(self, username: str, password: str) -> None: ...
    def delete(self) -> None: ...


class LoginStorageIssue(str, Enum):
    LOAD = "load"
    SAVE = "save"
    DELETE = "delete"


class D2LoginService:
    """Wrap one router provider, with no cached password or retry loop.

    The caller's single cancellable worker owns authentication. Store writes
    and Forget share a lock/generation so an old attempt cannot restore a saved
    login or session. Only the router service's session proof permits saving.
    """

    is_demo = False

    def __init__(self, provider, store: D2LoginStore) -> None:
        if getattr(provider, "is_demo", False) is True:
            raise ValueError("Remembered router login is unavailable in demo mode.")
        self._provider = provider
        self._store = store
        self._lock = RLock()
        self._storage_lock = Lock()
        self._generation = 0
        self._closed = False
        self._autofill_disabled = False
        self._saved = False
        self._issue: LoginStorageIssue | None = None

    def __repr__(self) -> str:
        return "D2LoginService(<details omitted>)"

    @property
    def router_address(self) -> str:
        return self._provider.router_address

    @property
    def saved_login_available(self) -> bool:
        with self._lock:
            return self._saved

    @property
    def storage_issue(self) -> LoginStorageIssue | None:
        with self._lock:
            return self._issue

    def load_remembered_login(self) -> RememberedD2Login | None:
        with self._lock:
            if self._closed or self._autofill_disabled:
                return None
            generation = self._generation
        failure = False
        record = None
        with self._storage_lock:
            try:
                record = self._store.load()
                if record is not None and (
                    not isinstance(record, RememberedD2Login)
                    or type(record.username) is not str or not record.username.strip()
                    or type(record.password) is not str or not record.password
                ):
                    failure = True
            except Exception:
                failure = True
        with self._lock:
            if self._closed or generation != self._generation or self._autofill_disabled:
                return None
            if failure:
                self._issue = LoginStorageIssue.LOAD
                return None
            self._issue = None
            self._saved = record is not None
            return record

    def _revoked(self, generation: int, stop_event: Event | None) -> bool:
        with self._lock:
            return (self._closed or generation != self._generation
                    or (stop_event is not None and stop_event.is_set()))

    def authenticate(self, password: str, *, username: str,
                     stop_event: Event | None = None,
                     remember: bool | None = None) -> DeviceState:
        with self._lock:
            generation = self._generation
        if self._revoked(generation, stop_event):
            raise AuthenticationError(AuthenticationFailure.CANCELLED) from None
        if remember is not None and type(remember) is not bool:
            raise AuthenticationError(AuthenticationFailure.MALFORMED) from None
        try:
            failure = None
            state = None
            try:
                state = self._provider.authenticate(password, username=username, stop_event=stop_event)
            except AuthenticationError as error:
                failure = error.code if type(error.code) is AuthenticationFailure else AuthenticationFailure.MALFORMED
            except Exception:
                failure = AuthenticationFailure.MALFORMED
            if failure is not None:
                raise AuthenticationError(failure) from None
            if not isinstance(state, DeviceState):
                raise AuthenticationError(AuthenticationFailure.MALFORMED) from None
            if self._revoked(generation, stop_event):
                self._invalidate()
                raise AuthenticationError(AuthenticationFailure.CANCELLED) from None
            # Snapshot usability is separate from proof that login established
            # an Authorization-bearing session which remains valid now.
            failure = None
            verified = False
            try:
                verified = self._provider.is_authenticated() is True
            except Exception:
                failure = AuthenticationFailure.MALFORMED
            if failure is not None:
                raise AuthenticationError(failure) from None
            if not verified:
                raise AuthenticationError(AuthenticationFailure.REJECTED) from None
            if remember is not None:
                # Serialize vault operations, without holding the state lock
                # across native calls. Shutdown can always revoke immediately.
                with self._storage_lock:
                    if self._revoked(generation, stop_event):
                        self._invalidate()
                        raise AuthenticationError(AuthenticationFailure.CANCELLED) from None
                    failure = False
                    try:
                        if remember is True:
                            self._store.save(username, password)
                        else:
                            self._store.delete()
                    except Exception:
                        failure = True
                    revoked = self._revoked(generation, stop_event)
                    deleted = False
                    if revoked and remember is True and not failure:
                        # A late completed write cannot restore forgotten or
                        # cancelled credentials. Forget's own delete is also
                        # serialized behind this operation.
                        try:
                            self._store.delete()
                            deleted = True
                        except Exception:
                            pass
                    with self._lock:
                        if revoked:
                            if remember is True and not failure:
                                self._saved = not deleted
                                self._issue = None if deleted else LoginStorageIssue.DELETE
                        elif failure:
                            self._issue = LoginStorageIssue.SAVE if remember is True else LoginStorageIssue.DELETE
                        else:
                            self._saved = remember is True
                            self._issue = None
                            self._autofill_disabled = remember is not True
                    if revoked:
                        self._invalidate()
                        raise AuthenticationError(AuthenticationFailure.CANCELLED) from None
            if self._revoked(generation, stop_event):
                self._invalidate()
                raise AuthenticationError(AuthenticationFailure.CANCELLED) from None
            return state
        finally:
            username = None
            password = None

    def get_device_state(self, *, stop_event: Event | None = None) -> DeviceState:
        return self._provider.get_device_state(stop_event=stop_event)

    def _invalidate(self) -> None:
        try:
            self._provider.invalidate_session()
        except Exception:
            pass

    def forget_saved_login(self) -> bool:
        with self._lock:
            self._generation += 1
            self._autofill_disabled = True
        self._invalidate()
        failure = False
        with self._storage_lock:
            try:
                self._store.delete()
            except Exception:
                failure = True
        with self._lock:
            if failure:
                self._issue = LoginStorageIssue.DELETE
                return False
            self._saved = False
            self._issue = None
            return True

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._generation += 1
            self._autofill_disabled = True
        self._invalidate()
        try:
            self._provider.close()
        except Exception:
            pass

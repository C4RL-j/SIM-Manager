"""Bind saved metadata to observed SIM identity without phone-number matching."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from sim_manager.account_models import AccountIssue, AccountPhase, AccountState, SessionValidity
from sim_manager.models import DeviceIssue, DeviceState, Readiness, SimState
from sim_manager.sim_models import SimCarrier, SimProfile, SimProfileValidationError, normalize_phone_number, valid_identity_key
from sim_manager.storage.sim_profiles import MemorySimProfileStore, SimProfileStore, SimProfileStoreError, WindowsSimProfileStore


class SimProfileService:
    def __init__(self, store: SimProfileStore | None = None, demo: bool = False) -> None:
        if demo and isinstance(store, WindowsSimProfileStore):
            raise ValueError("Demo SIM profiles require memory storage.")
        self._store = store if store is not None else MemorySimProfileStore()
        self._demo = bool(demo)
        self._profiles: tuple[SimProfile, ...] = ()
        self._current_sim = False
        self._identity: str | None = None
        self._phone: str | None = None
        self._context: tuple[str, str | None] | None = None
        self._revision = 0
        self._storage_failed = False
        self._closed = False
        try:
            loaded = MemorySimProfileStore(self._store.load()).load()
            self._profiles = tuple(replace(profile, account_state=self._disconnected()) for profile in loaded)
        except Exception as error:
            error.__traceback__ = None
            error.__context__ = None
            error.__cause__ = None
            self._storage_failed = True

    def _disconnected(self) -> AccountState:
        return AccountState(is_demo=self._demo)

    @property
    def profiles(self) -> tuple[SimProfile, ...]:
        return self._profiles

    @property
    def is_demo(self) -> bool:
        return self._demo

    @property
    def active_profile(self) -> SimProfile | None:
        return next((profile for profile in self._profiles if profile.active), None)

    @property
    def current_sim(self) -> bool:
        return self._current_sim

    @property
    def current_phone_number(self) -> str | None:
        return self._phone

    @property
    def current_identity(self) -> str | None:
        return self._identity

    @property
    def identity_verified(self) -> bool:
        return self._current_sim and self._identity is not None

    @property
    def context_token(self) -> int:
        """Opaque local revision; metadata edits never change physical context."""
        return self._revision

    @property
    def can_create(self) -> bool:
        return not self._closed and not self._storage_failed and self._current_sim and self.active_profile is None

    @property
    def notice(self) -> str:
        if self._storage_failed:
            return "Saved SIM profiles are unavailable."
        if not self._current_sim:
            return "Current SIM is unavailable."
        if self.active_profile is None:
            return "Create a profile for the current SIM."
        if self._identity is None:
            return "SIM identity is unverified. This profile will not match automatically."
        return ""

    def observe(self, state: DeviceState) -> bool:
        """Return true only when usable SIM evidence changes physical context.

        Router authentication and transport failures provide no replacement
        evidence and preserve the last observed binding. A successful SIM read
        with missing identity conservatively moves to an unverified context.
        """
        if self._closed or not isinstance(state, DeviceState) or not isinstance(state.sim, SimState):
            return False
        errors = state.errors if isinstance(state.errors, tuple) else ()
        failed_sources = {issue.source for issue in errors if isinstance(issue, DeviceIssue) and isinstance(issue.source, str)}
        supplied_sources = state.successful_sources if isinstance(state.successful_sources, tuple) else ()
        successful_sources = {source for source in supplied_sources if isinstance(source, str)}
        if "sim" not in successful_sources or "sim" in failed_sources:
            return False
        explicit_absence = state.sim.present is False
        ready = not explicit_absence and state.sim.readiness is Readiness.READY
        device_succeeded = "device" in successful_sources and "device" not in failed_sources
        if ready and not device_succeeded and self._identity is not None:
            # A failed identity getter cannot prove replacement or identity loss.
            return False
        identity = state.sim.identity_key if ready and device_succeeded and valid_identity_key(state.sim.identity_key) else None
        phone = state.sim.phone_number if ready and "deviceDetails" in successful_sources and "deviceDetails" not in failed_sources else None
        # Treat injected data with the same syntax policy as normalized status.
        if phone is not None:
            try:
                phone = normalize_phone_number(phone)
            except SimProfileValidationError:
                phone = None
        context = ("known", identity) if identity is not None else ("unverified", phone) if ready else ("absent", None)
        self._current_sim = ready
        self._identity = identity
        self._phone = phone
        if context == self._context:
            return False
        self._context = context
        self._revision += 1
        self._profiles = tuple(replace(profile, active=identity is not None and profile.identity_key == identity, account_state=self._disconnected()) for profile in self._profiles)
        return True

    def _persist(self, profiles: tuple[SimProfile, ...]) -> None:
        failed = False
        try:
            self._store.save(profiles)
        except Exception as error:
            error.__traceback__ = None
            error.__context__ = None
            error.__cause__ = None
            failed = True
        if failed:
            self._storage_failed = True
            raise SimProfileStoreError() from None

    def create_profile(self, name: str, phone_number: str | None, carrier: SimCarrier) -> SimProfile:
        if not self.can_create:
            raise SimProfileValidationError()
        profile = SimProfile(str(uuid4()), name, phone_number, carrier, self._identity, True, self._disconnected())
        updated = self._profiles + (profile,)
        self._persist(updated)
        self._profiles = updated
        return profile

    def rename_profile(self, profile_id: str, name: str) -> SimProfile:
        if self._closed or self._storage_failed:
            raise SimProfileValidationError()
        profile = next((item for item in self._profiles if item.profile_id == profile_id), None)
        if profile is None:
            raise SimProfileValidationError()
        renamed = replace(profile, name=name)
        updated = tuple(renamed if item.profile_id == profile_id else item for item in self._profiles)
        self._persist(updated)
        self._profiles = updated
        return renamed

    def set_account_state(self, state: AccountState) -> None:
        profile = self.active_profile
        if self._closed or not isinstance(state, AccountState) or not isinstance(state.phase, AccountPhase) or not isinstance(state.validity, SessionValidity) or state.issue is not None and not isinstance(state.issue, AccountIssue) or type(state.otp_available) is not bool or type(state.is_demo) is not bool or state.is_demo is not self._demo or profile is None or profile.carrier is not SimCarrier.DITO:
            return
        self._profiles = tuple(replace(item, account_state=state) if item.profile_id == profile.profile_id else item for item in self._profiles)

    def close(self) -> None:
        self._closed = True
        self._profiles = ()
        self._current_sim = False
        self._identity = None
        self._phone = None
        self._context = None

    def __repr__(self) -> str:
        return "SimProfileService(<details omitted>)"

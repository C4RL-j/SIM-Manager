"""Offline SIM identity, isolation and encrypted metadata tests; all values synthetic."""

from dataclasses import FrozenInstanceError, replace
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from sim_manager.account_models import AccountPhase, AccountState, SessionValidity
from sim_manager.models import DeviceIssue, DeviceState, IssueCode, Readiness, SimState
from sim_manager.services.sim_profiles import SimProfileService
from sim_manager.sim_models import SimCarrier, SimProfile, SimProfileValidationError
from sim_manager.storage import sim_profiles as storage
from sim_manager.storage.sim_profiles import MemorySimProfileStore, SimProfileStoreError, WindowsSimProfileStore

KEY_A = "iccid-v1:" + "a" * 64
KEY_B = "iccid-v1:" + "b" * 64
PHONE = "+639000000001"
CONNECTED = AccountState(AccountPhase.CONNECTED, SessionValidity.VALIDATED)


def observed(key=KEY_A, phone=PHONE, *, ready=True, sources=("sim", "device", "deviceDetails"), errors=(), present=None):
    return DeviceState(sim=SimState(present=present, readiness=Readiness.READY if ready else Readiness.UNKNOWN, identity_key=key, phone_number=phone), successful_sources=sources, errors=errors)


def profile(*, key=KEY_A, name="Synthetic SIM", phone=PHONE, carrier=SimCarrier.DITO, active=False, account_state=AccountState()):
    return SimProfile(str(uuid4()), name, phone, carrier, key, active, account_state)


class FakeProtection:
    """Reversible test-only transform; never used by production composition."""
    def __init__(self):
        self.protected_inputs = []
        self.decrypted_outputs = []
        self.calls = []

    def protect(self, plaintext):
        self.calls.append("protect")
        self.protected_inputs.append(plaintext)
        return bytearray(b"TEST:" + bytes(char ^ 0xA5 for char in plaintext))

    def unprotect(self, encrypted):
        self.calls.append("unprotect")
        if not encrypted.startswith(b"TEST:"):
            raise RuntimeError("Synthetic private corruption")
        decoded = bytearray(char ^ 0xA5 for char in encrypted[5:])
        self.decrypted_outputs.append(decoded)
        return decoded


class ProfileModelTests(unittest.TestCase):
    def test_model_private_and_immutable(self):
        item = profile(active=True, account_state=CONNECTED)
        for representation in (repr(item), str(item)):
            for private in (item.profile_id, item.name, PHONE, KEY_A):
                self.assertNotIn(private, representation)
        with self.assertRaises(FrozenInstanceError):
            item.name = "Other"

    def test_canonical_uuid_not_phone_and_only_supported_carriers(self):
        item = profile()
        self.assertEqual(str(UUID(item.profile_id)), item.profile_id)
        self.assertNotEqual(item.profile_id, item.phone_number)
        self.assertEqual(set(SimCarrier), {SimCarrier.UNKNOWN, SimCarrier.DITO})

    def test_name_and_phone_normalized(self):
        item = profile(name="  My SIM  ", phone=" " + PHONE + " ")
        self.assertEqual(item.name, "My SIM")
        self.assertEqual(item.phone_number, PHONE)
        self.assertIsNone(profile(phone=" ").phone_number)

    def test_bad_fields_have_private_fixed_validation_errors(self):
        base = profile()
        for changes in ({"profile_id": PHONE}, {"name": ""}, {"name": "A\x00B"}, {"name": "N" * 81}, {"phone_number": "masked"}, {"phone_number": "１２３４５６７"}, {"phone_number": "1" * 16}, {"identity_key": PHONE}, {"carrier": "dito"}, {"active": 1}, {"account_state": PHONE}):
            with self.subTest(fields=tuple(changes)), self.assertRaises(SimProfileValidationError) as caught:
                replace(base, **changes)
            self.assertEqual(str(caught.exception), "SIM profile details are invalid.")
            self.assertIsNone(caught.exception.__context__)


class ProfileServiceTests(unittest.TestCase):
    def setUp(self):
        self.store = MemorySimProfileStore()
        self.service = SimProfileService(self.store)

    def create(self, key=KEY_A, phone=PHONE, carrier=SimCarrier.DITO):
        self.service.observe(observed(key, phone))
        return self.service.create_profile("Synthetic SIM", phone, carrier)

    def test_unknown_current_offers_create_and_creation_not_physical_change(self):
        self.assertFalse(self.service.current_sim)
        self.assertFalse(self.service.can_create)
        self.assertTrue(self.service.observe(observed()))
        self.assertTrue(self.service.current_sim)
        self.assertTrue(self.service.can_create)
        self.assertTrue(self.service.identity_verified)
        self.assertEqual(self.service.current_phone_number, PHONE)
        token = self.service.context_token
        item = self.service.create_profile("Synthetic SIM", PHONE, SimCarrier.DITO)
        self.assertEqual(self.service.active_profile, item)
        self.assertEqual(self.service.context_token, token)
        self.assertFalse(self.service.can_create)
        self.assertFalse(self.service.observe(observed()))

    def test_same_phone_different_verified_identity_creates_distinct_profiles(self):
        first = self.create()
        self.service.set_account_state(CONNECTED)
        self.assertTrue(self.service.observe(observed(KEY_B)))
        self.assertIsNone(self.service.active_profile)
        second = self.service.create_profile("Other SIM", PHONE, SimCarrier.DITO)
        self.assertNotEqual(first.profile_id, second.profile_id)
        self.assertEqual(len(self.service.profiles), 2)
        self.assertTrue(self.service.observe(observed(KEY_A)))
        self.assertEqual(self.service.active_profile.profile_id, first.profile_id)
        self.assertEqual(self.service.active_profile.account_state.phase, AccountPhase.DISCONNECTED)
        self.assertTrue(all(item.account_state.phase is AccountPhase.DISCONNECTED for item in self.service.profiles))

    def test_same_identity_phone_update_does_not_change_profile_or_account(self):
        item = self.create()
        self.service.set_account_state(CONNECTED)
        self.assertFalse(self.service.observe(observed(KEY_A, "+639000000002")))
        self.assertEqual(self.service.active_profile.profile_id, item.profile_id)
        self.assertEqual(self.service.active_profile.phone_number, PHONE)
        self.assertEqual(self.service.current_phone_number, "+639000000002")
        self.assertEqual(self.service.active_profile.account_state, CONNECTED)

    def test_rename_preserves_uuid_identity_binding_and_session(self):
        item = self.create()
        self.service.set_account_state(CONNECTED)
        token = self.service.context_token
        renamed = self.service.rename_profile(item.profile_id, "Second name")
        self.assertEqual(renamed.name, "Second name")
        self.assertEqual(renamed.profile_id, item.profile_id)
        self.assertEqual(renamed.identity_key, KEY_A)
        self.assertTrue(renamed.active)
        self.assertEqual(renamed.account_state, CONNECTED)
        self.assertEqual(token, self.service.context_token)

    def test_reload_starts_inactive_disconnected_then_matches_identity(self):
        item = self.create()
        self.service.set_account_state(CONNECTED)
        reloaded = SimProfileService(self.store)
        self.assertIsNone(reloaded.active_profile)
        self.assertFalse(reloaded.current_sim)
        self.assertFalse(reloaded.profiles[0].active)
        self.assertEqual(reloaded.profiles[0].account_state.phase, AccountPhase.DISCONNECTED)
        reloaded.observe(observed())
        self.assertEqual(reloaded.active_profile.profile_id, item.profile_id)
        self.assertEqual(reloaded.active_profile.account_state.phase, AccountPhase.DISCONNECTED)

    def test_unknown_does_not_match_saved_phone(self):
        self.create()
        self.assertTrue(self.service.observe(observed(None)))
        self.assertIsNone(self.service.active_profile)
        self.assertTrue(self.service.can_create)
        self.assertFalse(self.service.identity_verified)
        self.assertFalse(self.service.observe(observed(None)))

    def test_unverified_created_binding_only_continuous_context(self):
        item = self.create(None)
        self.service.set_account_state(CONNECTED)
        self.assertFalse(self.service.observe(observed(None)))
        self.assertEqual(self.service.active_profile.profile_id, item.profile_id)
        self.assertEqual(self.service.active_profile.account_state, CONNECTED)
        self.assertTrue(self.service.observe(observed(None, "+639000000002")))
        self.assertIsNone(self.service.active_profile)
        self.assertTrue(self.service.observe(observed(None)))
        self.assertIsNone(self.service.active_profile)
        reloaded = SimProfileService(self.store)
        reloaded.observe(observed(None))
        self.assertIsNone(reloaded.active_profile)

    def test_invalid_identity_never_matches(self):
        self.create()
        for key in ("a" * 64, "iccid-v1:" + "A" * 64, PHONE, 123, []):
            with self.subTest(kind=type(key).__name__):
                self.service.observe(observed(key))
                self.assertIsNone(self.service.active_profile)
                self.assertIsNone(self.service.current_identity)

    def test_status_failure_and_auth_forget_preserve_verified_account(self):
        item = self.create()
        self.service.set_account_state(CONNECTED)
        for snapshot in (DeviceState(), DeviceState(errors=(DeviceIssue("sim", IssueCode.AUTHENTICATION_REQUIRED),)), observed(KEY_B, sources=("device",), errors=(DeviceIssue("sim", IssueCode.TIMEOUT),))):
            self.assertFalse(self.service.observe(snapshot))
            self.assertEqual(self.service.active_profile.profile_id, item.profile_id)
            self.assertEqual(self.service.active_profile.account_state, CONNECTED)

    def test_successful_unknown_or_not_ready_detaches_and_resets(self):
        for snapshot in (observed(None), observed(ready=False), observed(present=False)):
            self.service = SimProfileService(self.store)
            self.service.observe(observed())
            if self.service.active_profile is None:
                self.service.create_profile("Synthetic SIM", PHONE, SimCarrier.DITO)
            self.service.set_account_state(CONNECTED)
            self.assertTrue(self.service.observe(snapshot))
            self.assertIsNone(self.service.active_profile)
            self.assertTrue(all(item.account_state.phase is AccountPhase.DISCONNECTED for item in self.service.profiles))

    def test_no_device_success_does_not_use_supplied_identity(self):
        self.service.observe(observed(sources=("sim", "deviceDetails")))
        self.assertFalse(self.service.identity_verified)
        self.assertIsNone(self.service.current_identity)

    def test_failed_device_identity_getter_and_unproven_absence_preserve_known_session(self):
        item = self.create()
        self.service.set_account_state(CONNECTED)
        for state in (observed(KEY_B, sources=("sim",)), observed(KEY_B, errors=(DeviceIssue("device", IssueCode.TIMEOUT),)), observed(present=False, sources=())):
            self.assertFalse(self.service.observe(state))
            self.assertEqual(self.service.active_profile.profile_id, item.profile_id)
            self.assertEqual(self.service.active_profile.account_state, CONNECTED)

    def test_malformed_snapshots_and_account_states_do_not_raise_or_associate(self):
        self.create()
        for snapshot in (None, DeviceState(sim=PHONE), DeviceState(successful_sources=PHONE), DeviceState(sim=SimState(), errors=(PHONE, [], DeviceIssue([], IssueCode.TIMEOUT)), successful_sources=([],))):
            self.assertFalse(self.service.observe(snapshot))
        for state in (PHONE, AccountState(phase=PHONE), AccountState(validity=PHONE), AccountState(issue=PHONE), AccountState(otp_available=1), AccountState(is_demo=1)):
            self.service.set_account_state(state)
            self.assertEqual(self.service.active_profile.account_state.phase, AccountPhase.DISCONNECTED)

    def test_account_state_ignored_for_unknown_carrier_or_no_active(self):
        self.service.set_account_state(CONNECTED)
        self.assertIsNone(self.service.active_profile)
        self.create(carrier=SimCarrier.UNKNOWN)
        self.service.set_account_state(CONNECTED)
        self.assertEqual(self.service.active_profile.account_state.phase, AccountPhase.DISCONNECTED)

    def test_validation_does_not_mutate_or_persist(self):
        self.service.observe(observed())
        for bad_name, bad_phone, bad_carrier in (("", PHONE, SimCarrier.DITO), ("SIM", "masked", SimCarrier.DITO), ("SIM", PHONE, "dito")):
            with self.assertRaises(SimProfileValidationError):
                self.service.create_profile(bad_name, bad_phone, bad_carrier)
            self.assertEqual(self.service.profiles, ())
            self.assertEqual(self.store.load(), ())
        with self.assertRaises(SimProfileValidationError):
            self.service.rename_profile(str(uuid4()), "Name")

    def test_load_failure_closed_notice_and_no_overwrite(self):
        class BrokenStore:
            def load(self): raise RuntimeError(PHONE)
            def save(self, profiles): raise AssertionError("Must not overwrite")
        service = SimProfileService(BrokenStore())
        service.observe(observed())
        self.assertFalse(service.can_create)
        self.assertEqual(service.notice, "Saved SIM profiles are unavailable.")
        self.assertEqual(service.profiles, ())

    def test_save_failure_rolls_back_and_sanitizes(self):
        class BrokenSave(MemorySimProfileStore):
            def save(self, profiles): raise RuntimeError(PHONE)
        service = SimProfileService(BrokenSave())
        service.observe(observed())
        with self.assertRaises(SimProfileStoreError) as caught:
            service.create_profile("Synthetic SIM", PHONE, SimCarrier.DITO)
        self.assertEqual(service.profiles, ())
        self.assertNotIn(PHONE, str(caught.exception))
        self.assertIsNone(caught.exception.__context__)
        self.assertIsNone(caught.exception.__cause__)

    def test_demo_and_defaults_are_memory_only_and_private(self):
        with patch.object(storage._WindowsProfileProtection, "protect", side_effect=AssertionError("Native API forbidden")), patch.object(storage._WindowsProfileProtection, "unprotect", side_effect=AssertionError("Native API forbidden")):
            demo = SimProfileService(demo=True)
            demo.observe(observed())
            item = demo.create_profile("Demo SIM", PHONE, SimCarrier.DITO)
            self.assertTrue(item.account_state.is_demo)
            independent = SimProfileService()
            self.assertEqual(independent.profiles, ())
        self.assertNotIn(PHONE, repr(demo))

    def test_demo_explicit_windows_store_rejected_before_load(self):
        store = WindowsSimProfileStore()
        with patch.object(store, "load", side_effect=AssertionError("Persistent store must not load")) as load:
            with self.assertRaisesRegex(ValueError, "Demo SIM profiles require memory storage"):
                SimProfileService(store, demo=True)
            load.assert_not_called()
        self.assertTrue(SimProfileService(demo=True).is_demo)
        self.assertFalse(SimProfileService().is_demo)

    def test_demo_live_account_states_cannot_cross_profile_boundary(self):
        self.create()
        self.service.set_account_state(replace(CONNECTED, is_demo=True))
        self.assertEqual(self.service.active_profile.account_state.phase, AccountPhase.DISCONNECTED)
        demo = SimProfileService(demo=True)
        demo.observe(observed())
        demo.create_profile("Synthetic SIM", PHONE, SimCarrier.DITO)
        demo.set_account_state(CONNECTED)
        self.assertEqual(demo.active_profile.account_state.phase, AccountPhase.DISCONNECTED)
        demo.set_account_state(replace(CONNECTED, is_demo=True))
        self.assertEqual(demo.active_profile.account_state.phase, AccountPhase.CONNECTED)

    def test_close_clears_runtime_preserves_store_and_ignores_late_observation(self):
        self.create()
        self.service.close()
        self.service.close()
        self.assertEqual(self.service.profiles, ())
        self.assertIsNone(self.service.current_phone_number)
        self.assertFalse(self.service.observe(observed()))
        self.assertEqual(len(self.store.load()), 1)


class ProfileStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "profiles.dpapi"
        self.protection = FakeProtection()
        self.store = WindowsSimProfileStore(self.path, protection=self.protection)

    def test_missing_file_does_not_invoke_native_or_protection(self):
        self.assertEqual(self.store.load(), ())
        self.assertEqual(self.protection.calls, [])

    def test_save_reload_atomic_encrypted_and_runtime_not_serialized(self):
        item = profile(active=True, account_state=CONNECTED)
        self.store.save((item,))
        content = self.path.read_bytes()
        for value in (PHONE.encode(), KEY_A.encode(), item.name.encode()):
            self.assertNotIn(value, content)
        restored = self.store.load()[0]
        self.assertEqual((restored.profile_id, restored.name, restored.phone_number, restored.identity_key), (item.profile_id, item.name, item.phone_number, item.identity_key))
        self.assertFalse(restored.active)
        self.assertEqual(restored.account_state.phase, AccountPhase.DISCONNECTED)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))
        decoded = bytes(char ^ 0xA5 for char in content[5:])
        self.assertEqual(set(json.loads(decoded)["profiles"][0]), {"profile_id", "name", "phone_number", "carrier", "identity_key"})
        self.assertTrue(all(not any(buffer) for buffer in self.protection.protected_inputs + self.protection.decrypted_outputs))

    def test_memory_store_strips_runtime_and_is_isolated(self):
        item = profile(active=True, account_state=CONNECTED)
        store = MemorySimProfileStore((item,))
        self.assertFalse(store.load()[0].active)
        self.assertEqual(store.load()[0].account_state.phase, AccountPhase.DISCONNECTED)
        self.assertEqual(MemorySimProfileStore().load(), ())
        self.assertNotIn(PHONE, repr(store))

    def test_duplicate_uuid_or_identity_and_cap_fail_closed(self):
        first = profile()
        for items in ((first, first), (first, profile()), [first], tuple(profile(key=None) for _ in range(101))):
            with self.assertRaises(SimProfileStoreError):
                self.store.save(items)
            self.assertFalse(self.path.exists())

    def test_unknown_unbound_profiles_with_same_phone_may_coexist(self):
        self.store.save((profile(key=None), profile(key=None)))
        self.assertEqual(len(self.store.load()), 2)

    def test_malformed_schema_no_private_error_context(self):
        item = profile()
        row = {"profile_id": item.profile_id, "name": item.name, "phone_number": PHONE, "carrier": "dito", "identity_key": KEY_A}
        bad_payloads = [b"not json " + PHONE.encode(), json.dumps({"version": True, "profiles": []}).encode(), json.dumps({"version": 2, "profiles": []}).encode(), json.dumps({"version": 1, "profiles": [{**row, "account_state": PHONE}]}).encode(), json.dumps({"version": 1, "profiles": [{**row, "carrier": "smart"}]}).encode(), json.dumps({"version": 1, "profiles": [{**row, "profile_id": PHONE}]}).encode(), json.dumps({"version": 1, "profiles": [{**row, "phone_number": []}]}).encode(), json.dumps({"version": 1, "profiles": [row, row]}).encode()]
        for payload in bad_payloads:
            self.path.write_bytes(self.protection.protect(bytearray(payload)))
            with self.assertRaises(SimProfileStoreError) as caught:
                self.store.load()
            self.assertNotIn(PHONE, str(caught.exception))
            self.assertIsNone(caught.exception.__context__)
            self.assertIsNone(caught.exception.__cause__)

    def test_empty_and_oversized_encrypted_file_rejected_before_decrypt(self):
        for payload in (b"", b"X" * (storage.MAX_FILE_BYTES + 1)):
            self.path.write_bytes(payload)
            with self.assertRaises(SimProfileStoreError):
                self.store.load()
        self.assertNotIn("unprotect", self.protection.calls)

    def test_failed_replace_preserves_previous_file_removes_temp(self):
        first = profile()
        self.store.save((first,))
        before = self.path.read_bytes()
        with patch.object(storage.os, "replace", side_effect=OSError(PHONE)):
            with self.assertRaises(SimProfileStoreError) as caught:
                self.store.save((replace(first, name="Changed"),))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list(self.path.parent.glob("*.tmp")))
        self.assertIsNone(caught.exception.__context__)

    def test_protection_bad_results_and_exceptions_fail_closed(self):
        for result in (b"not owned", None, bytearray(), bytearray(b"X" * (storage.MAX_FILE_BYTES + 1))):
            with patch.object(self.protection, "protect", return_value=result), self.assertRaises(SimProfileStoreError):
                self.store.save((profile(),))
        self.path.write_bytes(b"TEST:X")
        for result in ("private text", None, bytearray(b"X" * (storage.MAX_PLAIN_BYTES + 1))):
            with patch.object(self.protection, "unprotect", return_value=result), self.assertRaises(SimProfileStoreError):
                self.store.load()
        with patch.object(self.protection, "unprotect", side_effect=RuntimeError(PHONE)):
            with self.assertRaises(SimProfileStoreError) as caught:
                self.store.load()
        self.assertNotIn(PHONE, str(caught.exception))
        self.assertIsNone(caught.exception.__context__)

    def test_default_location_outside_repo_lazy_and_private_repr(self):
        with patch.object(storage.ctypes, "WinDLL", side_effect=AssertionError("No native library at import"), create=True):
            specification = importlib.util.spec_from_file_location("synthetic_profile_storage_import", storage.__file__)
            module = importlib.util.module_from_spec(specification)
            specification.loader.exec_module(module)
            lazy = module.WindowsSimProfileStore()
        with patch.dict(os.environ, {"LOCALAPPDATA": self.temporary.name}):
            self.assertEqual(lazy._location(), Path(self.temporary.name) / "SIM Manager" / "sim-profiles.dpapi")
        self.assertNotIn(self.temporary.name, repr(self.store))

    def test_native_non_windows_fail_closed(self):
        with patch.object(storage.os, "name", "posix"):
            with self.assertRaises(storage.SimProfileStoreError) as caught:
                storage._WindowsProfileProtection().protect(bytearray(b"synthetic"))
        self.assertIsNone(caught.exception.__context__)

    def test_native_bridge_flags_entropy_output_free_and_wipe(self):
        allocations = []
        calls = []
        class Function:
            def __init__(self, callback): self.callback = callback
            def __call__(self, *args): return self.callback(*args)
        def operation(input_pointer, description, entropy_pointer, reserved, prompt, flags, output_pointer):
            input_blob = ctypes.cast(input_pointer, ctypes.POINTER(storage._DataBlob)).contents
            entropy_blob = ctypes.cast(entropy_pointer, ctypes.POINTER(storage._DataBlob)).contents
            calls.append((description, reserved, prompt, flags, ctypes.string_at(entropy_blob.pbData, entropy_blob.cbData)))
            output_bytes = b"native synthetic output"
            output_buffer = (ctypes.c_ubyte * len(output_bytes)).from_buffer_copy(output_bytes)
            allocations.append(output_buffer)
            output = ctypes.cast(output_pointer, ctypes.POINTER(storage._DataBlob)).contents
            output.cbData = len(output_bytes)
            output.pbData = output_buffer
            return 1
        freed = []
        def free(pointer):
            freed.append(not any(allocations[-1]))
            return None
        crypt = type("Crypt", (), {"CryptProtectData": Function(operation), "CryptUnprotectData": Function(operation)})()
        kernel = type("Kernel", (), {"LocalFree": Function(free)})()
        with patch.object(storage.os, "name", "nt"), patch.object(storage.ctypes, "WinDLL", side_effect=[crypt, kernel, crypt, kernel], create=True):
            protection = storage._WindowsProfileProtection()
            self.assertEqual(protection.protect(bytearray(b"synthetic")), bytearray(b"native synthetic output"))
            self.assertEqual(protection.unprotect(bytearray(b"synthetic")), bytearray(b"native synthetic output"))
        self.assertEqual(freed, [True, True])
        self.assertTrue(all(call[:4] == (None, None, None, 1) and call[4] == storage._ENTROPY for call in calls))
        self.assertEqual(storage._DataBlob._fields_[0][1], ctypes.c_uint32)


if __name__ == "__main__":
    unittest.main()

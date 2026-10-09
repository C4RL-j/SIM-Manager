"""Offline remembered-D2 login proof, privacy and revocation boundaries."""

from queue import Queue
from threading import Event, Thread
from time import perf_counter
import traceback
import unittest
from unittest.mock import patch

from sim_manager.models import DeviceState
from sim_manager.services.device import AuthenticationError, AuthenticationFailure
from sim_manager.services.router_login import D2LoginService, LoginStorageIssue
from sim_manager.storage.windows_credentials import RememberedD2Login


USERNAME = "SyntheticAdminA2"
PASSWORD = "SYNTHETIC_PASSWORD_NOT_REAL"
RAW_DETAIL = "SYNTHETIC_PRIVATE_EXCEPTION_DETAIL"
WAIT = 3.0


class FakeStore:
    def __init__(self, record=None):
        self.record = record
        self.calls = []
        self.load_error = self.save_error = self.delete_error = None

    def load(self):
        self.calls.append("load")
        if self.load_error is not None:
            raise self.load_error
        return self.record

    def save(self, username, password):
        self.calls.append("save")
        if self.save_error is not None:
            raise self.save_error
        self.record = RememberedD2Login(username, password)

    def delete(self):
        self.calls.append("delete")
        if self.delete_error is not None:
            raise self.delete_error
        self.record = None


class FakeProvider:
    is_demo = False
    router_address = "https://192.168.1.1"

    def __init__(self):
        self.state = DeviceState()
        self.authenticated = False
        self.proof = True
        self.auth_error = self.proof_error = None
        self.auth_calls = []
        self.refresh_calls = []
        self.invalidations = self.close_calls = 0
        self.on_authenticate = None

    def authenticate(self, password, *, username, stop_event=None):
        self.auth_calls.append((username, password, stop_event))
        if self.on_authenticate is not None:
            self.on_authenticate()
        if self.auth_error is not None:
            raise self.auth_error
        self.authenticated = True
        return self.state

    def is_authenticated(self):
        if self.proof_error is not None:
            raise self.proof_error
        return self.proof if self.authenticated else False

    def get_device_state(self, *, stop_event=None):
        self.refresh_calls.append(stop_event)
        return self.state

    def invalidate_session(self):
        self.invalidations += 1
        self.authenticated = False

    def close(self):
        self.close_calls += 1
        self.authenticated = False


class D2LoginServiceTests(unittest.TestCase):
    def setUp(self):
        # Every store and provider below is synthetic. Fail if a regression
        # tries to instantiate a socket or load the native credential API.
        self.network_guard = patch("socket.socket", side_effect=AssertionError("Offline only"))
        self.vault_guard = patch(
            "sim_manager.storage.windows_credentials._WindowsCredentialBackend._get_api",
            side_effect=AssertionError("Synthetic store only"),
        )
        self.network_guard.start()
        self.vault_guard.start()
        self.addCleanup(self.network_guard.stop)
        self.addCleanup(self.vault_guard.stop)
        self.provider = FakeProvider()
        self.store = FakeStore()
        self.service = D2LoginService(self.provider, self.store)

    def assert_safe_error(self, action, code):
        try:
            action()
        except AuthenticationError as error:
            self.assertIs(error.code, code)
            rendered = "".join(traceback.format_exception(error))
            for private in (USERNAME, PASSWORD, RAW_DETAIL):
                self.assertNotIn(private, str(error))
                self.assertNotIn(private, repr(error))
                self.assertNotIn(private, rendered)
            self.assertIsNone(error.__cause__)
            self.assertIsNone(error.__context__)
        else:
            self.fail("Expected a closed authentication outcome")

    def authenticate(self, *, remember=True, stop=None):
        return self.service.authenticate(
            PASSWORD, username=USERNAME, remember=remember, stop_event=stop,
        )

    def start_call(self, action):
        output = Queue(maxsize=1)

        def run():
            try:
                output.put(("value", action()))
            except BaseException as error:
                # Never let a worker print a traceback, even on a test failure.
                output.put(("error", error))

        worker = Thread(target=run, daemon=True)
        worker.start()
        return worker, output

    def finish_call(self, worker, output):
        worker.join(WAIT)
        self.assertFalse(worker.is_alive(), "Synthetic worker did not stop")
        return output.get_nowait()

    def block_authentication(self):
        entered, release = Event(), Event()

        def block():
            entered.set()
            if not release.wait(WAIT):
                raise RuntimeError("Synthetic authentication barrier timed out")

        self.provider.on_authenticate = block
        self.addCleanup(release.set)
        return entered, release

    def test_success_saves_exact_alphanumeric_username_and_loads_record(self):
        state = self.authenticate()
        self.assertIs(state, self.provider.state)
        self.assertEqual(self.store.calls, ["save"])
        self.assertTrue(self.service.saved_login_available)
        self.assertIsNone(self.service.storage_issue)
        record = self.service.load_remembered_login()
        self.assertIsInstance(record, RememberedD2Login)
        self.assertEqual((record.username, record.password), (USERNAME, PASSWORD))
        self.assertEqual(self.provider.auth_calls[0][:2], (USERNAME, PASSWORD))
        self.assertEqual(self.service.router_address, self.provider.router_address)
        self.assertNotIn(PASSWORD, repr(self.service))
        self.assertNotIn(USERNAME, repr(self.service))

    def test_load_is_fresh_and_does_not_cache_credentials(self):
        self.store.record = RememberedD2Login(USERNAME, PASSWORD)
        first = self.service.load_remembered_login()
        self.store.record = RememberedD2Login("AnotherSyntheticAdminB3", "ANOTHER_SYNTHETIC_PASSWORD")
        second = self.service.load_remembered_login()
        self.assertIsNot(first, second)
        self.assertIs(second, self.store.record)
        self.assertEqual(self.store.calls, ["load", "load"])
        self.assertEqual(self.provider.auth_calls, [])

    def test_missing_record_does_not_attempt_authentication(self):
        self.assertIsNone(self.service.load_remembered_login())
        self.assertFalse(self.service.saved_login_available)
        self.assertIsNone(self.service.storage_issue)
        self.assertEqual(self.provider.auth_calls, [])

    def test_automatic_login_preserves_existing_store_without_writes(self):
        self.store.record = RememberedD2Login(USERNAME, PASSWORD)
        self.service.load_remembered_login()
        self.assertIs(self.authenticate(remember=None), self.provider.state)
        self.assertEqual(self.store.calls, ["load"])
        self.assertTrue(self.service.saved_login_available)

    def test_successful_unchecked_remember_deletes_existing_record(self):
        self.store.record = RememberedD2Login(USERNAME, PASSWORD)
        self.service.load_remembered_login()
        self.authenticate(remember=False)
        self.assertEqual(self.store.calls, ["load", "delete"])
        self.assertIsNone(self.store.record)
        self.assertFalse(self.service.saved_login_available)
        self.assertIsNone(self.service.load_remembered_login())
        self.assertEqual(self.store.calls, ["load", "delete"])

    def test_failed_unchecked_login_preserves_existing_record(self):
        previous = RememberedD2Login(USERNAME, PASSWORD)
        self.store.record = previous
        self.provider.auth_error = AuthenticationError(AuthenticationFailure.REJECTED)
        self.assert_safe_error(lambda: self.authenticate(remember=False), AuthenticationFailure.REJECTED)
        self.assertIs(self.store.record, previous)
        self.assertEqual(self.store.calls, [])

    def test_partial_status_can_save_when_session_login_is_verified(self):
        self.provider.state = DeviceState(partial=True)
        self.assertIs(self.authenticate(), self.provider.state)
        self.assertEqual(self.store.calls, ["save"])

    def test_snapshot_without_strict_session_proof_cannot_save_or_delete(self):
        for proof in (False, None, 1, "authenticated"):
            for remember in (True, False, None):
                with self.subTest(proof=proof, remember=remember):
                    self.provider.proof = proof
                    self.assert_safe_error(
                        lambda: self.authenticate(remember=remember), AuthenticationFailure.REJECTED,
                    )
        self.assertEqual(self.store.calls, [])

    def test_non_snapshot_return_cannot_authorize_saved_credentials(self):
        self.provider.state = {"synthetic": "untrusted"}
        self.assert_safe_error(self.authenticate, AuthenticationFailure.MALFORMED)
        self.assertEqual(self.store.calls, [])

    def test_closed_authentication_failures_preserve_codes_without_saving(self):
        for code in AuthenticationFailure:
            with self.subTest(code=code):
                self.provider.auth_error = AuthenticationError(code)
                self.assert_safe_error(self.authenticate, code)
        self.assertEqual(self.store.calls, [])

    def test_raw_provider_failure_is_sanitized_without_private_context(self):
        self.provider.auth_error = RuntimeError(RAW_DETAIL)
        self.assert_safe_error(self.authenticate, AuthenticationFailure.MALFORMED)
        self.assertEqual(self.store.calls, [])

    def test_raw_session_proof_failure_is_sanitized_without_private_context(self):
        self.provider.proof_error = RuntimeError(RAW_DETAIL)
        self.assert_safe_error(self.authenticate, AuthenticationFailure.MALFORMED)
        self.assertEqual(self.store.calls, [])

    def test_cancelled_before_authentication_never_saves(self):
        stop = Event()
        stop.set()
        self.assert_safe_error(lambda: self.authenticate(stop=stop), AuthenticationFailure.CANCELLED)
        self.assertEqual(self.provider.auth_calls, [])
        self.assertEqual(self.store.calls, [])

    def test_cancellation_at_provider_completion_invalidates_and_never_saves(self):
        stop = Event()
        self.provider.on_authenticate = stop.set
        self.assert_safe_error(lambda: self.authenticate(stop=stop), AuthenticationFailure.CANCELLED)
        self.assertFalse(self.provider.authenticated)
        self.assertGreaterEqual(self.provider.invalidations, 1)
        self.assertEqual(self.store.calls, [])

    def test_invalid_and_failed_loads_expose_only_closed_storage_issue(self):
        invalid = (object(), RememberedD2Login("", PASSWORD), RememberedD2Login(USERNAME, ""), RememberedD2Login(None, PASSWORD))
        for record in invalid:
            with self.subTest(kind=type(record).__name__):
                self.store.record = record
                self.assertIsNone(self.service.load_remembered_login())
                self.assertIs(self.service.storage_issue, LoginStorageIssue.LOAD)
        self.store.load_error = RuntimeError(RAW_DETAIL)
        self.assertIsNone(self.service.load_remembered_login())
        self.assertIs(self.service.storage_issue, LoginStorageIssue.LOAD)
        self.assertNotIn(RAW_DETAIL, repr(self.service))
        self.assertEqual(self.provider.auth_calls, [])

    def test_failed_save_keeps_verified_session_and_safe_snapshot(self):
        self.store.save_error = RuntimeError(RAW_DETAIL)
        self.assertIs(self.authenticate(), self.provider.state)
        self.assertTrue(self.provider.authenticated)
        self.assertIs(self.service.storage_issue, LoginStorageIssue.SAVE)
        self.assertFalse(self.service.saved_login_available)
        self.assertNotIn(RAW_DETAIL, repr(self.service))
        self.assertIsNone(self.store.record)

    def test_failed_unchecked_delete_keeps_snapshot_and_reports_closed_issue(self):
        previous = RememberedD2Login(USERNAME, PASSWORD)
        self.store.record = previous
        self.service.load_remembered_login()
        self.store.delete_error = RuntimeError(RAW_DETAIL)
        self.assertIs(self.authenticate(remember=False), self.provider.state)
        self.assertIs(self.service.storage_issue, LoginStorageIssue.DELETE)
        self.assertIs(self.store.record, previous)
        self.assertTrue(self.provider.authenticated)

    def test_forget_deletes_clears_autofill_and_invalidates_reusable_session(self):
        self.authenticate()
        self.assertTrue(self.service.forget_saved_login())
        self.assertFalse(self.provider.authenticated)
        self.assertIsNone(self.store.record)
        self.assertFalse(self.service.saved_login_available)
        self.assertIsNone(self.service.load_remembered_login())
        self.assertEqual(self.store.calls, ["save", "delete"])
        self.assertEqual(self.provider.close_calls, 0)
        # Forget keeps explicit sign-in available, without restoring old autofill.
        self.authenticate()
        self.assertIsNotNone(self.service.load_remembered_login())

    def test_failed_forget_still_disables_autofill_and_invalidates_session(self):
        self.authenticate()
        self.store.delete_error = RuntimeError(RAW_DETAIL)
        self.assertFalse(self.service.forget_saved_login())
        self.assertIs(self.service.storage_issue, LoginStorageIssue.DELETE)
        self.assertFalse(self.provider.authenticated)
        self.assertIsNone(self.service.load_remembered_login())
        self.assertEqual(self.store.calls, ["save", "delete"])

    def test_forget_during_blocked_login_prevents_late_save_and_session_restore(self):
        entered, release = self.block_authentication()
        worker, output = self.start_call(self.authenticate)
        try:
            self.assertTrue(entered.wait(WAIT))
            self.assertTrue(self.service.forget_saved_login())
        finally:
            release.set()
        kind, result = self.finish_call(worker, output)
        self.assertEqual(kind, "error")
        self.assertIsInstance(result, AuthenticationError)
        self.assertIs(result.code, AuthenticationFailure.CANCELLED)
        self.assertEqual(self.store.calls, ["delete"])
        self.assertIsNone(self.store.record)
        self.assertFalse(self.provider.authenticated)
        self.assertIsNone(self.service.load_remembered_login())

    def test_completed_unconsumed_login_result_cannot_restore_forgotten_record(self):
        worker, output = self.start_call(self.authenticate)
        worker.join(WAIT)
        self.assertFalse(worker.is_alive())
        self.assertTrue(self.service.forget_saved_login())
        kind, result = output.get_nowait()
        self.assertEqual(kind, "value")
        self.assertIs(result, self.provider.state)
        self.assertIsNone(self.store.record)
        self.assertFalse(self.provider.authenticated)
        self.assertIsNone(self.service.load_remembered_login())

    def test_forget_serializes_after_started_save_and_wins_final_storage_state(self):
        save_entered, release_save, delete_entered = Event(), Event(), Event()
        forget_revoked = Event()
        original_save, original_delete = self.store.save, self.store.delete
        original_invalidate = self.provider.invalidate_session

        def save(username, password):
            save_entered.set()
            if not release_save.wait(WAIT):
                raise RuntimeError("Synthetic save barrier timed out")
            original_save(username, password)

        def delete():
            delete_entered.set()
            original_delete()

        def invalidate():
            original_invalidate()
            forget_revoked.set()

        self.store.save, self.store.delete = save, delete
        self.provider.invalidate_session = invalidate
        self.addCleanup(release_save.set)
        auth_worker, auth_output = self.start_call(self.authenticate)
        self.assertTrue(save_entered.wait(WAIT))
        forget_worker, forget_output = self.start_call(self.service.forget_saved_login)
        try:
            self.assertTrue(forget_revoked.wait(WAIT))
            self.assertFalse(delete_entered.wait(0.1), "Forget raced an unfinished store write")
        finally:
            release_save.set()
        kind, result = self.finish_call(auth_worker, auth_output)
        self.assertEqual(kind, "error")
        self.assertIsInstance(result, AuthenticationError)
        self.assertIs(result.code, AuthenticationFailure.CANCELLED)
        self.assertEqual(self.finish_call(forget_worker, forget_output), ("value", True))
        # The stale write rollback and Forget both delete idempotently.
        self.assertEqual(self.store.calls[0], "save")
        self.assertEqual(self.store.calls.count("save"), 1)
        self.assertGreaterEqual(self.store.calls.count("delete"), 1)
        self.assertIsNone(self.store.record)
        self.assertFalse(self.service.saved_login_available)
        self.assertFalse(self.provider.authenticated)

    def test_cancellation_while_save_completes_removes_new_record(self):
        stop, save_entered, release_save = Event(), Event(), Event()
        original_save = self.store.save

        def save(username, password):
            save_entered.set()
            if not release_save.wait(WAIT):
                raise RuntimeError("Synthetic save barrier timed out")
            original_save(username, password)

        self.store.save = save
        self.addCleanup(release_save.set)
        worker, output = self.start_call(lambda: self.authenticate(stop=stop))
        try:
            self.assertTrue(save_entered.wait(WAIT))
            stop.set()
        finally:
            release_save.set()
        kind, result = self.finish_call(worker, output)
        self.assertEqual(kind, "error")
        self.assertIsInstance(result, AuthenticationError)
        self.assertIs(result.code, AuthenticationFailure.CANCELLED)
        self.assertEqual(self.store.calls, ["save", "delete"])
        self.assertIsNone(self.store.record)
        self.assertFalse(self.service.saved_login_available)
        self.assertFalse(self.provider.authenticated)

    def test_close_during_blocked_login_revokes_late_result_and_calls_close_once(self):
        entered, release = self.block_authentication()
        worker, output = self.start_call(self.authenticate)
        try:
            self.assertTrue(entered.wait(WAIT))
            self.service.close()
            self.service.close()
        finally:
            release.set()
        kind, result = self.finish_call(worker, output)
        self.assertEqual(kind, "error")
        self.assertIsInstance(result, AuthenticationError)
        self.assertIs(result.code, AuthenticationFailure.CANCELLED)
        self.assertEqual(self.provider.close_calls, 1)
        self.assertFalse(self.provider.authenticated)
        self.assertEqual(self.store.calls, [])

    def test_close_during_blocked_save_returns_promptly_and_rolls_back_stale_write(self):
        save_entered, release_save = Event(), Event()
        original_save = self.store.save

        def save(username, password):
            save_entered.set()
            if not release_save.wait(WAIT):
                raise RuntimeError("Synthetic save barrier timed out")
            original_save(username, password)

        def close():
            started = perf_counter()
            self.service.close()
            return perf_counter() - started

        self.store.save = save
        self.addCleanup(release_save.set)
        auth_worker, auth_output = self.start_call(self.authenticate)
        self.assertTrue(save_entered.wait(WAIT))
        close_worker, close_output = self.start_call(close)
        try:
            close_worker.join(0.5)
            closed_promptly = not close_worker.is_alive()
        finally:
            # Release the synthetic native call even when a locking regression
            # blocks close, so the test itself always terminates.
            release_save.set()
        close_kind, elapsed = self.finish_call(close_worker, close_output)
        kind, result = self.finish_call(auth_worker, auth_output)
        self.assertTrue(closed_promptly, "Close waited for an unfinished credential write")
        self.assertEqual(close_kind, "value")
        self.assertLess(elapsed, 0.5)
        self.assertEqual(kind, "error")
        self.assertIsInstance(result, AuthenticationError)
        self.assertIs(result.code, AuthenticationFailure.CANCELLED)
        self.assertEqual(self.provider.close_calls, 1)
        self.assertEqual(self.store.calls, ["save", "delete"])
        self.assertIsNone(self.store.record)
        self.assertFalse(self.service.saved_login_available)
        self.assertFalse(self.provider.authenticated)
        self.assertIsNone(self.service.load_remembered_login())

    def test_closed_service_does_not_load_or_attempt_login(self):
        self.service.close()
        self.assertIsNone(self.service.load_remembered_login())
        self.assert_safe_error(self.authenticate, AuthenticationFailure.CANCELLED)
        self.assertEqual(self.store.calls, [])
        self.assertEqual(self.provider.auth_calls, [])

    def test_refresh_passes_through_without_credentials_or_storage_access(self):
        stop = Event()
        self.assertIs(self.service.get_device_state(stop_event=stop), self.provider.state)
        self.assertEqual(self.provider.refresh_calls, [stop])
        self.assertEqual(self.provider.auth_calls, [])
        self.assertEqual(self.store.calls, [])

    def test_demo_provider_cannot_enable_remembered_login(self):
        self.provider.is_demo = True
        with self.assertRaises(ValueError):
            D2LoginService(self.provider, self.store)
        self.assertEqual(self.store.calls, [])
        self.assertEqual(self.provider.auth_calls, [])


if __name__ == "__main__":
    unittest.main()

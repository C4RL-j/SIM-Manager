"""Offline D2 saved-login composition; no Windows vault, network or browser."""

from contextlib import redirect_stderr, redirect_stdout
import io
import threading
import time
from unittest.mock import patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit

from sim_manager import app
from sim_manager.account_models import AccountPhase, AccountState, SessionValidity
from sim_manager.models import DeviceIssue, DeviceState, IssueCode
from sim_manager.services.device import AuthenticationError, AuthenticationFailure
from sim_manager.services.router_login import D2LoginService, LoginStorageIssue
from sim_manager.storage.windows_credentials import RememberedD2Login
from sim_manager.ui.main_window import MainWindow

from test_desktop import DesktopCase, active_dito_profiles, known_snapshot


USERNAME = "SyntheticD2Admin7"
PASSWORD = "SYNTHETIC_D2_REMEMBER_PASSWORD"
PRIVATE = "SYNTHETIC_PRIVATE_STORAGE_ERROR"


def authentication_required():
    return DeviceState(errors=(DeviceIssue("wireless", IssueCode.AUTHENTICATION_REQUIRED),))


class FakeStore:
    def __init__(self, record=None, *, load_error=None, save_error=None, delete_error=None):
        self.record = record
        self.load_error = load_error
        self.save_error = save_error
        self.delete_error = delete_error
        self.loads = self.saves = self.deletes = 0
        self.save_threads = []

    def load(self):
        self.loads += 1
        if self.load_error is not None:
            raise self.load_error
        return self.record

    def save(self, username, password):
        self.saves += 1
        self.save_threads.append(threading.get_ident())
        if self.save_error is not None:
            raise self.save_error
        self.record = RememberedD2Login(username, password)

    def delete(self):
        self.deletes += 1
        if self.delete_error is not None:
            raise self.delete_error
        self.record = None


class FakeD2Provider:
    is_demo = False
    router_address = "https://192.168.1.1"

    def __init__(self, *, error=None, blocked=False, cooperative=True, proof=True):
        self.error = error
        self.blocked = blocked
        self.cooperative = cooperative
        self.proof = proof
        self.authenticated = False
        self.snapshot = known_snapshot()
        self.auth_calls = []
        self.read_calls = []
        self.credentials_match = []
        self.invalidations = self.closes = 0
        self.started = threading.Event()
        self.finished = threading.Event()
        self.release = threading.Event()

    def authenticate(self, password, *, username, stop_event=None):
        self.auth_calls.append((threading.get_ident(), stop_event))
        self.credentials_match.append((username == USERNAME, password == PASSWORD))
        self.started.set()
        try:
            deadline = time.monotonic() + 2.5
            while self.blocked and not self.release.is_set():
                if self.cooperative and stop_event is not None and stop_event.is_set():
                    raise AuthenticationError(AuthenticationFailure.CANCELLED)
                if time.monotonic() >= deadline:
                    raise AuthenticationError(AuthenticationFailure.TIMEOUT)
                self.release.wait(0.005)
            if self.error is not None:
                raise self.error
            self.authenticated = self.proof
            return self.snapshot
        finally:
            self.finished.set()

    def get_device_state(self, *, stop_event=None):
        self.read_calls.append(threading.get_ident())
        return self.snapshot if self.authenticated is True else authentication_required()

    def is_authenticated(self):
        return self.authenticated

    def invalidate_session(self):
        self.invalidations += 1
        self.authenticated = False

    def close(self):
        self.closes += 1
        self.invalidate_session()


class BlockingSaveStore(FakeStore):
    """A bounded synthetic native-write gate, released after GUI shutdown."""

    def __init__(self):
        super().__init__()
        self.save_started = threading.Event()
        self.save_release = threading.Event()

    def save(self, username, password):
        self.saves += 1
        self.save_threads.append(threading.get_ident())
        self.save_started.set()
        if not self.save_release.wait(3.0):
            raise RuntimeError("Synthetic credential-write gate timed out")
        self.record = RememberedD2Login(username, password)


class StaticAccountService:
    """An unrelated synthetic DITO session, without any browser capability."""

    is_demo = False

    def __init__(self):
        self.state = AccountState(phase=AccountPhase.CONNECTED, validity=SessionValidity.VALIDATED)
        self.listener = None
        self.connections = self.disconnections = self.cancellations = self.shutdowns = 0

    def set_listener(self, listener):
        self.listener = listener
        if listener is not None:
            listener(self.state)

    def connect(self):
        self.connections += 1
        return False

    def disconnect(self):
        self.disconnections += 1

    def cancel(self):
        self.cancellations += 1

    def shutdown(self):
        self.shutdowns += 1

    def offer_otp(self, inbox):
        pass

    def otp_for_copy(self):
        return None


class RememberedD2LoginTests(DesktopCase):
    def setup_login(self, *, store=None, provider=None, account=None):
        store = FakeStore() if store is None else store
        provider = FakeD2Provider() if provider is None else provider
        self.providers.append(provider)
        service = D2LoginService(provider, store)
        profiles = None
        if account is not None:
            profiles, provider.snapshot = active_dito_profiles()
        window = MainWindow(service, router_login_service=service, account_service=account,
                            sim_profiles=profiles)
        self.windows.append(window)
        window.show()
        if account is not None and account.listener is not None:
            # Publish the synthetic existing session after the window has bound
            # its listener to this explicitly observed active DITO profile.
            account.listener(account.state)
        return window, service, provider, store

    def startup(self, window):
        self.assertTrue(window.start_initial_load())
        self.wait_until(lambda: not window.refresh_controller.busy)

    def manual_dialog(self, window):
        window.render_snapshot(authentication_required())
        self.assertTrue(window.open_sign_in())
        return window._sign_in_dialog

    def submit_manual(self, window, *, remember=True):
        dialog = self.manual_dialog(window)
        dialog.username_input.setText(USERNAME)
        dialog.password_input.setText(PASSWORD)
        dialog.remember_checkbox.setChecked(remember)
        dialog.accept()
        self.assertEqual(dialog.username_input.text(), "")
        self.assertEqual(dialog.password_input.text(), "")
        return dialog

    def test_saved_startup_authenticates_once_off_thread_without_rewriting_store(self):
        store = FakeStore(RememberedD2Login(USERNAME, PASSWORD))
        window, service, provider, store = self.setup_login(store=store)
        self.startup(window)
        self.assertEqual(len(provider.auth_calls), 1)
        self.assertNotEqual(provider.auth_calls[0][0], threading.get_ident())
        self.assertEqual(provider.credentials_match, [(True, True)])
        self.assertEqual(provider.read_calls, [])
        self.assertEqual((store.loads, store.saves, store.deletes), (1, 0, 0))
        self.assertTrue(window.live_label.isVisible())
        self.assertIsNone(window._sign_in_dialog)
        self.assertTrue(service.saved_login_available)
        self.assertFalse(window.start_initial_load())
        self.assertFalse(window.start_initial_load())
        QTest.qWait(80)
        self.assertEqual(len(provider.auth_calls), 1)
        window.navigation.setCurrentRow(4)
        self.assertTrue(window.settings_page.forget_login_button.isVisible())

    def test_failed_saved_startup_opens_masked_prefilled_manual_dialog_without_loop(self):
        store = FakeStore(RememberedD2Login(USERNAME, PASSWORD))
        provider = FakeD2Provider(error=AuthenticationError(AuthenticationFailure.REJECTED))
        window, _, provider, store = self.setup_login(store=store, provider=provider)
        self.startup(window)
        self.wait_until(lambda: window._sign_in_dialog is not None)
        dialog = window._sign_in_dialog
        self.assertEqual(dialog.username_input.text(), USERNAME)
        self.assertEqual(dialog.password_input.text(), PASSWORD)
        self.assertEqual(dialog.password_input.echoMode(), QLineEdit.EchoMode.Password)
        self.assertTrue(dialog.remember_checkbox.isChecked())
        self.assertEqual(window.status_label.text(), "Authentication rejected")
        self.assertFalse(window.live_label.isVisible())
        self.assertEqual((store.loads, store.saves, store.deletes), (2, 0, 0))
        self.assertFalse(window.start_initial_load())
        QTest.qWait(100)
        self.assertEqual(len(provider.auth_calls), 1)

    def test_without_saved_login_startup_reads_once_and_waits_for_explicit_sign_in(self):
        window, _, provider, store = self.setup_login()
        self.startup(window)
        self.assertEqual(provider.auth_calls, [])
        self.assertEqual(len(provider.read_calls), 1)
        self.assertEqual(store.loads, 1)
        self.assertIsNone(window._sign_in_dialog)
        self.assertTrue(window.sign_in_button.isVisible())
        self.assertFalse(window.start_initial_load())

    def test_manual_remember_saves_only_after_successful_session_proof(self):
        provider = FakeD2Provider(blocked=True)
        window, service, provider, store = self.setup_login(provider=provider)
        self.submit_manual(window)
        self.wait_until(provider.started.is_set)
        self.assertEqual(store.saves, 0)
        self.assertIsNone(store.record)
        provider.release.set()
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(store.saves, 1)
        self.assertEqual(store.deletes, 0)
        self.assertNotEqual(store.save_threads[0], threading.get_ident())
        self.assertEqual((store.record.username == USERNAME, store.record.password == PASSWORD), (True, True))
        self.assertTrue(service.saved_login_available)
        self.assertTrue(window.live_label.isVisible())

    def test_manual_failure_never_saves_or_automatically_reopens_dialog(self):
        provider = FakeD2Provider(error=AuthenticationError(AuthenticationFailure.REJECTED))
        window, _, provider, store = self.setup_login(provider=provider)
        self.submit_manual(window)
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(store.saves, 0)
        self.assertIsNone(store.record)
        self.assertEqual(window.status_label.text(), "Authentication rejected")
        self.assertIsNone(window._sign_in_dialog)
        QTest.qWait(80)
        self.assertEqual(len(provider.auth_calls), 1)
        dialog = self.manual_dialog(window)
        self.assertEqual(dialog.password_input.text(), "")
        self.assertFalse(dialog.remember_checkbox.isChecked())

    def test_unchecking_saved_login_deletes_it_only_after_successful_manual_login(self):
        store = FakeStore(RememberedD2Login(USERNAME, PASSWORD))
        provider = FakeD2Provider(error=AuthenticationError(AuthenticationFailure.REJECTED))
        window, service, provider, store = self.setup_login(store=store, provider=provider)
        self.startup(window)
        self.wait_until(lambda: window._sign_in_dialog is not None)
        dialog = window._sign_in_dialog
        dialog.remember_checkbox.setChecked(False)
        provider.error = None
        dialog.accept()
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual((store.saves, store.deletes), (0, 1))
        self.assertIsNone(store.record)
        self.assertFalse(service.saved_login_available)
        self.assertTrue(window.live_label.isVisible())

    def test_snapshot_without_exact_true_session_proof_is_not_live_or_saved(self):
        provider = FakeD2Provider(proof=1)
        window, _, _, store = self.setup_login(provider=provider)
        self.submit_manual(window)
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(store.saves, 0)
        self.assertEqual(window.status_label.text(), "Authentication rejected")
        self.assertFalse(window.live_label.isVisible())

    def test_settings_forget_removes_saved_login_and_session_without_touching_dito(self):
        store = FakeStore(RememberedD2Login(USERNAME, PASSWORD))
        account = StaticAccountService()
        window, service, provider, store = self.setup_login(store=store, account=account)
        self.startup(window)
        active_id = window.sim_profiles.active_profile.profile_id
        self.assertEqual(window.sim_profiles.active_profile.account_state.phase, AccountPhase.CONNECTED)
        window.navigation.setCurrentRow(4)
        window.settings_page.forget_login_button.click()
        self.assertEqual(store.deletes, 1)
        self.assertIsNone(store.record)
        self.assertFalse(service.saved_login_available)
        self.assertFalse(provider.authenticated)
        self.assertFalse(window.live_label.isVisible())
        self.assertEqual(window.status_label.text(), "Authentication required")
        self.assertTrue(window.settings_page.forget_login_button.isHidden())
        self.assertEqual(account.state.phase, AccountPhase.CONNECTED)
        self.assertEqual(window.sims_page.account_controls.status_label.text(), "Connected")
        self.assertEqual(window.sim_profiles.active_profile.profile_id, active_id)
        self.assertEqual(window.sim_profiles.active_profile.account_state.phase, AccountPhase.CONNECTED)
        self.assertEqual((account.connections, account.disconnections, account.cancellations), (0, 0, 0))
        self.assertIsNone(window.messages_controller)

    def test_dialog_forget_clears_saved_fields_and_session_without_submission(self):
        store = FakeStore(RememberedD2Login(USERNAME, PASSWORD))
        window, _, provider, store = self.setup_login(store=store)
        dialog = self.manual_dialog(window)
        dialog.password_visibility_action.trigger()
        dialog.forget_button.click()
        self.assertEqual(store.deletes, 1)
        self.assertIsNone(store.record)
        self.assertEqual(provider.auth_calls, [])
        self.assertFalse(provider.authenticated)
        self.assertIs(window._sign_in_dialog, dialog)
        self.assertEqual(dialog.username_input.text(), "")
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(dialog.password_input.echoMode(), QLineEdit.EchoMode.Password)
        self.assertFalse(dialog.remember_checkbox.isChecked())
        self.assertTrue(dialog.forget_button.isHidden())
        self.assertEqual(dialog.storage_note.text(), "Saved router login was forgotten.")

    def test_settings_forget_clears_open_dialog_without_recursively_deleting_store(self):
        store = FakeStore(RememberedD2Login(USERNAME, PASSWORD))
        window, _, _, store = self.setup_login(store=store)
        dialog = self.manual_dialog(window)
        dialog.password_visibility_action.trigger()
        signals = []
        dialog.forget_requested.connect(lambda: signals.append(True))
        window.settings_page.forget_login_button.click()
        self.assertEqual(signals, [])
        self.assertEqual(store.deletes, 1)
        self.assertEqual(dialog.username_input.text(), "")
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(dialog.password_input.echoMode(), QLineEdit.EchoMode.Password)
        self.assertFalse(dialog.remember_checkbox.isChecked())

    def test_forget_revokes_uncooperative_late_startup_authentication(self):
        store = FakeStore(RememberedD2Login(USERNAME, PASSWORD))
        provider = FakeD2Provider(blocked=True, cooperative=False)
        window, _, provider, store = self.setup_login(store=store, provider=provider)
        self.assertTrue(window.start_initial_load())
        self.wait_until(provider.started.is_set)
        self.assertTrue(window.forget_saved_login())
        self.assertTrue(provider.auth_calls[0][1].is_set())
        provider.release.set()
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(store.saves, 0)
        self.assertEqual(store.deletes, 1)
        self.assertIsNone(store.record)
        self.assertFalse(provider.authenticated)
        self.assertFalse(window.live_label.isVisible())
        self.assertIsNone(window._sign_in_dialog)
        self.assertFalse(window.start_initial_load())
        self.assertEqual(len(provider.auth_calls), 1)

    def test_load_failure_uses_closed_notices_and_still_allows_runtime_login(self):
        store = FakeStore(load_error=RuntimeError(PRIVATE))
        window, service, provider, store = self.setup_login(store=store)
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            self.startup(window)
            dialog = self.manual_dialog(window)
        self.assertEqual(provider.auth_calls, [])
        self.assertEqual(service.storage_issue, LoginStorageIssue.LOAD)
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(dialog.storage_note.text(), "Saved router login is unavailable. Enter credentials for this session.")
        self.assertEqual(window.settings_page.saved_login_note.text(), "Saved D2 login is unavailable. Sign in manually.")
        self.assertNotIn(PRIVATE, output.getvalue() + self.displayed_text(window))

    def test_save_failure_keeps_verified_session_and_only_fixed_storage_notice(self):
        store = FakeStore(save_error=RuntimeError(PRIVATE))
        window, service, _, store = self.setup_login(store=store)
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            self.submit_manual(window)
            self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(store.saves, 1)
        self.assertIsNone(store.record)
        self.assertEqual(service.storage_issue, LoginStorageIssue.SAVE)
        self.assertTrue(window.live_label.isVisible())
        self.assertEqual(window.settings_page.saved_login_note.text(), "D2 sign-in succeeded, but the login could not be saved securely.")
        self.assertNotIn(PRIVATE, output.getvalue() + self.displayed_text(window))
        self.assertNotIn(PASSWORD, output.getvalue() + self.displayed_text(window))

    def test_failed_forget_does_not_claim_removal_or_reuse_saved_autofill(self):
        store = FakeStore(RememberedD2Login(USERNAME, PASSWORD), delete_error=RuntimeError(PRIVATE))
        window, service, provider, store = self.setup_login(store=store)
        self.startup(window)
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            self.assertFalse(window.forget_saved_login())
            dialog = self.manual_dialog(window)
        self.assertIsNotNone(store.record)
        self.assertFalse(provider.authenticated)
        self.assertEqual(service.storage_issue, LoginStorageIssue.DELETE)
        self.assertEqual(dialog.username_input.text(), "")
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(window.settings_page.saved_login_note.text(), "Saved D2 login could not be removed. Try Forget again.")
        self.assertFalse(window.settings_page.forget_login_button.isHidden())
        self.assertNotIn(PRIVATE, output.getvalue() + self.displayed_text(window))

    def test_close_is_bounded_during_native_save_and_late_write_is_removed(self):
        store = BlockingSaveStore()
        # Release even if an assertion fails; no test can leave a gated worker.
        self.addCleanup(store.save_release.set)
        provider = FakeD2Provider(blocked=True)
        window, _, provider, store = self.setup_login(store=store, provider=provider)
        self.submit_manual(window)
        self.wait_until(provider.started.is_set)
        provider.release.set()
        self.wait_until(store.save_started.is_set)
        worker = window.refresh_controller._thread
        before = self.values(window)
        started = time.monotonic()
        window.close()
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertFalse(provider.authenticated)
        self.assertFalse(window.open_sign_in())
        store.save_release.set()
        self.wait_until(lambda: not worker.is_alive())
        self.assertIsNone(store.record)
        self.assertGreaterEqual(store.deletes, 1)
        self.assertEqual(self.values(window), before)
        self.assertIsNone(window._sign_in_dialog)

    def test_demo_and_injected_provider_compositions_never_construct_windows_store(self):
        with patch("sim_manager.storage.windows_credentials.WindowsD2CredentialStore", side_effect=AssertionError("Credential-store construction forbidden")) as store:
            demo = app.create_window(demo=True)
            self.windows.append(demo)
            demo.show()
            self.wait_until(lambda: demo._startup_started and not demo.refresh_controller.busy)
            self.assertIsNone(demo._router_login)
            injected = self.provider()
            custom = app.create_window(provider=injected, account_service=StaticAccountService())
            self.windows.append(custom)
            custom.show()
            self.wait_until(lambda: custom._startup_started and not custom.refresh_controller.busy)
            self.assertIsNone(custom._router_login)
            store.assert_not_called()

    def test_production_composition_uses_fake_store_and_one_saved_startup_without_dito_browser(self):
        store = FakeStore(RememberedD2Login(USERNAME, PASSWORD))
        provider = FakeD2Provider()
        self.providers.append(provider)
        account = StaticAccountService()
        profiles, provider.snapshot = active_dito_profiles()
        with patch("sim_manager.services.device.LiveDeviceService", return_value=provider), patch(
            "sim_manager.storage.windows_credentials.WindowsD2CredentialStore", return_value=store,
        ) as constructor:
            window = app.create_window(account_service=account, sim_profiles=profiles)
            self.windows.append(window)
            window.show()
            self.wait_until(lambda: window._startup_started and not window.refresh_controller.busy)
        constructor.assert_called_once_with(provider.router_address)
        self.assertIsInstance(window._router_login, D2LoginService)
        self.assertEqual(len(provider.auth_calls), 1)
        self.assertEqual((store.loads, store.saves, store.deletes), (1, 0, 0))
        self.assertTrue(window.live_label.isVisible())
        self.assertEqual(account.state.phase, AccountPhase.CONNECTED)
        self.assertEqual(account.connections, 0)

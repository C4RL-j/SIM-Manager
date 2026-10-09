"""Synthetic SIM-first page checks; no router, vault, carrier or browser I/O."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import os
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QScrollArea

from sim_manager import app
from sim_manager.account_models import AccountPhase, AccountState, SessionValidity
from sim_manager.message_models import Message, MessageInbox
from sim_manager.models import DeviceState, RadioState
from sim_manager.services.presentation import present_device
from sim_manager.sim_models import SimCarrier, SimProfile
from sim_manager.ui.icons import navigation_icon
from sim_manager.ui.pages.history import HistoryPage
from sim_manager.ui.pages.home import HomePage
from sim_manager.ui.pages.messages import MessagesPage
from sim_manager.ui.pages.settings import SettingsPage
from sim_manager.ui.pages.sims import SimsPage


PHONE_A = "09000000001"
PHONE_B = "09000000002"
ID_A = "00000000-0000-4000-8000-000000000001"
ID_B = "00000000-0000-4000-8000-000000000002"
PRIVATE = "SYNTHETIC_PRIVATE_EXCEPTION"


def profile_a(*, name="Family SIM", active=True, carrier=SimCarrier.DITO):
    return SimProfile(profile_id=ID_A, name=name, phone_number=PHONE_A, carrier=carrier,
                      identity_key="iccid-v1:" + "1" * 64, active=active)


def profile_b(*, name="Backup SIM", active=False):
    return SimProfile(profile_id=ID_B, name=name, phone_number=PHONE_B,
                      identity_key="iccid-v1:" + "2" * 64, active=active)


class SyntheticAccount:
    is_demo = False

    def __init__(self, state=None):
        self.state = state or AccountState()
        self.listener = None
        self.calls = []

    def set_listener(self, listener):
        self.listener = listener
        if listener is not None:
            listener(self.state)

    def connect(self):
        self.calls.append("connect")
        return False

    def disconnect(self):
        self.calls.append("disconnect")

    def cancel(self):
        self.calls.append("cancel")

    def shutdown(self):
        self.calls.append("shutdown")

    def offer_otp(self, inbox):
        self.calls.append("offer")

    def otp_for_copy(self):
        self.calls.append("copy")
        return None


class SimPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = app.create_application([])
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.guards = ExitStack()
        self.addCleanup(self.guards.close)
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "webbrowser.open"):
            self.guards.enter_context(patch(target, side_effect=AssertionError("External I/O forbidden")))
        for operation in ("load", "save", "delete"):
            self.guards.enter_context(patch(
                "sim_manager.storage.windows_credentials.WindowsD2CredentialStore." + operation,
                side_effect=AssertionError("Real credential storage forbidden"),
            ))
        self.pages = []
        self.addCleanup(self.clean_pages)

    def clean_pages(self):
        for page in self.pages:
            if isinstance(page, SimsPage):
                page.account_controls.shutdown()
            page.close()
            page.deleteLater()
        self.application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def page(self, cls, *args, **kwargs):
        page = cls(*args, **kwargs)
        self.pages.append(page)
        page.show()
        self.application.processEvents()
        return page

    def test_home_displays_full_profile_text_and_preserves_all_router_metrics(self):
        page = self.page(HomePage)
        view = present_device(DeviceState(radio=RadioState(bands=(1, 3), rsrp=-91, rsrq=-10, rssi=-77, sinr=14)))
        page.render(view)
        saved = profile_a(name="<b>Family SIM</b>")
        page.render_profile(saved, current_sim=True)
        self.assertEqual(page.profile_values["name"].text(), "<b>Family SIM</b>")
        self.assertEqual(page.profile_values["phone_number"].text(), PHONE_A)
        self.assertEqual(page.profile_values["carrier"].text(), "DITO")
        for key, label in page.values.items():
            self.assertEqual(label.text(), getattr(view, key))
        self.assertTrue(any(label.text() == "Units unverified" for label in page.findChildren(QLabel)))
        for label in page.profile_values.values():
            self.assertEqual(label.textFormat(), Qt.TextFormat.PlainText)

    def test_home_unknown_sim_number_is_visible_without_fake_account_data(self):
        page = self.page(HomePage)
        page.render_profile(None, current_sim=True, phone_number=PHONE_A)
        self.assertEqual(page.profile_values["name"].text(), "Unnamed SIM")
        self.assertEqual(page.profile_values["phone_number"].text(), PHONE_A)
        for key in ("load_balance", "data_remaining", "promo", "promo_expiry"):
            self.assertEqual(page.profile_values[key].text(), "Not available")
        page.render_profile(None, current_sim=False, phone_number=PHONE_A)
        self.assertEqual(page.profile_values["name"].text(), "No active SIM")
        self.assertEqual(page.profile_values["phone_number"].text(), "Not provided")

    def test_home_quick_messages_action_emits_only_navigation_request(self):
        page = self.page(HomePage)
        requests = []
        page.messages_requested.connect(lambda: requests.append(True))
        page.messages_button.click()
        self.assertEqual(requests, [True])

    def test_sims_auto_selects_active_and_browsing_other_profile_retains_otp_session(self):
        account = SyntheticAccount(AccountState(phase=AccountPhase.CONNECTING, otp_available=True))
        page = self.page(SimsPage, account)
        active, other = profile_a(), profile_b()
        page.render_profiles((other, active), active, can_create=False, current_sim=True)
        page.account_controls.set_context(True)
        self.assertEqual(page.selected_profile.profile_id, ID_A)
        self.assertFalse(page.account_controls.isHidden())
        self.assertIn("Active", page.profile_list.item(1).text())
        state = account.state
        page.profile_list.setCurrentRow(0)
        self.assertTrue(page.account_controls.isHidden())
        self.assertEqual(page.profile_number_label.text(), PHONE_B)
        self.assertIs(account.state, state)
        self.assertTrue(account.state.otp_available)
        self.assertTrue(page.account_controls.otp_copy_button.isEnabled())
        self.assertEqual(account.calls, [])

    def test_unknown_or_inactive_profile_has_no_visible_account_controls(self):
        account = SyntheticAccount(AccountState(phase=AccountPhase.CONNECTED, validity=SessionValidity.VALIDATED))
        page = self.page(SimsPage, account)
        unknown = profile_a(carrier=SimCarrier.UNKNOWN)
        page.render_profiles((unknown,), unknown, can_create=False, current_sim=True)
        self.assertTrue(page.account_controls.isHidden())
        active = profile_a()
        page.render_profiles((active,), active, can_create=False, current_sim=False)
        self.assertTrue(page.account_controls.isHidden())
        self.assertEqual(account.calls, [])

    def test_create_offer_is_optional_and_actual_combo_emits_dito_enum(self):
        account = SyntheticAccount()
        page = self.page(SimsPage, account)
        page.render_profiles((), None, can_create=True, current_sim=True, current_phone_number=PHONE_A)
        self.assertFalse(page.create_card.isHidden())
        self.assertEqual(page.create_name_input.text(), "")
        self.assertEqual(page.create_phone_input.text(), PHONE_A)
        requests = []
        page.create_requested.connect(lambda name, phone, carrier: requests.append((name, phone, carrier)))
        page.create_button.click()
        self.assertEqual(requests, [])
        self.assertEqual(page.notice_label.text(), "Enter a SIM name.")
        page.create_name_input.setText("Fixture DITO SIM")
        page.create_carrier_combo.setCurrentIndex(page.create_carrier_combo.findData(SimCarrier.DITO.value))
        page.create_button.click()
        self.assertEqual(requests, [("Fixture DITO SIM", PHONE_A, SimCarrier.DITO)])
        self.assertIs(requests[0][2], SimCarrier.DITO)
        self.assertEqual(account.calls, [])
        self.assertTrue(all(field.echoMode() == QLineEdit.EchoMode.Normal for field in page.findChildren(QLineEdit)))

    def test_repeated_snapshots_preserve_creation_edits_and_real_context_reset_prefills_new_number(self):
        page = self.page(SimsPage)
        page.render_profiles((), None, can_create=True, current_sim=True, current_phone_number=PHONE_A)
        page.create_name_input.setText("Work in progress")
        page.create_phone_input.setText(PHONE_B)
        page.render_profiles((), None, can_create=True, current_sim=True, current_phone_number=PHONE_A)
        self.assertEqual(page.create_name_input.text(), "Work in progress")
        self.assertEqual(page.create_phone_input.text(), PHONE_B)
        page.reset_create_form()
        page.render_profiles((), None, can_create=True, current_sim=True, current_phone_number=PHONE_A)
        self.assertEqual(page.create_name_input.text(), "")
        self.assertEqual(page.create_phone_input.text(), PHONE_A)

    def test_rename_inactive_profile_emits_stable_id_without_activation_or_number_change(self):
        account = SyntheticAccount()
        page = self.page(SimsPage, account)
        active, other = profile_a(), profile_b()
        page.render_profiles((active, other), active, can_create=False, current_sim=True)
        page.profile_list.setCurrentRow(1)
        requests = []
        page.rename_requested.connect(lambda identifier, name: requests.append((identifier, name)))
        page.rename_name_input.setText("Renamed backup")
        page.rename_button.click()
        self.assertEqual(requests, [(ID_B, "Renamed backup")])
        self.assertEqual(other.name, "Backup SIM")
        self.assertEqual(other.phone_number, PHONE_B)
        self.assertEqual(active.profile_id, ID_A)
        self.assertEqual(account.calls, [])

    def test_profile_refresh_preserves_selected_row_and_in_progress_rename(self):
        page = self.page(SimsPage)
        active, other = profile_a(), profile_b()
        page.render_profiles((active, other), active, can_create=False, current_sim=True)
        page.profile_list.setCurrentRow(1)
        page.rename_name_input.setText("In progress")
        page.render_profiles((active, other), active, can_create=False, current_sim=True)
        self.assertEqual(page.selected_profile.profile_id, ID_B)
        self.assertEqual(page.rename_name_input.text(), "In progress")
        renamed = profile_b(name="Renamed backup")
        page.render_profiles((active, renamed), active, can_create=False, current_sim=True)
        self.assertEqual(page.rename_name_input.text(), "Renamed backup")

    def test_real_active_profile_change_selects_new_active_row(self):
        page = self.page(SimsPage)
        first, second = profile_a(), profile_b()
        page.render_profiles((first, second), first, can_create=False, current_sim=True)
        page.render_profiles((first, second), second, can_create=False, current_sim=True)
        self.assertEqual(page.selected_profile.profile_id, ID_B)
        self.assertIn("Active", page.profile_list.item(1).text())

    def test_private_raw_notice_is_closed_without_log_output(self):
        page = self.page(SimsPage)
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            page.render_profiles((), None, can_create=False, current_sim=False, notice=PRIVATE)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn(PRIVATE, page.notice_label.text())

    def test_messages_context_is_plain_full_number_and_reset_drops_old_sim_content(self):
        page = self.page(MessagesPage)
        page.set_sim_context(profile_a(name="<b>Family SIM</b>"), current_sim=True)
        self.assertEqual(page.sim_context_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertIn(PHONE_A, page.sim_context_label.text())
        page.render(MessageInbox(messages=(Message(sender="Synthetic sender", body="Synthetic previous SIM content"),)))
        self.assertTrue(page.loaded)
        page.reset_inbox()
        page.set_sim_context(None, current_sim=True)
        self.assertFalse(page.loaded)
        self.assertEqual(page.message_list.count(), 0)
        self.assertEqual(page.content_view.toPlainText(), "")
        self.assertEqual(page.empty_label.text(), "No messages loaded")
        self.assertNotIn("1 message", page.status_label.text())
        self.assertNotIn(PHONE_A, page.sim_context_label.text())

    def test_settings_contains_only_router_application_and_saved_router_login_controls(self):
        page = self.page(SettingsPage, router_address="https://192.168.1.1")
        self.assertFalse(hasattr(page, "account_controls"))
        self.assertEqual(page.router_address_label.text(), "https://192.168.1.1")
        self.assertEqual(set(page.findChildren(QPushButton)), {page.forget_login_button})
        self.assertEqual(page.findChildren(QLineEdit), [])
        self.assertFalse(any("DITO" in label.text() for label in page.findChildren(QLabel)))

    def test_history_is_placeholder_without_collecting_or_mutating_controls(self):
        page = self.page(HistoryPage)
        self.assertTrue(any("not available" in label.text() for label in page.findChildren(QLabel)))
        self.assertEqual(page.findChildren(QPushButton), [])
        self.assertEqual(page.findChildren(QLineEdit), [])

    def test_new_pages_fit_minimum_workspace_width_with_long_synthetic_name(self):
        long_profile = profile_a(name="W" * 80)
        for cls in (HomePage, SimsPage, MessagesPage, HistoryPage, SettingsPage):
            with self.subTest(page=cls.__name__):
                page = self.page(cls)
                if isinstance(page, HomePage):
                    page.render_profile(long_profile, current_sim=True)
                elif isinstance(page, SimsPage):
                    page.render_profiles((long_profile,), long_profile, can_create=False, current_sim=True)
                elif isinstance(page, MessagesPage):
                    page.set_sim_context(long_profile, current_sim=True)
                scroller = QScrollArea()
                scroller.setWidgetResizable(True)
                scroller.setWidget(page)
                scroller.resize(600, 440)
                scroller.show()
                self.application.processEvents()
                try:
                    self.assertEqual(scroller.horizontalScrollBar().maximum(), 0)
                finally:
                    # Return ownership to our normal page cleanup.
                    scroller.takeWidget()
                    scroller.close()
                    scroller.deleteLater()

    def test_home_sims_history_icons_have_visible_pixels_at_native_resolution(self):
        for name in ("Home", "SIMs", "History"):
            with self.subTest(name=name):
                raster = navigation_icon(name).pixmap(20, 20).toImage()
                self.assertTrue(any(raster.pixelColor(x, y).alpha() for x in range(20) for y in range(20)))

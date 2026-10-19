"""Offline native helpers with synthetic profiles/inboxes and no carrier I/O."""

from contextlib import redirect_stderr, redirect_stdout
import io
from unittest.mock import patch

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QLabel

from test_desktop import DesktopCase
from sim_manager.message_models import Message, MessageInbox
from sim_manager.models import DeviceState, Readiness, SimState
from sim_manager.services.sign_in_helpers import NewMessageOtpWatch
from sim_manager.services.sim_profiles import SimProfileService
from sim_manager.sim_models import SimCarrier
from sim_manager.storage.sim_profiles import MemorySimProfileStore
from sim_manager.ui.sign_in_helpers import SignInHelpers


def snapshot(key="a"):
    return DeviceState(
        sim=SimState(present=True, readiness=Readiness.READY,
                     identity_key="iccid-v1:" + key * 64),
        successful_sources=("sim", "device", "deviceDetails"),
    )


def otp(code="123456", identity="synthetic-one"):
    return Message(identity=identity, sender="DITO",
                   body=f"{code} is your authentication code.")


class SyntheticInboxController(QObject):
    inbox_ready = Signal(object)
    failed = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.busy = False
        self.starts = 0
        self.cancels = 0
        self.shutdowns = 0

    def start(self):
        if self.busy:
            return False
        self.busy = True
        self.starts += 1
        self.busy_changed.emit(True)
        return True

    def complete(self, inbox):
        self.busy = False
        self.busy_changed.emit(False)
        self.inbox_ready.emit(inbox)

    def fail(self, reason):
        self.busy = False
        self.busy_changed.emit(False)
        self.failed.emit(reason)

    def cancel(self):
        self.cancels += 1

    def shutdown(self):
        self.shutdowns += 1


class SignInHelpersTests(DesktopCase):
    def profiles(self, *, phone="09920000001", carrier=SimCarrier.DITO):
        profiles = SimProfileService(MemorySimProfileStore())
        profiles.observe(snapshot())
        first = profiles.create_profile("Synthetic current SIM", phone, carrier)
        profiles.observe(snapshot("b"))
        profiles.create_profile("Synthetic spare SIM", "09920000002", SimCarrier.UNKNOWN)
        profiles.observe(snapshot())
        return profiles, first

    def helper(self, *, profiles=None, controller=None, refresh=None):
        if profiles is None:
            profiles, _ = self.profiles()
        if controller is None:
            controller = SyntheticInboxController()
        helper = SignInHelpers(profiles, controller, refresh or controller.start)
        helper.resize(448, 94)
        helper.show()
        self.addCleanup(helper.deleteLater)
        self.addCleanup(helper.close)
        self.addCleanup(helper.shutdown)
        return helper, controller, profiles

    def next_read(self, helper):
        helper._next_read = 0.0
        helper._poll()

    def candidate(self, helper, controller):
        helper.request_sms_code(1)
        controller.complete(MessageInbox((otp(),)))
        self.next_read(helper)
        controller.complete(MessageInbox((otp(), otp("654321", "synthetic-two"))))

    def test_profiles_current_highlight_others_disabled_and_number_survives_long_name(self):
        helper, controller, profiles = self.helper()
        self.assertEqual(controller.starts, 0)
        self.assertEqual(helper.profile_combo.count(), 2)
        current = helper.profile_combo.model().item(0)
        other = helper.profile_combo.model().item(1)
        self.assertTrue(current.isEnabled())
        self.assertTrue(current.font().bold())
        self.assertFalse(other.isEnabled())
        self.assertFalse(other.isSelectable())
        self.assertIn("DITO · 09920000001", current.text())
        self.assertIn("Unknown · 09920000002", other.text())
        self.assertEqual(helper.profile_combo.currentIndex(), 0)
        self.assertIn("09920000001", helper.number_label.text())
        profiles.rename_profile(profiles.active_profile.profile_id, "Long name <b>" + "x" * 60)
        helper._sync_profiles()
        self.assertIn("Long name", helper.profile_combo.itemText(0))
        tooltip = helper.profile_combo.itemData(0, Qt.ItemDataRole.ToolTipRole)
        self.assertIn("&lt;b&gt;", tooltip)
        self.assertNotIn("<b>", tooltip)
        self.assertIn("09920000001", helper.number_label.text())
        self.assertEqual(helper.height(), 94)
        self.assertLessEqual(helper.minimumSizeHint().width(), 448)

    def test_copy_removes_exactly_one_zero_preserves_saved_number_and_user_clipboard(self):
        profiles, _ = self.profiles(phone="00992000001")
        helper, _, _ = self.helper(profiles=profiles)
        self.application.clipboard().setText("Synthetic previous clipboard")
        helper.copy_number_button.click()
        self.assertEqual(self.application.clipboard().text(), "0992000001")
        self.assertEqual(profiles.active_profile.phone_number, "00992000001")
        helper.stop()
        self.assertEqual(self.application.clipboard().text(), "")
        helper.copy_number_button.click()
        self.application.clipboard().setText("Synthetic user clipboard")
        helper.shutdown()
        self.assertEqual(self.application.clipboard().text(), "Synthetic user clipboard")

    def test_only_requested_new_otp_is_offered_fill_copy_are_explicit_and_never_submit(self):
        helper, controller, _ = self.helper()
        received = []
        helper.fill_requested.connect(received.append)
        self.application.clipboard().setText("Synthetic unchanged clipboard")
        helper.request_sms_code(1)
        self.assertEqual(controller.starts, 1)
        self.assertEqual(helper._read_timer.interval(), 2000)
        controller.complete(MessageInbox((otp(),)))
        self.assertFalse(helper.copy_otp_button.isVisible())
        self.next_read(helper)
        controller.complete(MessageInbox((otp(), otp("654321", "synthetic-two"))))
        self.assertTrue(helper.copy_otp_button.isVisible())
        self.assertFalse(helper.fill_otp_button.isEnabled())
        self.assertEqual(received, [])
        self.assertEqual(self.application.clipboard().text(), "Synthetic unchanged clipboard")
        helper.set_fillable(True)
        helper.fill_otp_button.click()
        self.assertEqual(received, ["654321"])
        self.assertFalse(helper.fill_otp_button.isEnabled())
        helper.fill_result(True)
        self.assertIn("Click Sign In on MyDITO", helper.status_label.text())
        helper.copy_otp_button.click()
        self.assertEqual(self.application.clipboard().text(), "654321")
        for label in helper.findChildren(QLabel):
            self.assertNotIn("654321", label.text())
        helper.stop()
        self.assertFalse(helper.copy_otp_button.isVisible())
        self.assertEqual(self.application.clipboard().text(), "")

    def test_pre_request_and_superseded_reads_are_ignored_without_overlapping_workers(self):
        helper, controller, _ = self.helper()
        controller.start()  # A Messages-page request already in progress.
        helper.request_sms_code(1)
        self.assertEqual(controller.starts, 1)
        controller.complete(MessageInbox((otp(),)))
        self.assertFalse(helper._watch.available)
        self.next_read(helper)
        self.assertEqual(controller.starts, 2)
        helper.request_sms_code(2)
        helper.request_sms_code(2)  # Repeated probe notification is not a request.
        helper._poll()
        self.assertEqual(controller.starts, 2)
        controller.complete(MessageInbox((otp("654321"),)))
        self.assertFalse(helper._watch.available)
        self.next_read(helper)
        controller.complete(MessageInbox((otp("654321"),)))  # New request baseline.
        self.assertFalse(helper.copy_otp_button.isVisible())
        self.next_read(helper)
        controller.complete(MessageInbox((otp("654321"), otp("112233", "new"))))
        self.assertTrue(helper.copy_otp_button.isVisible())
        self.assertEqual(helper._watch.value(), "112233")

    def test_sim_context_change_revokes_stale_fill_copy_and_cancels_only_owned_work(self):
        helper, controller, profiles = self.helper()
        self.candidate(helper, controller)
        helper.set_fillable(True)
        received = []
        helper.fill_requested.connect(received.append)
        helper.copy_otp_button.click()
        self.next_read(helper)
        profiles.observe(snapshot("b"))
        helper.fill_otp_button.click()  # Guard before the periodic UI update.
        helper.copy_number_button.click()
        self.assertEqual(received, [])
        helper._sync_profiles()
        self.assertEqual(controller.cancels, 1)
        self.assertEqual(controller.shutdowns, 0)
        self.assertEqual(self.application.clipboard().text(), "")
        self.assertFalse(helper.copy_otp_button.isVisible())
        self.assertFalse(helper.copy_number_button.isEnabled())
        self.assertIn("SIM changed", helper.status_label.text())
        profiles.observe(snapshot())
        helper.request_sms_code(2)
        self.assertFalse(helper._watch.active)

    def test_shutdown_preserves_shared_external_read_and_ignores_late_signals(self):
        helper, controller, _ = self.helper()
        controller.start()
        helper.request_sms_code(1)
        helper.shutdown()
        self.assertEqual(controller.cancels, 0)
        self.assertEqual(controller.shutdowns, 0)
        self.assertTrue(controller.busy)
        controller.complete(MessageInbox((otp(),)))
        helper.request_sms_code(2)
        self.application.processEvents()
        self.assertEqual(controller.starts, 1)
        self.assertFalse(helper._read_timer.isActive())
        self.assertFalse(helper._context_timer.isActive())
        self.assertEqual(helper.profile_combo.count(), 0)

    def test_expiry_and_fill_failure_clear_actions_without_changing_authentication(self):
        helper, controller, _ = self.helper()
        now = [0.0]
        helper._watch = NewMessageOtpWatch(clock=lambda: now[0])
        self.candidate(helper, controller)
        helper.set_fillable(True)
        helper.fill_otp_button.click()
        helper.fill_result(False)
        self.assertIn("Copy OTP", helper.status_label.text())
        helper.copy_otp_button.click()
        self.next_read(helper)
        now[0] = 301.0
        helper._sync_profiles()
        self.assertEqual(controller.cancels, 1)
        self.assertFalse(helper._read_timer.isActive())
        self.assertFalse(helper.copy_otp_button.isVisible())
        self.assertEqual(self.application.clipboard().text(), "")
        self.assertIn("check ended", helper.status_label.text())

    def test_missing_active_dito_and_private_errors_fail_closed_without_diagnostics(self):
        profiles, _ = self.profiles(carrier=SimCarrier.UNKNOWN)
        helper, controller, _ = self.helper(profiles=profiles)
        helper.copy_number_button.click()
        helper.request_sms_code(1)
        self.assertFalse(helper.copy_number_button.isEnabled())
        self.assertEqual(controller.starts, 0)
        private = "Synthetic private SMS body and OTP 123456"

        def failure():
            raise RuntimeError(private)

        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            usable, failing_controller, _ = self.helper(refresh=failure)
            usable.request_sms_code(1)
            self.assertIsNone(usable._owned_generation)
            usable._refresh = failing_controller.start
            self.next_read(usable)
            failing_controller.fail(private)
            self.next_read(usable)
            failing_controller.complete(MessageInbox((otp(),), partial=True))
            self.assertFalse(usable.copy_otp_button.isVisible())
            self.next_read(usable)
            failing_controller.complete(MessageInbox((otp(),)))
            self.assertFalse(usable.copy_otp_button.isVisible())
            self.next_read(usable)
            failing_controller.complete(MessageInbox((otp(), otp("654321", "new"))))
            self.assertTrue(usable.copy_otp_button.isVisible())
            clipboard_target = "sim_manager.ui.sign_in_helpers.QApplication.clipboard"
            with patch(clipboard_target, side_effect=RuntimeError(private)):
                usable.copy_number_button.click()
                usable.copy_otp_button.click()
                usable._copied = "Synthetic owned clipboard"
                usable._clear_copied()
                self.assertIsNone(usable._copied)
            for operation in ("setText", "text", "clear"):
                with patch(clipboard_target) as clipboard:
                    clipboard.return_value.text.return_value = "Synthetic owned clipboard"
                    getattr(clipboard.return_value, operation).side_effect = RuntimeError(private)
                    if operation == "setText":
                        usable.copy_number_button.click()
                        usable.copy_otp_button.click()
                    else:
                        usable._copied = "Synthetic owned clipboard"
                        usable._clear_copied()
                        self.assertIsNone(usable._copied)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(errors.getvalue(), "")
        self.assertNotIn(private, usable.status_label.text())
        self.assertNotIn("123456", repr(usable._watch))


if __name__ == "__main__":
    import unittest
    unittest.main()

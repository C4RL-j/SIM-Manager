"""One synthetic scheduler clock/session shared by manual and timed actions."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
import os
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from sim_manager.account_models import AccountDataIssue, AccountPhase, AccountState, SessionValidity
from sim_manager.ui.account_refresh import AccountRefreshController


def connected(**values):
    return AccountState(phase=AccountPhase.CONNECTED, validity=SessionValidity.VALIDATED, **values)


class AccountRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.now = 100.0
        self.context = ("synthetic-profile", 1)
        self.state = connected()
        self.calls = 0
        self.controller = AccountRefreshController(self.refresh, clock=lambda: self.now)
        self.addCleanup(self.controller.shutdown)

    def observe(self, state, context=None):
        self.state = state
        self.controller.observe(state, self.context if context is None else context)

    def refresh(self):
        self.calls += 1
        self.observe(replace(self.state, data_refreshing=True, data_issue=None, retry_after_seconds=None))
        return True

    def test_deferred_startup_does_not_duplicate_existing_post_login_read_and_uses_one_timer(self):
        self.observe(connected())
        self.assertTrue(self.controller._timer.isActive())
        self.assertEqual(self.controller._timer.interval(), 0)
        self.observe(connected(data_refreshing=True))
        self.assertFalse(self.controller._timer.isActive())
        self.controller._timer.timeout.emit()
        self.assertEqual(self.calls, 0)
        self.assertFalse(self.controller.can_refresh_now)
        self.observe(connected())
        self.assertEqual(self.controller._timer.interval(), 30_000)
        self.now += 29
        self.controller._timer.timeout.emit()
        self.assertEqual(self.calls, 0)
        self.now += 1
        self.controller._timer.timeout.emit()
        self.assertEqual(self.calls, 1)
        self.assertFalse(self.controller.request_now())
        self.assertFalse(self.controller._timer.isActive())
        self.assertEqual(len(self.controller.findChildren(QTimer)), 1)

    def test_expiry_context_loss_unknown_validity_and_shutdown_stop_without_login_actions(self):
        states = (AccountState(), AccountState(phase=AccountPhase.CONNECTING),
                  AccountState(phase=AccountPhase.CONNECTED),
                  AccountState(phase=AccountPhase.EXPIRED, validity=SessionValidity.EXPIRED),
                  connected(data_issue=AccountDataIssue.ACCOUNT_MISMATCH), connected(is_demo=True))
        for state in states:
            self.observe(state)
            self.assertFalse(self.controller.can_refresh_now)
            self.assertFalse(self.controller._timer.isActive())
            self.assertFalse(self.controller.request_now())
        self.observe(connected())
        self.controller.observe(self.state, None)
        self.assertFalse(self.controller._timer.isActive())
        self.assertFalse(self.controller.can_refresh_now)
        self.context = ("synthetic-other-profile", 2)
        self.observe(connected())
        self.assertEqual(self.controller._timer.interval(), 0)
        self.controller.shutdown()
        self.controller._timer.timeout.emit()
        self.assertEqual(self.calls, 0)
        self.assertFalse(self.controller.request_now())
        self.assertIsNone(self.controller._context)
        self.assertIsNone(self.controller._last_state)

    def test_disabled_auto_keeps_manual_available_and_interval_change_has_no_overlap(self):
        self.controller.configure(False, 15)
        self.observe(connected())
        self.assertFalse(self.controller._timer.isActive())
        self.assertTrue(self.controller.can_refresh_now)
        self.assertEqual(self.controller.status_text, "Automatic refresh off.")
        self.assertTrue(self.controller.request_now())
        self.controller.configure(True, 60)
        self.assertFalse(self.controller._timer.isActive())
        self.assertFalse(self.controller.request_now())
        self.observe(connected())
        self.assertEqual(self.controller._timer.interval(), 60_000)
        self.now += 5
        self.observe(self.state)
        self.assertEqual(self.controller._timer.interval(), 60_000)
        self.assertEqual(self.controller.interval_seconds, 60)

    def test_automatic_failure_backoff_is_bounded_manual_can_override_and_success_resets_it(self):
        self.observe(connected())
        self.controller.request_now()
        for delay in (30, 60, 120, 240, 480, 600, 600):
            self.observe(connected(data_issue=AccountDataIssue.UNAVAILABLE))
            self.assertEqual(self.controller._timer.interval(), delay * 1000)
            self.assertTrue(self.controller.can_refresh_now)
            calls = self.calls
            self.controller._timer.timeout.emit()
            self.assertEqual(self.calls, calls)
            self.now += delay
            self.controller._timer.timeout.emit()
            self.assertEqual(self.calls, calls + 1)
        self.observe(connected())
        self.assertEqual(self.controller._timer.interval(), 30_000)
        self.assertTrue(self.controller.request_now())
        self.observe(connected(data_issue=AccountDataIssue.UNSUPPORTED))
        self.assertEqual(self.controller._timer.interval(), 30_000)
        self.assertTrue(self.controller.request_now())
        self.assertFalse(self.controller.can_refresh_now)

    def test_server_cooldown_blocks_manual_even_with_auto_off_and_reenables_without_request(self):
        self.controller.configure(False, 30)
        self.observe(connected())
        self.controller.request_now()
        self.observe(connected(data_issue=AccountDataIssue.RATE_LIMITED, retry_after_seconds=120))
        self.assertFalse(self.controller.can_refresh_now)
        self.assertFalse(self.controller.request_now())
        self.assertIn("Rate limited", self.controller.status_text)
        self.assertEqual(self.controller._timer.interval(), 120_000)
        self.controller.configure(False, 15)
        self.now += 119
        self.controller._timer.timeout.emit()
        self.assertFalse(self.controller.can_refresh_now)
        self.now += 1
        self.controller._timer.timeout.emit()
        self.assertTrue(self.controller.can_refresh_now)
        self.assertFalse(self.controller._timer.isActive())
        self.assertEqual(self.calls, 1)
        self.controller.request_now()
        self.observe(connected(data_issue=AccountDataIssue.RATE_LIMITED))
        self.assertEqual(self.controller._timer.interval(), 60_000)

    def test_private_callback_error_and_invalid_configuration_do_not_publish_private_values(self):
        output = StringIO()
        def fail():
            raise RuntimeError("SYNTHETIC_PRIVATE_ACCOUNT_PAYLOAD")
        self.controller._refresh = fail
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            self.observe(connected())
            self.assertFalse(self.controller.request_now())
            self.assertTrue(self.controller.can_refresh_now)
            self.assertEqual(self.controller._timer.interval(), 30_000)
            self.assertNotIn("SYNTHETIC_PRIVATE", self.controller.status_text + repr(self.controller))
            for value in (True, 0, 10, "30"):
                with self.assertRaisesRegex(ValueError, "^Account refresh settings are invalid\\.$"):
                    self.controller.configure(True, value)
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()

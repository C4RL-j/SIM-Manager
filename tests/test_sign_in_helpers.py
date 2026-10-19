"""Synthetic freshness, privacy and copy formatting; no browser or retrieval."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import unittest

from sim_manager.message_models import Message, MessageInbox, MessageIssueCode
from sim_manager.services.sign_in_helpers import NewMessageOtpWatch, mydito_number


def otp(code: str, *, identity: str = "synthetic", timestamp: str = "unknown") -> Message:
    return Message(
        identity=identity, timestamp=timestamp, sender="DITO",
        body=f"{code} is your authentication code. Synthetic test message.",
    )


class SignInHelperTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.watch = NewMessageOtpWatch(clock=lambda: self.now)

    def test_copy_number_removes_exactly_one_leading_zero_only(self):
        for original, copied in (
            ("09000000001", "9000000001"), ("009000000001", "09000000001"),
            ("9000000001", "9000000001"), ("+639000000001", "+639000000001"),
            (" 09000000001", " 09000000001"), ("0", ""), ("", ""),
        ):
            with self.subTest(number=original):
                self.assertEqual(mydito_number(original), copied)
        self.assertEqual(mydito_number(None), "")

    def test_watch_is_explicit_and_complete_first_snapshot_never_offers(self):
        old = MessageInbox((otp("123456"),))
        self.assertFalse(self.watch.observe(old))
        self.assertFalse(self.watch.active)
        self.watch.start_request()
        for incomplete in (
            MessageInbox((otp("654321"),), available=False),
            MessageInbox((otp("654321"),), partial=True),
            MessageInbox((otp("654321"),), issues=(MessageIssueCode.MALFORMED_ENTRY,)),
        ):
            self.assertFalse(self.watch.observe(incomplete))
            self.assertIsNone(self.watch.value())
        self.assertFalse(self.watch.observe(old))
        self.assertFalse(self.watch.observe(old))
        self.assertTrue(self.watch.observe(MessageInbox((otp("654321"),))))
        self.assertEqual(self.watch.value(), "654321")

    def test_content_identity_ignores_router_ids_timestamps_and_order(self):
        self.watch.start_request()
        self.watch.observe(MessageInbox((otp("123456", identity="old", timestamp="future"),)))
        same_body = otp("123456", identity="changed", timestamp="past")
        self.assertFalse(self.watch.observe(MessageInbox((same_body,))))
        reused_id = otp("654321", identity="old", timestamp="future")
        self.assertTrue(self.watch.observe(MessageInbox((reused_id, same_body))))
        self.assertEqual(self.watch.value(), "654321")
        self.assertTrue(self.watch.observe(MessageInbox((same_body, reused_id))))
        self.assertTrue(self.watch.observe(MessageInbox()))
        self.assertTrue(self.watch.observe(MessageInbox(partial=True)))
        self.assertEqual(self.watch.value(), "654321")

    def test_unique_code_accepts_duplicates_but_ambiguity_stays_disabled(self):
        self.watch.start_request()
        self.watch.observe(MessageInbox())
        same_code_other_body = Message(sender=" dito ", body="654321 is your authentication code.")
        self.assertTrue(self.watch.observe(MessageInbox((otp("654321"), same_code_other_body))))
        self.assertFalse(self.watch.observe(MessageInbox((otp("000012"),))))
        self.assertIsNone(self.watch.value())
        self.assertFalse(self.watch.observe(MessageInbox((otp("654321"),))))

    def test_retry_excludes_all_previous_requests_even_if_baseline_empty(self):
        self.watch.start_request()
        self.watch.observe(MessageInbox((otp("123456"),)))
        self.watch.observe(MessageInbox((otp("654321"),)))
        self.watch.start_request()
        self.assertIsNone(self.watch.value())
        self.watch.observe(MessageInbox())
        self.assertFalse(self.watch.observe(MessageInbox((otp("654321"), otp("123456")))))
        self.assertTrue(self.watch.observe(MessageInbox((otp("000012"),))))
        self.assertEqual(self.watch.value(), "000012")

    def test_monotonic_expiry_and_cancel_release_candidate_and_history(self):
        self.watch.start_request()
        self.watch.observe(MessageInbox())
        self.watch.observe(MessageInbox((otp("123456"),)))
        self.now = 309.999
        self.assertTrue(self.watch.available)
        self.now = 310.0
        self.assertFalse(self.watch.active)
        self.assertIsNone(self.watch.value())
        self.watch.start_request()
        self.watch.observe(MessageInbox())
        self.assertFalse(self.watch.observe(MessageInbox((otp("123456"),))))
        self.watch.cancel()
        self.assertFalse(self.watch.active)
        self.assertEqual(self.watch._seen, set())
        self.assertEqual(self.watch._excluded, set())
        self.watch.start_request()
        self.watch.observe(MessageInbox())
        self.assertTrue(self.watch.observe(MessageInbox((otp("123456"),))))

    def test_bounds_and_unknown_values_fail_closed_without_raw_errors(self):
        self.watch.start_request()
        self.assertFalse(self.watch.observe(None))
        self.assertFalse(self.watch.observe(MessageInbox(messages=[])))
        self.assertFalse(self.watch.observe(MessageInbox(("private body",))))
        self.watch.observe(MessageInbox())
        self.watch._MAX_FINGERPRINTS = 1
        self.watch.observe(MessageInbox((otp("123456"),)))
        self.assertFalse(self.watch.observe(MessageInbox((otp("654321"),))))
        self.watch.start_request()
        self.assertFalse(self.watch.active)
        self.watch.cancel()
        self.watch._MAX_OBSERVATIONS = 1
        self.watch.start_request()
        self.watch.observe(MessageInbox())
        self.assertFalse(self.watch.observe(MessageInbox((otp("123456"),))))

    def test_private_state_and_clock_failure_emit_no_logs_or_output(self):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            self.watch.start_request()
            self.watch.observe(MessageInbox())
            self.watch.observe(MessageInbox((otp("123456"),)))
            self.assertEqual(repr(self.watch), "NewMessageOtpWatch(<details omitted>)")
            self.assertEqual(str(self.watch), repr(self.watch))
            self.assertNotIn("123456", repr(vars(self.watch)))
            self.assertNotIn("authentication code", repr(vars(self.watch)))
            def broken_clock():
                raise RuntimeError("private phone 09000000001; code 123456")
            self.watch._clock = broken_clock
            self.assertIsNone(self.watch.value())
            self.watch.start_request()
            self.assertFalse(self.watch.active)
        self.assertEqual(output.getvalue(), "")
        with self.assertRaisesRegex(ValueError, "^Invalid OTP helper lifetime\\.$"):
            NewMessageOtpWatch(max_age="private")


if __name__ == "__main__":
    unittest.main()

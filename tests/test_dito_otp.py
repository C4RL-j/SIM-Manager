"""Synthetic carrier-specific matching and private diagnostic output."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from sim_manager.carriers.dito import DitoOtpCandidate, match_otp
from sim_manager.message_models import Message


class DitoOtpTests(unittest.TestCase):
    def test_source_evidenced_sender_and_prefix_match(self):
        candidate = match_otp(Message(sender="DITO", body="123456 is your authentication code."))
        self.assertIsInstance(candidate, DitoOtpCandidate)
        self.assertEqual(candidate.copy_value(), "123456")

    def test_case_and_ascii_whitespace_are_tolerated(self):
        candidate = match_otp(Message(sender=" dito ", body="\n654321\tIS YOUR AUTHENTICATION CODE. Never share it."))
        self.assertEqual(candidate.copy_value(), "654321")

    def test_zero_prefixed_ascii_code_is_preserved(self):
        self.assertEqual(match_otp(Message(sender="DITO", body="000012 is your authentication code.")).copy_value(), "000012")

    def test_unrelated_sender_does_not_match(self):
        for sender in (None, "", "Other", "DITO support", "prefixDITO", "DITO.ph"):
            with self.subTest(sender=sender):
                self.assertIsNone(match_otp(Message(sender=sender, body="123456 is your authentication code.")))

    def test_unrelated_body_does_not_match(self):
        for body in ("", "123456 is your purchase confirmation code.",
                     "Your authentication code is 123456.",
                     "Sample text 123456 is your authentication code.",
                     "123456 is your authentication code", "A123456 is your authentication code."):
            with self.subTest(body=body):
                self.assertIsNone(match_otp(Message(sender="DITO", body=body)))

    def test_wrong_length_and_unicode_digits_do_not_match(self):
        for code in ("12345", "1234567", "１２３４５６", "١٢٣٤٥٦", "12345x"):
            with self.subTest(code=code):
                self.assertIsNone(match_otp(Message(sender="DITO", body=f"{code} is your authentication code.")))

    def test_malformed_types_are_ignored_without_string_conversion(self):
        class DangerousValue:
            def __str__(self):
                raise RuntimeError("Synthetic private conversion")
        for message in (None, {}, "Synthetic message",
                        Message(sender=DangerousValue(), body="123456 is your authentication code."),
                        Message(sender="DITO", body=DangerousValue())):
            self.assertIsNone(match_otp(message))

    def test_timestamp_and_identity_do_not_assert_freshness_or_latest(self):
        candidate = match_otp(Message(identity="synthetic-old", sender="DITO", timestamp="Unknown router time", body="123456 is your authentication code."))
        self.assertEqual(candidate.copy_value(), "123456")
        self.assertFalse(hasattr(candidate, "timestamp"))
        self.assertFalse(hasattr(candidate, "identity"))

    def test_candidate_repr_and_str_never_expose_code(self):
        candidate = DitoOtpCandidate("123456")
        with self.assertNoLogs(level="DEBUG"):
            self.assertEqual(repr(candidate), "DitoOtpCandidate(<details omitted>)")
            self.assertEqual(str(candidate), "DitoOtpCandidate(<details omitted>)")
        self.assertNotIn("123456", repr(candidate))

    def test_candidate_opaque_even_with_wrong_constructor_type(self):
        candidate = DitoOtpCandidate({"token": "synthetic-private-token"})
        self.assertNotIn("synthetic-private-token", repr(candidate))
        self.assertNotIn("synthetic-private-token", str(candidate))

    def test_candidate_is_immutable_and_has_no_message_fields(self):
        candidate = DitoOtpCandidate("123456")
        with self.assertRaises(FrozenInstanceError):
            candidate._code = "654321"
        self.assertFalse(hasattr(candidate, "__dict__"))
        self.assertFalse(hasattr(candidate, "body"))
        self.assertFalse(hasattr(candidate, "sender"))


if __name__ == "__main__":
    unittest.main()

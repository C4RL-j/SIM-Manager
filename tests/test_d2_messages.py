"""Offline SMS normalization/transport-boundary cases; all values synthetic."""

from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import logging
import threading
import unittest
from unittest.mock import Mock, patch

from sim_manager.devices.d2 import router
from sim_manager.devices.d2.messages import D2MessageClient, MESSAGE_DEADLINE_SECONDS, normalize_messages
from sim_manager.message_models import Message, MessageInbox, MessageIssueCode as Code


PRIVATE_BODY = "SYNTHETIC_PRIVATE_BODY_WITH_FAKE_OTP_246810"
PRIVATE_SENDER = "SYNTHETIC_PRIVATE_SENDER"
PRIVATE_ID = "SYNTHETIC_PRIVATE_ID"


def item(**changes):
    value = {"SmsId": "a", "number": "Example sender", "smsdate": "10-08-2026",
             "smstime": "10:42:00", "content": "Synthetic message text."}
    value.update(changes)
    return value


def response(items=(), *, stringified=False):
    data = {"ItemList": list(items)}
    return {"code": 200, "msg": "ok", "data": json.dumps(data) if stringified else data}


class MessageModelTests(unittest.TestCase):
    def test_models_are_immutable(self):
        for model, name in ((Message(), "body"), (MessageInbox(), "available")):
            with self.subTest(model=type(model).__name__):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(model, name, None)

    def test_models_default_to_empty_unknown_fields(self):
        message = Message()
        self.assertIsNone(message.identity)
        self.assertIsNone(message.sender)
        self.assertIsNone(message.timestamp)
        self.assertEqual(message.body, "")
        inbox = MessageInbox()
        self.assertTrue(inbox.available)
        self.assertFalse(inbox.partial)
        self.assertEqual(inbox.messages, ())

    def test_repr_and_str_omit_private_fields_even_wrongly_typed(self):
        message = Message(PRIVATE_ID, PRIVATE_SENDER, PRIVATE_BODY, PRIVATE_BODY)
        for model in (message, MessageInbox((message,), issues=(PRIVATE_BODY,)),
                      Message(body={PRIVATE_BODY: PRIVATE_SENDER})):
            with self.subTest(model=type(model).__name__):
                for private in (PRIVATE_ID, PRIVATE_SENDER, PRIVATE_BODY):
                    self.assertNotIn(private, repr(model))
                    self.assertNotIn(private, str(model))

    def test_logging_models_never_prints_private_values(self):
        stream = io.StringIO()
        logger = logging.Logger("synthetic-sms-models")
        logger.addHandler(logging.StreamHandler(stream))
        logger.warning("%s %r", Message(body=PRIVATE_BODY), MessageInbox((Message(sender=PRIVATE_SENDER),)))
        self.assertNotIn(PRIVATE_BODY, stream.getvalue())
        self.assertNotIn(PRIVATE_SENDER, stream.getvalue())


class MessageParserTests(unittest.TestCase):
    def test_normal_object_inbox(self):
        inbox = normalize_messages(response([item()]))
        self.assertTrue(inbox.available)
        self.assertFalse(inbox.partial)
        self.assertEqual(len(inbox.messages), 1)
        self.assertEqual(inbox.messages[0].identity, "a")
        self.assertEqual(inbox.messages[0].sender, "Example sender")
        self.assertEqual(inbox.messages[0].timestamp, "10-08-2026 10:42:00")
        self.assertEqual(inbox.messages[0].body, "Synthetic message text.")

    def test_normal_stringified_inbox(self):
        inbox = normalize_messages(response([item()], stringified=True))
        self.assertTrue(inbox.available)
        self.assertEqual(len(inbox.messages), 1)

    def test_zero_messages_requires_explicit_empty_itemlist(self):
        inbox = normalize_messages(response())
        self.assertTrue(inbox.available)
        self.assertFalse(inbox.partial)
        self.assertEqual(inbox.messages, ())

    def test_multiple_messages_preserve_returned_order_without_time_or_id_sort(self):
        values = [item(SmsId="9", smsdate="unparsed-later"),
                  item(SmsId="2", smsdate="unparsed-earlier"), item(SmsId="10", smsdate=None)]
        inbox = normalize_messages(response(values))
        self.assertEqual(tuple(message.identity for message in inbox.messages), ("9", "2", "10"))
        self.assertEqual(inbox.messages[0].timestamp, "unparsed-later 10:42:00")

    def test_malformed_individual_messages_do_not_discard_good_rows(self):
        inbox = normalize_messages(response([item(SmsId="a"), None, 42, "bad", {},
                                              {"future": "unknown"}, item(SmsId="b")]))
        self.assertTrue(inbox.available)
        self.assertTrue(inbox.partial)
        self.assertEqual(tuple(message.identity for message in inbox.messages), ("a", "b"))
        self.assertEqual(inbox.issues, (Code.MALFORMED_ENTRY,))

    def test_all_malformed_entries_are_partial_not_a_verified_empty_response(self):
        inbox = normalize_messages(response([None, {}]))
        self.assertTrue(inbox.available)
        self.assertTrue(inbox.partial)
        self.assertEqual(inbox.messages, ())

    def test_missing_sender_stays_unknown(self):
        value = item()
        del value["number"]
        inbox = normalize_messages(response([value]))
        self.assertIsNone(inbox.messages[0].sender)
        self.assertFalse(inbox.partial)

    def test_blank_sender_stays_unknown(self):
        inbox = normalize_messages(response([item(number="  ")]))
        self.assertIsNone(inbox.messages[0].sender)

    def test_missing_timestamp_stays_unknown(self):
        value = item()
        del value["smsdate"], value["smstime"]
        inbox = normalize_messages(response([value]))
        self.assertIsNone(inbox.messages[0].timestamp)
        self.assertFalse(inbox.partial)

    def test_date_or_time_alone_is_preserved_as_text(self):
        inbox = normalize_messages(response([item(smsdate=None), item(SmsId="b", smstime=None)]))
        self.assertEqual(inbox.messages[0].timestamp, "10:42:00")
        self.assertEqual(inbox.messages[1].timestamp, "10-08-2026")

    def test_timestamp_does_not_guess_timezone_or_parse_arbitrary_content(self):
        inbox = normalize_messages(response([item(smsdate="router date", smstime="router time")]))
        self.assertEqual(inbox.messages[0].timestamp, "router date router time")
        self.assertFalse(inbox.partial)

    def test_empty_or_missing_body_retains_message(self):
        first = item(content="")
        second = item(SmsId="b")
        del second["content"]
        inbox = normalize_messages(response([first, second]))
        self.assertEqual(tuple(message.body for message in inbox.messages), ("", ""))
        self.assertFalse(inbox.partial)

    def test_body_whitespace_and_multiline_content_preserved(self):
        body = "  Synthetic first line\n\tSynthetic second line\r\n  "
        inbox = normalize_messages(response([item(content=body)]))
        self.assertEqual(inbox.messages[0].body, body)

    def test_nonstrings_are_not_coerced_into_private_repr(self):
        inbox = normalize_messages(response([item(number={PRIVATE_SENDER: PRIVATE_BODY},
                                                  content=[PRIVATE_BODY], SmsId=True,
                                                  smsdate=23, smstime=False)]))
        self.assertTrue(inbox.partial)
        message = inbox.messages[0]
        self.assertEqual(message.body, "")
        self.assertIsNone(message.sender)
        self.assertIsNone(message.timestamp)
        self.assertIsNone(message.identity)

    def test_integer_id_is_opaque_text(self):
        inbox = normalize_messages(response([item(SmsId=0)]))
        self.assertEqual(inbox.messages[0].identity, "0")

    def test_pathological_integer_id_is_ignored(self):
        inbox = normalize_messages(response([item(SmsId=2 ** 200)]))
        self.assertIsNone(inbox.messages[0].identity)
        self.assertTrue(inbox.partial)

    def test_exact_duplicate_id_and_message_collapses(self):
        inbox = normalize_messages(response([item(), item()]))
        self.assertEqual(len(inbox.messages), 1)
        self.assertTrue(inbox.partial)
        self.assertEqual(inbox.issues, (Code.DUPLICATE_ID,))

    def test_conflicting_duplicate_id_retains_distinct_rows_in_router_order(self):
        inbox = normalize_messages(response([item(content="Synthetic first"),
                                              item(content="Synthetic second"), item(content="Synthetic first")]))
        self.assertEqual(tuple(message.body for message in inbox.messages), ("Synthetic first", "Synthetic second"))
        self.assertEqual(inbox.issues, (Code.DUPLICATE_ID,))

    def test_rows_without_id_are_not_deduplicated(self):
        inbox = normalize_messages(response([item(SmsId=None), item(SmsId=None)]))
        self.assertEqual(len(inbox.messages), 2)
        self.assertFalse(inbox.partial)

    def test_other_field_difference_with_duplicate_id_retained(self):
        inbox = normalize_messages(response([item(), item(number="Another synthetic sender"),
                                              item(smsdate="Another synthetic date")]))
        self.assertEqual(len(inbox.messages), 3)
        self.assertTrue(inbox.partial)

    def test_unsupported_envelope_shapes_do_not_claim_empty(self):
        for data in ({}, None, [], "null", "[]", '"double encoded"', {"ItemList": {}}, {"ItemList": None}):
            with self.subTest(data_type=type(data).__name__):
                inbox = normalize_messages({"code": 200, "msg": "ok", "data": data})
                self.assertFalse(inbox.available)
                self.assertEqual(inbox.issues, (Code.UNSUPPORTED_RESPONSE,))

    def test_malformed_envelopes_fail_with_closed_code(self):
        for value in (None, [], "bad", {}, {"code": "200"}, {"code": True},
                      {"code": 200, "data": {}}, {"code": 200, "msg": "ok"}):
            with self.subTest(value_type=type(value).__name__):
                inbox = normalize_messages(value)
                self.assertFalse(inbox.available)
                self.assertEqual(inbox.issues, (Code.MALFORMED_RESPONSE,))

    def test_non_success_envelope_omits_arbitrary_response_error(self):
        inbox = normalize_messages({"code": 500, "msg": PRIVATE_BODY, "data": PRIVATE_SENDER})
        self.assertFalse(inbox.available)
        self.assertEqual(inbox.issues, (Code.UNAVAILABLE,))
        self.assertNotIn(PRIVATE_BODY, repr(inbox))

    def test_malformed_data_json_does_not_expose_body_or_decoder_exception(self):
        inbox = normalize_messages({"code": 200, "msg": "ok", "data": '{"ItemList": [' + PRIVATE_BODY})
        self.assertFalse(inbox.available)
        self.assertEqual(inbox.issues, (Code.MALFORMED_RESPONSE,))

    def test_unknown_fields_and_unverified_readed_storage_are_not_copied(self):
        inbox = normalize_messages(response([item(readed="0", storage="SIM", unknown=PRIVATE_BODY)]))
        self.assertFalse(inbox.partial)
        self.assertFalse(hasattr(inbox.messages[0], "is_read"))
        self.assertFalse(hasattr(inbox.messages[0], "storage"))
        self.assertFalse(hasattr(inbox.messages[0], "unknown"))

    def test_unicode_content_is_preserved_without_guessing_an_encoding(self):
        body = "Synthetic café — こんにちは 🙂"
        inbox = normalize_messages(response([item(content=body)], stringified=True))
        self.assertEqual(inbox.messages[0].body, body)
        self.assertFalse(inbox.partial)

    def test_unexpected_bytes_field_is_missing_and_partial(self):
        inbox = normalize_messages(response([item(content=b"synthetic bytes", number=b"example")]))
        self.assertEqual(inbox.messages[0].body, "")
        self.assertIsNone(inbox.messages[0].sender)
        self.assertTrue(inbox.partial)

    def test_surrogates_controls_and_wire_replacement_are_safe_partial_text(self):
        inbox = normalize_messages(response([item(content="Synthetic\ud800\x00\ufffd", number="Example\x7f")]))
        self.assertEqual(inbox.messages[0].body, "Synthetic\ufffd\ufffd\ufffd")
        self.assertEqual(inbox.messages[0].sender, "Example\ufffd")
        self.assertTrue(inbox.partial)

    def test_cancellation_before_parsing_discards_result(self):
        stop = threading.Event()
        stop.set()
        inbox = normalize_messages(response([item()]), stop_event=stop)
        self.assertFalse(inbox.available)
        self.assertEqual(inbox.issues, (Code.CANCELLED,))

    def test_deadline_before_parsing_discards_result(self):
        inbox = normalize_messages(response([item()]), deadline=10, clock=lambda: 10)
        self.assertFalse(inbox.available)
        self.assertEqual(inbox.issues, (Code.TIMEOUT,))

    def test_deadline_between_entries_discards_partial_private_result(self):
        clock = Mock(side_effect=[0, 0, 20])
        inbox = normalize_messages(response([item(), item(SmsId="b")]), deadline=10, clock=clock)
        self.assertFalse(inbox.available)
        self.assertEqual(inbox.messages, ())
        self.assertEqual(inbox.issues, (Code.TIMEOUT,))

    def test_item_count_is_defensively_bounded(self):
        inbox = normalize_messages(response([item(SmsId=None)] * 1001))
        self.assertEqual(len(inbox.messages), 1000)
        self.assertTrue(inbox.partial)

    def test_stringified_data_has_size_bound(self):
        inbox = normalize_messages({"code": 200, "msg": "ok", "data": " " * (router.MAX_RESPONSE_BYTES + 1)})
        self.assertEqual(inbox.issues, (Code.MALFORMED_RESPONSE,))

    def test_oversized_injected_text_field_is_ignored_and_partial(self):
        inbox = normalize_messages(response([item(content="x" * (router.MAX_RESPONSE_BYTES + 1))]))
        self.assertEqual(inbox.messages[0].body, "")
        self.assertTrue(inbox.partial)


class MessageClientTests(unittest.TestCase):
    def test_constructing_client_performs_no_io(self):
        with patch.object(router, "fetch_sms_response") as fetch:
            client = D2MessageClient()
            self.assertIn("details omitted", repr(client))
            fetch.assert_not_called()

    def test_exact_preserved_readonly_transport_contract_forwarded(self):
        fetch = Mock(return_value=response([item()]))
        stop = threading.Event()
        inbox = D2MessageClient(fetch).get_messages(stop_event=stop)
        self.assertTrue(inbox.available)
        fetch.assert_called_once_with("192.168.1.1", 2323, 3, connect_timeout=3.0, response_timeout=30.0,
                                      stop_event=stop, max_response_bytes=router.MAX_RESPONSE_BYTES)

    def test_configured_read_count_changes_only_getter_count(self):
        for count in (1, 7, 100):
            with self.subTest(count=count):
                fetch = Mock(return_value=response([item()]))
                stop = threading.Event()
                client = D2MessageClient(fetch, read_num=count)
                self.assertEqual(client.read_limit, count)
                self.assertTrue(client.get_messages(stop_event=stop).available)
                fetch.assert_called_once_with("192.168.1.1", 2323, count,
                                              connect_timeout=3.0, response_timeout=30.0,
                                              stop_event=stop, max_response_bytes=router.MAX_RESPONSE_BYTES)

    def test_default_and_configured_read_limits_are_read_only(self):
        self.assertEqual(D2MessageClient().read_limit, router.READ_NUM)
        client = D2MessageClient(read_num=100)
        with self.assertRaises(AttributeError):
            client.read_limit = 1
        self.assertEqual(client.read_limit, 100)
        self.assertEqual(router.READ_NUM, 3)

    def test_invalid_read_counts_fail_before_io_without_coercion(self):
        for value in (0, -1, 101, True, False, 3.0, "100", None, [], {}):
            with self.subTest(value_type=type(value).__name__):
                fetch = Mock()
                with self.assertRaisesRegex(ValueError, "integer from 1 to 100"):
                    D2MessageClient(fetch, read_num=value)
                fetch.assert_not_called()

    def test_invalid_private_count_does_not_reach_errors_logs_or_conversion(self):
        class PrivateValue:
            def __str__(self):
                raise AssertionError(PRIVATE_BODY)
            def __repr__(self):
                return PRIVATE_BODY
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            with self.assertRaises(ValueError) as caught:
                D2MessageClient(read_num=PrivateValue())
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn(PRIVATE_BODY, str(caught.exception))
        self.assertNotIn(PRIVATE_BODY, repr(caught.exception))

    def test_larger_read_preserves_cancellation_and_late_result_limit(self):
        stop = threading.Event()
        stop.set()
        fetch = Mock(return_value=response([item()] * 100))
        result = D2MessageClient(fetch, read_num=100).get_messages(stop_event=stop)
        self.assertEqual(result.issues, (Code.CANCELLED,))
        fetch.assert_not_called()
        clock = Mock(side_effect=[0, 0, MESSAGE_DEADLINE_SECONDS + 1])
        result = D2MessageClient(fetch, read_num=100, clock=clock).get_messages()
        self.assertEqual(result.issues, (Code.TIMEOUT,))
        self.assertEqual(result.messages, ())

    def test_real_transport_noise_and_wrapper_remain_behind_device_boundary(self):
        shell = "synthetic shell noise\n" + json.dumps(response([item()], stringified=True)) + "\n# "
        fetch = Mock(side_effect=lambda *args, **kwargs: router.get_sms_response(shell))
        inbox = D2MessageClient(fetch).get_messages()
        self.assertTrue(inbox.available)
        self.assertEqual(len(inbox.messages), 1)

    def test_cancelled_before_fetch_performs_no_io(self):
        stop = threading.Event()
        stop.set()
        fetch = Mock()
        inbox = D2MessageClient(fetch).get_messages(stop_event=stop)
        self.assertEqual(inbox.issues, (Code.CANCELLED,))
        fetch.assert_not_called()

    def test_cancelled_after_fetch_discards_private_messages(self):
        stop = threading.Event()
        def fetch(*args, **kwargs):
            stop.set()
            return response([item(content=PRIVATE_BODY)])
        inbox = D2MessageClient(fetch).get_messages(stop_event=stop)
        self.assertEqual(inbox.issues, (Code.CANCELLED,))
        self.assertEqual(inbox.messages, ())

    def test_late_injected_fetch_discards_private_messages(self):
        clock = Mock(side_effect=[0, 0, MESSAGE_DEADLINE_SECONDS + 1])
        inbox = D2MessageClient(Mock(return_value=response([item()])), clock=clock).get_messages()
        self.assertEqual(inbox.issues, (Code.TIMEOUT,))
        self.assertEqual(inbox.messages, ())

    def test_transport_failures_map_to_closed_codes(self):
        cases = ((router.RouterCancelledError, Code.CANCELLED),
                 (router.RouterTimeoutError, Code.TIMEOUT), (TimeoutError, Code.TIMEOUT),
                 (router.RouterConnectionError, Code.UNREACHABLE),
                 (router.RouterDisconnectedError, Code.UNREACHABLE), (OSError, Code.UNREACHABLE),
                 (router.RouterLoginRequiredError, Code.AUTHENTICATION_REQUIRED),
                 (router.RouterResponseError, Code.MALFORMED_RESPONSE),
                 (ValueError, Code.MALFORMED_RESPONSE), (RuntimeError, Code.UNAVAILABLE))
        for error_type, expected in cases:
            with self.subTest(error_type=error_type.__name__):
                inbox = D2MessageClient(Mock(side_effect=error_type(PRIVATE_BODY))).get_messages()
                self.assertFalse(inbox.available)
                self.assertEqual(inbox.issues, (expected,))
                self.assertEqual(inbox.messages, ())
                self.assertNotIn(PRIVATE_BODY, str(inbox))

    def test_failure_context_and_tracebacks_are_discarded_not_retained(self):
        try:
            raise ValueError(PRIVATE_BODY)
        except ValueError as inner:
            try:
                raise router.RouterResponseError("Synthetic safe outer") from inner
            except router.RouterResponseError as outer:
                saved = outer
        inbox = D2MessageClient(Mock(side_effect=saved)).get_messages()
        self.assertEqual(inbox.issues, (Code.MALFORMED_RESPONSE,))
        self.assertIsNone(saved.__context__)
        self.assertIsNone(saved.__cause__)
        self.assertIsNone(saved.__traceback__)

    def test_no_sms_body_sender_or_fake_otp_in_stdout_stderr_or_logs(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream), self.assertNoLogs(level="DEBUG"):
            inbox = D2MessageClient(Mock(return_value=response([item(content=PRIVATE_BODY, number=PRIVATE_SENDER)]))).get_messages()
            failure = D2MessageClient(Mock(side_effect=RuntimeError(PRIVATE_BODY))).get_messages()
        self.assertEqual(stream.getvalue(), "")
        self.assertTrue(inbox.available)
        self.assertFalse(failure.available)

    def test_cancel_has_priority_over_simultaneous_transport_error(self):
        stop = threading.Event()
        def fetch(*args, **kwargs):
            stop.set()
            raise router.RouterResponseError(PRIVATE_BODY)
        inbox = D2MessageClient(fetch).get_messages(stop_event=stop)
        self.assertEqual(inbox.issues, (Code.CANCELLED,))


if __name__ == "__main__":
    unittest.main()

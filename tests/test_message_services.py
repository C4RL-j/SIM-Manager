"""Offline message services: synthetic values, independent demo/live paths."""

from __future__ import annotations

import ast
import inspect
import threading
import unittest
from unittest.mock import Mock, patch

from sim_manager.devices.d2.messages import D2MessageClient
from sim_manager.message_models import Message, MessageInbox, MessageIssueCode
from sim_manager.services import messages
from sim_manager.services.messages import DemoMessageService, LiveMessageService


class MessageServiceTests(unittest.TestCase):
    def test_live_service_forwards_normalized_result_and_stop_event(self):
        result = MessageInbox((Message(body="Synthetic service message"),))
        client = Mock()
        client.get_messages.return_value = result
        service = LiveMessageService(client)
        stop = threading.Event()
        self.assertIs(service.get_messages(stop_event=stop), result)
        self.assertFalse(service.is_demo)
        client.get_messages.assert_called_once_with(stop_event=stop)

    def test_live_constructing_is_inert_and_repr_is_private(self):
        with patch("sim_manager.devices.d2.router.fetch_sms_response") as fetch:
            service = LiveMessageService()
            self.assertEqual(repr(service), "LiveMessageService(<details omitted>)")
            fetch.assert_not_called()

    def test_live_cancellation_before_call_does_no_fetch(self):
        stop = threading.Event()
        stop.set()
        client = Mock()
        inbox = LiveMessageService(client).get_messages(stop_event=stop)
        self.assertFalse(inbox.available)
        self.assertEqual(inbox.issues, (MessageIssueCode.CANCELLED,))
        client.get_messages.assert_not_called()

    def test_live_cancellation_after_call_discards_result(self):
        stop = threading.Event()
        def get_messages(**kwargs):
            stop.set()
            return MessageInbox((Message(body="Synthetic cancelled message"),))
        client = Mock()
        client.get_messages.side_effect = get_messages
        inbox = LiveMessageService(client).get_messages(stop_event=stop)
        self.assertEqual(inbox.messages, ())
        self.assertEqual(inbox.issues, (MessageIssueCode.CANCELLED,))

    def test_malformed_client_result_is_not_exposed(self):
        client = Mock()
        client.get_messages.return_value = {"content": "Synthetic private body"}
        inbox = LiveMessageService(client).get_messages()
        self.assertFalse(inbox.available)
        self.assertEqual(inbox.issues, (MessageIssueCode.MALFORMED_RESPONSE,))

    def test_live_transport_failure_never_silently_substitutes_demo(self):
        with patch.object(DemoMessageService, "get_messages") as demo:
            service = LiveMessageService(D2MessageClient(Mock(side_effect=ConnectionError("Synthetic private error"))))
            inbox = service.get_messages()
            self.assertFalse(inbox.available)
            self.assertEqual(inbox.messages, ())
            self.assertEqual(inbox.issues, (MessageIssueCode.UNREACHABLE,))
            demo.assert_not_called()

    def test_live_inbox_is_not_cached_between_requests(self):
        first = MessageInbox((Message(body="Synthetic previous"),))
        second = MessageInbox()
        client = Mock()
        client.get_messages.side_effect = [first, second]
        service = LiveMessageService(client)
        self.assertIs(service.get_messages(), first)
        self.assertIs(service.get_messages(), second)
        self.assertEqual(set(vars(service)), {"_client"})

    def test_partial_result_is_preserved_for_ui_decision(self):
        result = MessageInbox((Message(body="Synthetic partial"),), partial=True,
                              issues=(MessageIssueCode.MALFORMED_ENTRY,))
        client = Mock()
        client.get_messages.return_value = result
        self.assertIs(LiveMessageService(client).get_messages(), result)

    def test_injected_client_errors_are_sanitized_by_service(self):
        for error, code in ((TimeoutError, MessageIssueCode.TIMEOUT),
                            (ConnectionError, MessageIssueCode.UNREACHABLE),
                            (ValueError, MessageIssueCode.MALFORMED_RESPONSE),
                            (RuntimeError, MessageIssueCode.UNAVAILABLE)):
            with self.subTest(error_type=error.__name__):
                client = Mock()
                client.get_messages.side_effect = error("Synthetic private message")
                with self.assertNoLogs(level="DEBUG"):
                    inbox = LiveMessageService(client).get_messages()
                self.assertFalse(inbox.available)
                self.assertEqual(inbox.issues, (code,))
                self.assertNotIn("Synthetic private message", repr(inbox))

    def test_demo_is_explicit_synthetic_and_has_no_live_io(self):
        with patch("sim_manager.devices.d2.router.fetch_sms_response") as fetch:
            service = DemoMessageService()
            inbox = service.get_messages()
            self.assertTrue(service.is_demo)
            self.assertTrue(inbox.available)
            self.assertEqual(len(inbox.messages), 2)
            self.assertTrue(all(message.identity.startswith("demo-") for message in inbox.messages))
            self.assertIn("synthetic", inbox.messages[0].body)
            fetch.assert_not_called()

    def test_demo_cancelled_returns_no_messages_and_performs_no_io(self):
        stop = threading.Event()
        stop.set()
        with patch("sim_manager.devices.d2.router.fetch_sms_response") as fetch:
            inbox = DemoMessageService().get_messages(stop_event=stop)
            self.assertFalse(inbox.available)
            self.assertEqual(inbox.messages, ())
            self.assertEqual(inbox.issues, (MessageIssueCode.CANCELLED,))
            fetch.assert_not_called()

    def test_demo_repr_is_opaque(self):
        self.assertEqual(repr(DemoMessageService()), "DemoMessageService(<details omitted>)")

    def test_services_import_no_carrier_regex_session_or_browser(self):
        tree = ast.parse(inspect.getsource(messages))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        for name in imports:
            self.assertFalse(any(word in name.lower() for word in ("dito", "smart", "session", "browser", "re.")))


if __name__ == "__main__":
    unittest.main()

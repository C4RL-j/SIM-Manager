"""Offline inbox GUI/lifecycle tests; every message is explicitly synthetic."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import threading
import time
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QPushButton

from test_desktop import DesktopCase, known_snapshot
from sim_manager.message_models import Message, MessageInbox, MessageIssueCode
from sim_manager.models import DeviceIssue, DeviceState, IssueCode
from sim_manager.ui.main_window import MainWindow


PRIVATE_ERROR = "SYNTHETIC_SMS_EXCEPTION_ONLY"


def synthetic_inbox():
    return MessageInbox(messages=(
        Message(identity="example-one", sender="Sample service", timestamp="2026-10-08 10:42:00", body="Synthetic first message.\nSecond line."),
        Message(identity="example-two", sender="Example sender", timestamp="2026-10-07 11:00:00", body="<b>Synthetic plain text</b>\nhttps://example.invalid/"),
    ))


class ControlledMessageProvider:
    def __init__(self, inbox=None, *, blocked=False, cooperative=True, error=None, demo=False):
        self.inbox = synthetic_inbox() if inbox is None else inbox
        self.blocked = blocked
        self.cooperative = cooperative
        self.error = error
        self.is_demo = demo
        self.started = threading.Event()
        self.finished = threading.Event()
        self.release = threading.Event()
        self.calls = []

    def get_messages(self, *, stop_event=None):
        self.calls.append((threading.get_ident(), stop_event))
        self.started.set()
        try:
            deadline = time.monotonic() + 2.0
            while self.blocked and not self.release.is_set():
                if self.cooperative and stop_event is not None and stop_event.is_set():
                    return MessageInbox(available=False, issues=(MessageIssueCode.CANCELLED,))
                if time.monotonic() >= deadline:
                    raise TimeoutError(PRIVATE_ERROR)
                self.release.wait(0.005)
            if self.error is not None:
                raise self.error
            return self.inbox
        finally:
            self.finished.set()


class MessageGuiTests(DesktopCase):
    def message_provider(self, *args, **kwargs):
        provider = ControlledMessageProvider(*args, **kwargs)
        self.providers.append(provider)
        return provider

    def message_window(self, provider=None, *, demo=False, snapshot_provider=None):
        if provider is None:
            provider = self.message_provider(demo=demo)
        snapshot_provider = snapshot_provider or self.provider()
        window = MainWindow(snapshot_provider, demo=demo, message_provider=provider)
        self.windows.append(window)
        window.show()
        return window

    def load_messages(self, window):
        window.navigation.setCurrentRow(2)
        self.wait_until(lambda: not window.messages_controller.busy)

    def test_opening_messages_loads_once_independently_of_http_authentication(self):
        provider = self.message_provider()
        window = self.message_window(provider)
        window.render_snapshot(DeviceState(errors=(DeviceIssue("sim", IssueCode.AUTHENTICATION_REQUIRED),)))
        self.assertEqual(provider.calls, [])
        self.load_messages(window)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(window.messages_page.message_list.count(), 2)
        self.assertEqual(window.messages_page.status_label.text(), "2 messages · Inbox loaded from router")
        self.assertEqual(window.status_label.text(), "Authentication required")
        self.assertFalse(window.refresh_controller.busy)
        for page in (4, 0, 2):
            window.navigation.setCurrentRow(page)
        self.assertEqual(len(provider.calls), 1)

    def test_single_click_selects_but_double_click_and_enter_open_plain_text_details(self):
        window = self.message_window()
        self.load_messages(window)
        page = window.messages_page
        selected = []
        page.message_selected.connect(selected.append)
        rectangle = page.message_list.visualItemRect(page.message_list.item(1))
        QTest.mouseClick(page.message_list.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
        self.assertIs(selected[-1], page._messages[1])
        self.assertIsNone(page.details_dialog)
        for old_preview in ("sender_label", "timestamp_label", "content_view"):
            self.assertFalse(hasattr(page, old_preview))
        self.assertEqual(page.findChildren(QPlainTextEdit), [])
        QTest.mouseDClick(page.message_list.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
        self.wait_until(lambda: page.details_dialog is not None)
        details = page.details_dialog
        self.assertEqual(details.sender_label.text(), "Example sender")
        self.assertEqual(details.timestamp_label.text(), "Oct 7, 2026 · 11:00 AM")
        self.assertEqual(details.content_view.toPlainText(), "<b>Synthetic plain text</b>\nhttps://example.invalid/")
        self.assertTrue(details.content_view.isReadOnly())
        for label in (details.sender_label, details.timestamp_label, page.status_label):
            self.assertEqual(label.textFormat(), Qt.TextFormat.PlainText)
        QTest.keyClick(details, Qt.Key.Key_Escape)
        self.wait_until(lambda: page.details_dialog is None)
        page.message_list.setFocus()
        QTest.keyClick(page.message_list, Qt.Key.Key_Return)
        self.wait_until(lambda: page.details_dialog is not None)
        self.assertEqual(page.details_dialog.content_view.toPlainText(), "<b>Synthetic plain text</b>\nhttps://example.invalid/")
        page.details_dialog.close_button.click()
        self.wait_until(lambda: page.details_dialog is None)

    def test_list_preview_is_compact_but_opened_content_remains_complete(self):
        body = "Synthetic sentence. " * 30
        provider = self.message_provider(MessageInbox(messages=(Message(sender="Sample", body=body),)))
        window = self.message_window(provider)
        self.load_messages(window)
        self.assertLess(len(window.messages_page.message_list.item(0).text()), len(body))
        self.assertIsNone(window.messages_page.details_dialog)
        window.messages_page.open_selected_message()
        self.assertEqual(window.messages_page.details_dialog.content_view.toPlainText(), body)

    def test_two_line_rows_and_inbox_expand_without_horizontal_overflow(self):
        messages = tuple(Message(
            sender="Synthetic service " + "W" * 80,
            timestamp=f"2026-10-08 10:{minute:02d}:00",
            body="Synthetic preview " * 40,
        ) for minute in range(20))
        window = self.message_window(self.message_provider(MessageInbox(messages=messages)))
        window.resize(840, 600)
        self.load_messages(window)
        page = window.messages_page
        self.application.processEvents()
        small_height = page.message_list.height()
        first = page.message_list.item(0)
        self.assertEqual(first.text().count("\n"), 1)
        self.assertGreaterEqual(page.message_list.visualItemRect(first).height(),
                                2 * page.message_list.fontMetrics().height())
        self.assertLessEqual(page.message_list.visualItemRect(first).height(),
                             3 * page.message_list.fontMetrics().lineSpacing() + 40)
        self.assertEqual(page.message_list.horizontalScrollBar().maximum(), 0)
        scroller = window.pages.widget(2)
        self.assertEqual(scroller.horizontalScrollBar().maximum(), 0)
        window.resize(1000, 850)
        self.application.processEvents()
        self.assertGreater(page.message_list.height(), small_height + 100)
        self.assertEqual(page.message_list.horizontalScrollBar().maximum(), 0)
        self.assertEqual(scroller.horizontalScrollBar().maximum(), 0)
        self.assertIsNone(page.details_dialog)

    def test_newest_first_sort_requires_all_comparable_unambiguous_iso_timestamps(self):
        window = self.message_window()
        self.load_messages(window)
        page = window.messages_page

        def display_order(timestamps):
            rows = tuple(Message(identity=str(index), timestamp=timestamp, body="Synthetic body")
                         for index, timestamp in enumerate(timestamps))
            page.render(MessageInbox(messages=rows))
            return [message.identity for message in page._messages]

        self.assertEqual(display_order(("2026-10-07 11:00:00", "2026-10-08 10:00:00",
                                        "2026-10-08 10:00:00")), ["1", "2", "0"])
        self.assertEqual(display_order(("2026-10-08T12:00:00+08:00", "2026-10-08T05:00:00Z")),
                         ["1", "0"])
        for timestamps in (
            ("2026-10-07 11:00:00", "08/10/2026 10:00:00"),
            ("2026-10-07 11:00:00", None),
            ("2026-10-07 11:00:00", "2026-10-08T10:00:00+08:00"),
            ("2026-10-07 11:00:00", "2026-02-31 10:00:00"),
            ("2026-10-07T11:00:00Z", "2026-10-08T10:00:00-00:00"),
            ("2026-10-07T11:00:00Z", "2026-10-08T10:00:00-0000"),
            ("2026-10-07T11:00:00Z", "2026-10-08T10:00:00+08:99"),
        ):
            with self.subTest(timestamps=timestamps):
                self.assertEqual(display_order(timestamps), ["0", "1"])

    def test_missing_fields_and_empty_body_have_safe_friendly_labels(self):
        window = self.message_window(self.message_provider(MessageInbox(messages=(Message(),))))
        self.load_messages(window)
        page = window.messages_page
        self.assertIn("Unknown sender", page.message_list.item(0).text())
        self.assertIn("Unknown time", page.message_list.item(0).text())
        self.assertIn("(Empty message)", page.message_list.item(0).text())
        self.assertIsNone(page.details_dialog)
        page.open_selected_message()
        self.assertEqual(page.details_dialog.content_view.toPlainText(), "")
        self.assertEqual(page.details_dialog.sender_label.text(), "Unknown sender")
        self.assertEqual(page.details_dialog.timestamp_label.text(), "Unknown time")

    def test_zero_messages_clears_a_previous_inbox_only_on_success(self):
        provider = self.message_provider()
        window = self.message_window(provider)
        self.load_messages(window)
        page = window.messages_page
        page.open_selected_message()
        previous_details = page.details_dialog
        cleared = []
        previous_details.finished.connect(lambda _: cleared.append(previous_details.content_view.toPlainText() == ""))
        previous_refresh = page.last_refreshed_at
        provider.inbox = MessageInbox()
        self.assertTrue(window.start_messages_refresh())
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertEqual(window.messages_page.message_list.count(), 0)
        self.assertIsNone(page.details_dialog)
        self.assertEqual(cleared, [True])
        self.assertGreater(page.last_refreshed_at, previous_refresh)
        self.assertEqual(window.messages_page.empty_label.text(), "No messages")
        self.assertTrue(window.messages_page.empty_label.isVisible())

    def test_messages_refresh_runs_off_thread_and_delivers_on_qt_thread_without_overlap(self):
        provider = self.message_provider(blocked=True)
        window = self.message_window(provider)
        main_thread = threading.get_ident()
        deliveries = []
        window.messages_controller.inbox_ready.connect(lambda _: deliveries.append(threading.get_ident()))
        self.assertTrue(window.start_messages_refresh())
        self.wait_until(provider.started.is_set)
        self.assertNotEqual(provider.calls[0][0], main_thread)
        self.assertFalse(window.start_messages_refresh())
        self.assertEqual(len(provider.calls), 1)
        self.assertFalse(window.messages_page.refresh_button.isEnabled())
        self.assertFalse(window.messages_page.cancel_button.isVisible())
        # The page is hidden here; its cancel action becomes visible on navigation.
        window.navigation.setCurrentRow(2)
        self.assertTrue(window.messages_page.cancel_button.isVisible())
        provider.release.set()
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertEqual(deliveries, [main_thread])
        self.assertTrue(window.messages_page.refresh_button.isEnabled())

    def test_independent_overview_and_messages_refreshes_do_not_share_cancellation(self):
        overview = self.provider(known_snapshot(), blocked=True)
        inbox = self.message_provider(blocked=True)
        window = self.message_window(inbox, snapshot_provider=overview)
        window.start_refresh()
        window.start_messages_refresh()
        self.wait_until(lambda: overview.started.is_set() and inbox.started.is_set())
        window._cancel_messages_refresh()
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertTrue(window.refresh_controller.busy)
        self.assertFalse(overview.calls[0][1].is_set())
        overview.release.set()
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(self.values(window)["sim_state"], "Ready")

    def test_refresh_button_updates_messages_without_overview_calls(self):
        provider = self.message_provider()
        overview = self.provider()
        window = self.message_window(provider, snapshot_provider=overview)
        self.assertIsNone(window.messages_page.last_refreshed_at)
        before = datetime.now(timezone.utc)
        self.load_messages(window)
        page = window.messages_page
        self.assertIsInstance(page.last_refreshed_at, datetime)
        self.assertIsNotNone(page.last_refreshed_at.utcoffset())
        self.assertGreaterEqual(page.last_refreshed_at, before)
        self.assertLessEqual(page.last_refreshed_at, datetime.now(timezone.utc))
        self.assertTrue(page.last_refresh_label.text())
        previous_refresh = page.last_refreshed_at
        page.open_selected_message()
        previous_details = page.details_dialog
        cleared = []
        previous_details.finished.connect(lambda _: cleared.append(previous_details.content_view.toPlainText() == ""))
        provider.inbox = MessageInbox(messages=(Message(sender="Another sample", body="Synthetic replacement"),))
        QTest.mouseClick(window.messages_page.refresh_button, Qt.MouseButton.LeftButton)
        self.wait_until(lambda: len(provider.calls) == 2 and not window.messages_controller.busy)
        self.assertEqual(window.messages_page.message_list.count(), 1)
        self.assertGreater(page.last_refreshed_at, previous_refresh)
        self.assertIsNone(page.details_dialog)
        self.assertEqual(cleared, [True])
        page.open_selected_message()
        self.assertEqual(page.details_dialog.content_view.toPlainText(), "Synthetic replacement")
        self.assertEqual(overview.calls, [])

    def test_closed_failure_states_preserve_existing_messages_and_selection(self):
        provider = self.message_provider()
        window = self.message_window(provider)
        self.load_messages(window)
        page = window.messages_page
        page.message_list.setCurrentRow(1)
        page.open_selected_message()
        details = page.details_dialog
        successful_refresh = page.last_refreshed_at
        successful_label = page.last_refresh_label.text()
        expected = {
            MessageIssueCode.UNREACHABLE: "Router unavailable",
            MessageIssueCode.UNAVAILABLE: "SMS service unavailable",
            MessageIssueCode.TIMEOUT: "Messages request timed out",
            MessageIssueCode.AUTHENTICATION_REQUIRED: "SMS authentication required",
            MessageIssueCode.MALFORMED_RESPONSE: "Messages response could not be read",
            MessageIssueCode.UNSUPPORTED_RESPONSE: "SMS response is not supported",
        }
        for code, message in expected.items():
            with self.subTest(code=code):
                provider.inbox = MessageInbox(available=False, issues=(code,))
                window.start_messages_refresh()
                self.wait_until(lambda: not window.messages_controller.busy)
                self.assertEqual(window.messages_page.status_label.text(), message)
                self.assertEqual(window.messages_page.message_list.count(), 2)
                self.assertEqual(window.messages_page.message_list.currentRow(), 1)
                self.assertIs(page.details_dialog, details)
                self.assertEqual(details.sender_label.text(), "Example sender")
                self.assertEqual(page.last_refreshed_at, successful_refresh)
                self.assertEqual(page.last_refresh_label.text(), successful_label)

    def test_partial_result_renders_readable_rows_and_warns(self):
        provider = self.message_provider(MessageInbox(messages=(Message(body="Synthetic readable row"),), partial=True, issues=(MessageIssueCode.MALFORMED_ENTRY,)))
        window = self.message_window(provider)
        self.load_messages(window)
        self.assertEqual(window.messages_page.message_list.count(), 1)
        self.assertEqual(window.messages_page.status_label.text(), "Some messages could not be read")
        self.assertIsInstance(window.messages_page.last_refreshed_at, datetime)

    def test_unreadable_partial_does_not_claim_a_previous_inbox_is_empty(self):
        provider = self.message_provider()
        window = self.message_window(provider)
        self.load_messages(window)
        previous_refresh = window.messages_page.last_refreshed_at
        previous_label = window.messages_page.last_refresh_label.text()
        provider.inbox = MessageInbox(partial=True, issues=(MessageIssueCode.MALFORMED_ENTRY,))
        window.start_messages_refresh()
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertEqual(window.messages_page.message_list.count(), 2)
        self.assertEqual(window.messages_page.status_label.text(), "Some messages could not be read")
        self.assertEqual(window.messages_page.last_refreshed_at, previous_refresh)
        self.assertEqual(window.messages_page.last_refresh_label.text(), previous_label)

    def test_cancellation_preserves_inbox_and_blocks_late_success(self):
        provider = self.message_provider()
        window = self.message_window(provider)
        self.load_messages(window)
        previous_refresh = window.messages_page.last_refreshed_at
        previous_label = window.messages_page.last_refresh_label.text()
        provider.blocked = True
        window.start_messages_refresh()
        self.wait_until(lambda: len(provider.calls) == 2)
        QTest.mouseClick(window.messages_page.cancel_button, Qt.MouseButton.LeftButton)
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertTrue(provider.calls[-1][1].is_set())
        self.assertEqual(window.messages_page.message_list.count(), 2)
        self.assertEqual(window.messages_page.status_label.text(), "Messages refresh cancelled")
        self.assertTrue(window.messages_page.refresh_button.isEnabled())
        self.assertEqual(window.messages_page.last_refreshed_at, previous_refresh)
        self.assertEqual(window.messages_page.last_refresh_label.text(), previous_label)

    def test_cancel_after_worker_finishes_discards_queued_result(self):
        provider = self.message_provider()
        window = self.message_window(provider)
        window.start_messages_refresh()
        self.assertTrue(provider.finished.wait(0.5))
        window.messages_controller.cancel()
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertEqual(window.messages_page.message_list.count(), 0)
        self.assertEqual(window.messages_page.status_label.text(), "Messages refresh cancelled")
        self.assertIsNone(window.messages_page.last_refreshed_at)

    def test_unknown_worker_exceptions_never_print_or_display_private_text(self):
        for error in (RuntimeError(PRIVATE_ERROR), SystemExit(PRIVATE_ERROR), TimeoutError(PRIVATE_ERROR)):
            provider = self.message_provider(error=error)
            window = self.message_window(provider)
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(output), patch("threading.excepthook") as hook:
                self.load_messages(window)
            hook.assert_not_called()
            self.assertNotIn(PRIVATE_ERROR, output.getvalue() + self.displayed_text(window))
            self.assertEqual(window.messages_page.message_list.count(), 0)
            self.assertIsNone(window.messages_page.last_refreshed_at)

    def test_wrong_or_mistyped_normalized_result_fails_safely(self):
        for inbox in ({"private": PRIVATE_ERROR}, MessageInbox(messages=None)):
            window = self.message_window(self.message_provider(inbox))
            self.load_messages(window)
            self.assertEqual(window.messages_page.status_label.text(), "Messages response could not be read")
            self.assertNotIn(PRIVATE_ERROR, self.displayed_text(window))

    def test_thread_start_failure_is_safe_and_retryable(self):
        provider = self.message_provider()
        window = self.message_window(provider)
        with patch("sim_manager.ui.messages_refresh.Thread.start", side_effect=RuntimeError(PRIVATE_ERROR)):
            self.assertFalse(window.start_messages_refresh())
        self.assertFalse(window.messages_controller.busy)
        self.assertEqual(window.messages_page.status_label.text(), "SMS service unavailable")
        self.assertEqual(provider.calls, [])
        self.assertTrue(window.start_messages_refresh())
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertEqual(window.messages_page.message_list.count(), 2)

    def test_demo_messages_require_explicit_demo_and_keep_badge_on_failure(self):
        provider = self.message_provider(demo=True)
        with self.assertRaises(ValueError):
            MainWindow(self.provider(), message_provider=provider)
        self.assertEqual(provider.calls, [])
        window = self.message_window(provider, demo=True)
        self.load_messages(window)
        self.assertTrue(window.demo_label.isVisible())
        self.assertFalse(window.live_label.isVisible())
        self.assertEqual(window.messages_page.status_label.text(), "Demo messages • Router not connected")
        provider.error = RuntimeError(PRIVATE_ERROR)
        window.start_messages_refresh()
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertTrue(window.demo_label.isVisible())
        self.assertEqual(window.messages_page.message_list.count(), 2)

    def test_live_failure_never_substitutes_demo_messages(self):
        provider = self.message_provider(MessageInbox(available=False, issues=(MessageIssueCode.UNAVAILABLE,)))
        window = self.message_window(provider)
        self.load_messages(window)
        self.assertEqual(window.messages_page.message_list.count(), 0)
        self.assertTrue(window.demo_label.isHidden())
        self.assertIsNone(window.messages_page.last_refreshed_at)

    def test_demo_mode_cannot_start_an_injected_live_message_provider(self):
        provider = self.message_provider()
        with self.assertRaises(ValueError):
            MainWindow(self.provider(), demo=True, message_provider=provider)
        self.assertEqual(provider.calls, [])

    def test_no_message_provider_disables_fetch_without_device_construction(self):
        window = self.window()
        window.navigation.setCurrentRow(2)
        self.assertIsNone(window.messages_controller)
        self.assertFalse(window.start_messages_refresh())
        self.assertFalse(window.messages_page.refresh_button.isEnabled())
        self.assertEqual(window.messages_page.status_label.text(), "SMS service unavailable")

    def test_close_cancels_both_workers_clears_private_widgets_and_blocks_future_work(self):
        overview = self.provider(known_snapshot(), blocked=True)
        provider = self.message_provider()
        window = self.message_window(provider, snapshot_provider=overview)
        self.load_messages(window)
        window.messages_page.open_selected_message()
        details = window.messages_page.details_dialog
        cleared = []
        details.finished.connect(lambda _: cleared.append(details.content_view.toPlainText() == ""))
        provider.blocked = True
        provider.finished.clear()
        window.start_refresh()
        window.start_messages_refresh()
        self.wait_until(lambda: overview.started.is_set() and len(provider.calls) == 2)
        started = time.monotonic()
        window.close()
        self.assertLess(time.monotonic() - started, 1.3)
        self.assertTrue(provider.finished.is_set())
        self.assertTrue(overview.finished.is_set())
        self.assertTrue(provider.calls[-1][1].is_set())
        self.assertTrue(overview.calls[-1][1].is_set())
        self.assertEqual(window.messages_page.message_list.count(), 0)
        self.assertIsNone(window.messages_page.details_dialog)
        self.assertEqual(cleared, [True])
        self.assertIsNone(window.messages_page.last_refreshed_at)
        self.assertEqual(window.messages_page._messages, ())
        self.assertTrue(window.messages_controller._output.empty())
        self.assertFalse(window.start_messages_refresh())
        self.assertTrue(window.shutdown())

    def test_noncooperative_worker_shutdown_detaches_queue_and_discards_late_data(self):
        provider = self.message_provider(blocked=True, cooperative=False)
        window = self.message_window(provider)
        window.start_messages_refresh()
        self.wait_until(provider.started.is_set)
        old_output = window.messages_controller._output
        started = time.monotonic()
        self.assertFalse(window.messages_controller.shutdown(timeout=0.01))
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertIsNot(window.messages_controller._output, old_output)
        self.assertTrue(window.messages_controller._output.empty())
        provider.release.set()
        self.wait_until(provider.finished.is_set)
        self.assertEqual(window.messages_page.message_list.count(), 0)
        self.assertTrue(window.messages_controller._output.empty())
        self.assertTrue(window.messages_controller.shutdown())

    def test_window_shutdown_shares_one_join_budget_across_two_blocked_workers(self):
        overview = self.provider(known_snapshot(), blocked=True, cooperative=False)
        provider = self.message_provider(blocked=True, cooperative=False)
        window = self.message_window(provider, snapshot_provider=overview)
        window.start_refresh()
        window.start_messages_refresh()
        self.wait_until(lambda: overview.started.is_set() and provider.started.is_set())
        started = time.monotonic()
        self.assertFalse(window.shutdown())
        self.assertLess(time.monotonic() - started, 1.3)
        self.assertTrue(overview.calls[0][1].is_set())
        self.assertTrue(provider.calls[0][1].is_set())
        repeated = time.monotonic()
        self.assertFalse(window.shutdown())
        self.assertLess(time.monotonic() - repeated, 0.2)
        overview.release.set()
        provider.release.set()
        self.wait_until(lambda: overview.finished.is_set() and provider.finished.is_set())
        self.assertTrue(window.shutdown())
        self.assertEqual(window.messages_page.message_list.count(), 0)
        self.assertTrue(window.messages_controller._output.empty())

    def test_message_actions_remain_read_only_and_limit_is_disclosed(self):
        window = self.message_window()
        page = window.messages_page
        self.assertEqual({button.text() for button in page.findChildren(QPushButton)}, {"Refresh", "Cancel"})
        self.assertTrue(any("Up to 3 messages" in label.text() for label in page.findChildren(QLabel)))

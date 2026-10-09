"""In-memory, carrier-neutral SMS providers; no credentials or persistence.

A future carrier matcher may consume individual normalized Message values.
Generic retrieval never imports a carrier matcher, OTP regex, or HTTP session.
"""

from __future__ import annotations

from threading import Event
from typing import Protocol

from sim_manager.devices.d2.messages import D2MessageClient
from sim_manager.message_models import Message, MessageInbox, MessageIssueCode


class MessageProvider(Protocol):
    is_demo: bool

    @property
    def read_limit(self) -> int:
        ...

    def get_messages(self, *, stop_event: Event | None = None) -> MessageInbox:
        ...


class LiveMessageService:
    """Expose only normalized SMS; each call uses the independent getter."""

    is_demo = False

    def __init__(self, client: D2MessageClient | None = None) -> None:
        self._client = client if client is not None else D2MessageClient(read_num=20)

    def __repr__(self) -> str:
        return "LiveMessageService(<details omitted>)"

    @property
    def read_limit(self) -> int:
        try:
            value = getattr(self._client, "read_limit", 3)
        except Exception:
            return 3
        return value if type(value) is int and 1 <= value <= 100 else 3

    def get_messages(self, *, stop_event: Event | None = None) -> MessageInbox:
        if stop_event is not None and stop_event.is_set():
            return MessageInbox(available=False, issues=(MessageIssueCode.CANCELLED,))
        # The device client sanitizes transport failures; the service never
        # caches raw envelopes or messages and never substitutes demo data.
        failure: MessageIssueCode | None = None
        result: object = None
        try:
            result = self._client.get_messages(stop_event=stop_event)
        except TimeoutError:
            failure = MessageIssueCode.TIMEOUT
        except ConnectionError:
            failure = MessageIssueCode.UNREACHABLE
        except ValueError:
            failure = MessageIssueCode.MALFORMED_RESPONSE
        except Exception:
            # An injected client's raw error must not cross the service/UI
            # boundary either. No exception text or object is retained.
            failure = MessageIssueCode.UNAVAILABLE
        if stop_event is not None and stop_event.is_set():
            return MessageInbox(available=False, issues=(MessageIssueCode.CANCELLED,))
        if failure is not None:
            return MessageInbox(available=False, issues=(failure,))
        if not isinstance(result, MessageInbox):
            return MessageInbox(available=False, issues=(MessageIssueCode.MALFORMED_RESPONSE,))
        return result


class DemoMessageService:
    """Explicit synthetic inbox; never connects or falls back to live mode."""

    is_demo = True
    read_limit = 2

    def __repr__(self) -> str:
        return "DemoMessageService(<details omitted>)"

    def get_messages(self, *, stop_event: Event | None = None) -> MessageInbox:
        if stop_event is not None and stop_event.is_set():
            return MessageInbox(available=False, issues=(MessageIssueCode.CANCELLED,))
        return MessageInbox(messages=(
            Message("demo-one", "Example sender", "Demo date 10:42",
                    "This is a synthetic demonstration message. No router was contacted."),
            Message("demo-two", "Sample service", "Demo date 09:15",
                    "Select a message to read its full content. Demo messages are kept only in memory."),
        ))

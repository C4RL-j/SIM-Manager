"""Read-only D2 SMS normalization over the preserved Telnet/UBus getter.

This module has no HTTP-session or carrier dependency. Known keys are evidenced
by the legacy inbox consumer; readed/storage meanings have not been verified.
Messages retain router order and date/time text without timezone inference.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from threading import Event

from sim_manager.message_models import Message, MessageInbox, MessageIssueCode

from . import router


# Existing phase limits total under 36 seconds, including bounded sends and
# normalization. This additionally discards late injected results; an arbitrary
# injected fetcher must itself honor transport cancellation and phase bounds.
MESSAGE_DEADLINE_SECONDS = 36.0
_MAX_ITEMS = 1000
_KNOWN_FIELDS = frozenset({"SmsId", "number", "smsdate", "smstime", "content"})


def _failure(code: MessageIssueCode) -> MessageInbox:
    return MessageInbox(available=False, issues=(code,))


def _interruption(
    stop_event: Event | None, deadline: float | None, clock: Callable[[], float],
) -> MessageIssueCode | None:
    if stop_event is not None and stop_event.is_set():
        return MessageIssueCode.CANCELLED
    if deadline is not None and clock() >= deadline:
        return MessageIssueCode.TIMEOUT
    return None


def _text(value: object, *, multiline: bool = False) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    if type(value) is not str:
        return None, True
    if len(value) > router.MAX_RESPONSE_BYTES:
        return None, True
    # The transport already decodes unknown wire bytes with replacement. Also
    # replace lone JSON surrogates and unsafe controls before plain-text UI use.
    result = "".join(
        "\ufffd" if (0xD800 <= ord(ch) <= 0xDFFF or ord(ch) == 127
                     or (ord(ch) < 32 and not (multiline and ch in "\n\r\t"))) else ch
        for ch in value
    )
    malformed = result != value or "\ufffd" in result
    if not multiline:
        result = result.strip()
    return result or ("" if multiline else None), malformed


def normalize_messages(
    response: object,
    *,
    stop_event: Event | None = None,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> MessageInbox:
    """Normalize one selected envelope, isolating malformed individual entries.

    Only explicit ItemList=[] proves empty. Unknown firmware shapes report
    unsupported rather than silently showing an empty inbox. Exact duplicate
    ID/content rows collapse; conflicting duplicate IDs retain every message.
    """
    interrupted = _interruption(stop_event, deadline, clock)
    if interrupted is not None:
        return _failure(interrupted)
    if type(response) is not dict or type(response.get("code")) is not int:
        return _failure(MessageIssueCode.MALFORMED_RESPONSE)
    if response["code"] != 200:
        return _failure(MessageIssueCode.UNAVAILABLE)
    if response.get("msg") != "ok" or "data" not in response:
        return _failure(MessageIssueCode.MALFORMED_RESPONSE)
    data = response["data"]
    if type(data) is str:
        if len(data) > router.MAX_RESPONSE_BYTES:
            return _failure(MessageIssueCode.MALFORMED_RESPONSE)
        try:
            data = json.loads(data)
        except (ValueError, RecursionError):
            # No JSONDecodeError (and its private .doc) crosses this boundary.
            return _failure(MessageIssueCode.MALFORMED_RESPONSE)
    if type(data) is not dict or "ItemList" not in data:
        return _failure(MessageIssueCode.UNSUPPORTED_RESPONSE)
    items = data["ItemList"]
    if type(items) is not list:
        return _failure(MessageIssueCode.UNSUPPORTED_RESPONSE)

    messages: list[Message] = []
    issues: list[MessageIssueCode] = []
    identities: dict[str, set[tuple[str | None, str | None, str]]] = {}

    def issue(code: MessageIssueCode) -> None:
        if code not in issues:
            issues.append(code)

    if len(items) > _MAX_ITEMS:
        issue(MessageIssueCode.MALFORMED_ENTRY)
    for item in items[:_MAX_ITEMS]:
        interrupted = _interruption(stop_event, deadline, clock)
        if interrupted is not None:
            return _failure(interrupted)
        if type(item) is not dict or not _KNOWN_FIELDS.intersection(item):
            issue(MessageIssueCode.MALFORMED_ENTRY)
            continue
        identity_value = item.get("SmsId")
        if type(identity_value) is int:
            # Router IDs are opaque. Bounded conversion avoids pathological
            # integer inputs without interpreting numeric sort order.
            identity_value = str(identity_value) if identity_value.bit_length() <= 128 else None
            if identity_value is None:
                issue(MessageIssueCode.MALFORMED_ENTRY)
        identity, identity_bad = _text(identity_value)
        sender, sender_bad = _text(item.get("number"))
        date, date_bad = _text(item.get("smsdate"))
        time_text, time_bad = _text(item.get("smstime"))
        body, body_bad = _text(item.get("content"), multiline=True)
        if any((identity_bad, sender_bad, date_bad, time_bad, body_bad)):
            issue(MessageIssueCode.MALFORMED_ENTRY)
        timestamp = " ".join(part for part in (date, time_text) if part) or None
        message = Message(identity, sender, timestamp, body or "")
        if identity is not None:
            signature = (message.sender, message.timestamp, message.body)
            previous = identities.setdefault(identity, set())
            if previous:
                issue(MessageIssueCode.DUPLICATE_ID)
            if signature in previous:
                continue
            previous.add(signature)
        messages.append(message)
    interrupted = _interruption(stop_event, deadline, clock)
    if interrupted is not None:
        return _failure(interrupted)
    return MessageInbox(tuple(messages), partial=bool(issues), issues=tuple(issues))


def _discard_exception(error: BaseException) -> None:
    """Drop private response/OS context retained by transport failures.

    The transport's original behavior is preserved. No exception, traceback,
    cause or context is retained by the normalized result or this client.
    """
    pending = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        pending.extend(value for value in (current.__context__, current.__cause__) if value is not None)
        current.__traceback__ = None
        current.__context__ = None
        current.__cause__ = None


class D2MessageClient:
    """A normalized read-only inbox client, independent of admin HTTP login."""

    def __init__(
        self, fetcher: Callable[..., object] | None = None,
        *, read_num: int = router.READ_NUM,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if type(read_num) is not int or not 1 <= read_num <= 100:
            # Configuration errors must not format a supplied private value.
            raise ValueError("Message read limit must be an integer from 1 to 100.")
        self._fetcher = fetcher if fetcher is not None else router.fetch_sms_response
        self._read_num = read_num
        self._clock = clock

    def __repr__(self) -> str:
        return "D2MessageClient(<details omitted>)"

    @property
    def read_limit(self) -> int:
        return self._read_num

    def get_messages(self, *, stop_event: Event | None = None) -> MessageInbox:
        deadline = self._clock() + MESSAGE_DEADLINE_SECONDS
        interrupted = _interruption(stop_event, deadline, self._clock)
        if interrupted is not None:
            return _failure(interrupted)
        response: object = None
        failure: MessageIssueCode | None = None
        try:
            response = self._fetcher(
                router.ROUTER_HOST, router.ROUTER_PORT, self._read_num,
                connect_timeout=3.0, response_timeout=30.0,
                stop_event=stop_event, max_response_bytes=router.MAX_RESPONSE_BYTES,
            )
        except Exception as error:
            if isinstance(error, router.RouterCancelledError):
                failure = MessageIssueCode.CANCELLED
            elif isinstance(error, (router.RouterTimeoutError, TimeoutError)):
                failure = MessageIssueCode.TIMEOUT
            elif isinstance(error, router.RouterLoginRequiredError):
                failure = MessageIssueCode.AUTHENTICATION_REQUIRED
            elif isinstance(error, (router.RouterConnectionError, ConnectionError, OSError)):
                failure = MessageIssueCode.UNREACHABLE
            elif isinstance(error, (router.RouterResponseError, ValueError)):
                failure = MessageIssueCode.MALFORMED_RESPONSE
            else:
                failure = MessageIssueCode.UNAVAILABLE
            _discard_exception(error)
        interrupted = _interruption(stop_event, deadline, self._clock)
        if interrupted is not None:
            return _failure(interrupted)
        if failure is not None:
            return _failure(failure)
        return normalize_messages(response, stop_event=stop_event, deadline=deadline, clock=self._clock)

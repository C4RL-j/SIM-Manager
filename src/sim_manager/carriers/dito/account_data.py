"""Strict boundary for sanitized account values from the official page client.

Raw responses, subscriber identifiers and session material stay inside the page.
Only the bounded display schema below may cross into neutral account models.
"""

from datetime import datetime, timezone
import json

from sim_manager.account_models import (
    AccountBucket, AccountData, AccountDataIssue, AccountDataResult, AccountPromo,
    MAX_ACCOUNT_RETRY_SECONDS,
)


_FIELDS = frozenset({
    "load_balance", "data_remaining", "active_promos", "expiry",
    "sms_allowance", "call_allowance", "data_buckets",
})


def account_result(value: object, request: int) -> AccountDataResult | None:
    """None means pending; malformed/private payloads become a closed outcome."""
    try:
        if type(value) is not str or len(value) > 65_536:
            raise ValueError
        result = json.loads(value)
        fields = {"request", "state", "data"}
        if (type(result) is not dict or set(result) not in (fields, fields | {"retry_after"})
                or type(result["request"]) is not int or result["request"] != request):
            raise ValueError
        state, data = result["state"], result["data"]
        retry = result.get("retry_after")
        if "retry_after" in result and (
            state != AccountDataIssue.RATE_LIMITED.value or data is not None
            or type(retry) is not int or not 1 <= retry <= MAX_ACCOUNT_RETRY_SECONDS
        ):
            raise ValueError
        if state == "pending" and data is None:
            return None
        if state in {issue.value for issue in AccountDataIssue} and data is None:
            return AccountDataResult(issue=AccountDataIssue(state), retry_after_seconds=retry)
        if state != "ok" or type(data) is not dict or set(data) != _FIELDS:
            raise ValueError
        promos, buckets = data["active_promos"], data["data_buckets"]
        if (type(promos) is not list or len(promos) > 64
                or type(buckets) is not list or len(buckets) > 64):
            raise ValueError
        if any(type(item) is not dict or set(item) != {"name", "expiry"} for item in promos):
            raise ValueError
        if any(type(item) is not dict or set(item) != {"name", "remaining", "expiry"} for item in buckets):
            raise ValueError
        snapshot = AccountData(
            updated_at=datetime.now(timezone.utc),
            load_balance=data["load_balance"], data_remaining=data["data_remaining"],
            active_promos=tuple(AccountPromo(**item) for item in promos),
            expiry=data["expiry"], sms_allowance=data["sms_allowance"],
            call_allowance=data["call_allowance"],
            data_buckets=tuple(AccountBucket(**item) for item in buckets),
        )
        return AccountDataResult(data=snapshot)
    except Exception:
        # JSON/validation errors can contain private page values. Discard them.
        return AccountDataResult(issue=AccountDataIssue.UNSUPPORTED)

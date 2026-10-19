"""Synthetic sanitized account boundary and exact reviewed request policy."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
import unittest
from unittest.mock import patch

from sim_manager.account_models import AccountDataIssue
from sim_manager.carriers.dito.account_data import account_result
from sim_manager.carriers.dito.auth_policy import account_request_allowed, request_allowed


def snapshot(**updates):
    data = dict(load_balance="PHP 17.50", data_remaining="1.25 GB", active_promos=[],
                expiry=None, sms_allowance="All networks: 24 SMS", call_allowance=None,
                data_buckets=[dict(name="Synthetic data bucket", remaining="0.75 GB",
                                   expiry="2026-11-01 09:00:00")])
    data.update(updates)
    return json.dumps(dict(request=1, state="ok", data=data))


class DitoAccountDataBoundaryTests(unittest.TestCase):
    def test_only_rate_limit_wrapper_may_export_bounded_retry_delay(self):
        payload = dict(request=1, state="rate_limited", data=None, retry_after=120)
        result = account_result(json.dumps(payload), 1)
        self.assertIs(result.issue, AccountDataIssue.RATE_LIMITED)
        self.assertEqual(result.retry_after_seconds, 120)
        self.assertIsNone(result.data)
        for value in (None, 0, -1, 3601, True, "SYNTHETIC_PRIVATE_HEADER"):
            result = account_result(json.dumps(dict(payload, retry_after=value)), 1)
            self.assertIs(result.issue, AccountDataIssue.UNSUPPORTED)
            self.assertIsNone(result.retry_after_seconds)
        result = account_result(json.dumps(dict(payload, state="unavailable")), 1)
        self.assertIs(result.issue, AccountDataIssue.UNSUPPORTED)
        self.assertNotIn("120", repr(result))

    def test_reported_values_stay_separate_and_update_time_is_aware(self):
        result = account_result(snapshot(), 1)
        self.assertIsNone(result.issue)
        self.assertEqual(result.data.data_remaining, "1.25 GB")
        self.assertEqual(result.data.data_buckets[0].remaining, "0.75 GB")
        self.assertEqual(result.data.active_promos, ())
        self.assertIsNone(result.data.expiry)
        self.assertIsNone(result.data.call_allowance)
        self.assertIsNotNone(result.data.updated_at.utcoffset())
        self.assertEqual(result.data.source, "official MyDITO")
        self.assertNotIn("17.50", repr(result))
        self.assertNotIn("Synthetic data bucket", repr(result.data))

    def test_repeated_success_replaces_all_fields_and_stamps_only_new_verified_results(self):
        first_time = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
        next_time = datetime(2026, 10, 18, 12, 1, tzinfo=timezone.utc)
        first_payload = snapshot(
            active_promos=[dict(name="Synthetic prior plan", expiry="2026-11-01")],
            expiry="2026-11-01",
        )
        next_payload = json.loads(snapshot(
            load_balance="PHP 9.00", data_remaining="0.25 GB",
            active_promos=[dict(name="Synthetic latest plan", expiry="2026-11-29")],
            expiry=None, sms_allowance=None, call_allowance="Other networks: 15 mins",
            data_buckets=[dict(name="Synthetic latest bucket", remaining="0.10 GB", expiry=None)],
        ))
        next_payload["request"] = 2
        with patch("sim_manager.carriers.dito.account_data.datetime") as clock:
            clock.now.side_effect = [first_time, next_time]
            first = account_result(first_payload, 1)
            latest = account_result(json.dumps(next_payload), 2)
            failed = account_result(json.dumps(dict(request=3, state="unavailable", data=None)), 3)
            self.assertEqual(clock.now.call_args_list[0].args, (timezone.utc,))
            self.assertEqual(clock.now.call_args_list[1].args, (timezone.utc,))
            self.assertEqual(clock.now.call_count, 2)
        self.assertIsNone(first.issue)
        self.assertIsNone(latest.issue)
        self.assertEqual(first.data.updated_at, first_time)
        self.assertEqual(latest.data.updated_at, next_time)
        self.assertGreater(latest.data.updated_at, first.data.updated_at)
        self.assertEqual(latest.data.load_balance, "PHP 9.00")
        self.assertEqual(latest.data.data_remaining, "0.25 GB")
        self.assertEqual(latest.data.active_promos[0].name, "Synthetic latest plan")
        self.assertEqual(latest.data.active_promos[0].expiry, "2026-11-29")
        self.assertIsNone(latest.data.expiry)
        self.assertIsNone(latest.data.sms_allowance)
        self.assertEqual(latest.data.call_allowance, "Other networks: 15 mins")
        self.assertEqual(len(latest.data.data_buckets), 1)
        self.assertEqual(latest.data.data_buckets[0].name, "Synthetic latest bucket")
        self.assertEqual(latest.data.data_buckets[0].remaining, "0.10 GB")
        self.assertIsNone(latest.data.data_buckets[0].expiry)
        self.assertIs(failed.issue, AccountDataIssue.UNAVAILABLE)
        self.assertIsNone(failed.data)
        self.assertEqual(first.data.updated_at, first_time)

    def test_closed_pending_failure_and_expiry_without_private_payloads(self):
        self.assertIsNone(account_result(json.dumps(dict(request=1, state="pending", data=None)), 1))
        for issue in AccountDataIssue:
            result = account_result(json.dumps(dict(request=1, state=issue.value, data=None)), 1)
            self.assertIs(result.issue, issue)
            self.assertIsNone(result.data)
        result = account_result(snapshot(), 2)
        self.assertIs(result.issue, AccountDataIssue.UNSUPPORTED)

    def test_malformed_unknown_private_overlong_and_invalid_values_fail_privately(self):
        values = [None, {}, "x" * 65537, "not JSON",
                  snapshot(phone_number="SYNTHETIC_PRIVATE"), snapshot(load_balance=True),
                  snapshot(load_balance="x" * 161), snapshot(load_balance="private\ntext"),
                  snapshot(data_buckets=[dict(name="Synthetic", remaining="1 GB", expiry=None,
                                              token="SYNTHETIC_PRIVATE")]),
                  json.dumps(dict(request=True, state="ok", data={})),
                  json.dumps(dict(request=1, state="unavailable", data={"token":"SYNTHETIC_PRIVATE"}))]
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            for value in values:
                result = account_result(value, 1)
                self.assertIs(result.issue, AccountDataIssue.UNSUPPORTED)
                self.assertIsNone(result.data)
        self.assertEqual(output.getvalue(), "")

    def test_only_reviewed_account_getters_extend_default_auth_policy(self):
        origin = "https://my.dito.ph"
        reads = [
            ("POST", "/ecare/webs/balance/balInfo"),
            ("POST", "/ecare/webs/balance/balInfo/glSumInfo"),
            ("GET", "/ecare/webs/subs/qrySubsDetail?prodInstIds=123456"),
        ]
        for method, path in reads:
            self.assertFalse(request_allowed(origin + path, method))
            self.assertTrue(account_request_allowed(origin + path, method))
        for method, path in [
            ("GET", "/ecare/webs/balance/balInfo"),
            ("POST", "/ecare/webs/balance/balInfo?write=1"),
            ("GET", "/ecare/webs/subs/qrySubsDetail?prodInstIds=1,2"),
            ("GET", "/ecare/webs/subs/qrySubsDetail?prodInstIds=1&other=2"),
            ("POST", "/ecare/webs/purchase"),
            ("POST", "/ecare/webs/packageHisPageList"),
            ("GET", "/p__Home.d0391f07.async.js"),
        ]:
            self.assertFalse(account_request_allowed(origin + path, method))
        self.assertFalse(account_request_allowed("https://example.invalid/ecare/webs/balance/balInfo", "POST"))


if __name__ == "__main__":
    unittest.main()

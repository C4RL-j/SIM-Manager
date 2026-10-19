"""Synthetic Home display values and static icons without any live provider."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from io import StringIO
import os
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

from sim_manager.account_models import AccountBucket, AccountData, AccountPromo
from sim_manager.ui.home_display import (
    connection_icon, format_last_updated, format_promo_expiry, format_reported_date,
)


STAMP = datetime(2026, 10, 18, 10, 32, tzinfo=timezone.utc)


class HomeDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setQuitOnLastWindowClosed(False)

    def test_date_only_and_naive_reported_time_preserve_source_calendar(self):
        self.assertEqual(format_reported_date("2026-10-18"), "Oct 18, 2026")
        self.assertEqual(format_reported_date("2026-10-18 10:32:00"), "Oct 18, 2026 · 10:32 AM")
        self.assertEqual(format_reported_date("2026-12-31T23:59:59"), "Dec 31, 2026 · 11:59:59 PM")
        self.assertEqual(format_reported_date("2026-10-18 00:00"), "Oct 18, 2026 · 12:00 AM")
        self.assertEqual(format_reported_date("2026-10-18 12:00"), "Oct 18, 2026 · 12:00 PM")

    def test_aware_reported_dates_keep_source_offset_and_nonzero_seconds(self):
        self.assertEqual(format_reported_date("2026-01-01T00:15:00+14:00"),
                         "Jan 1, 2026 · 12:15 AM UTC+14:00")
        self.assertEqual(format_reported_date("2026-10-18T23:32:04Z"),
                         "Oct 18, 2026 · 11:32:04 PM UTC")
        self.assertEqual(format_reported_date("2026-10-18 10:32:00.125-0430"),
                         "Oct 18, 2026 · 10:32:00.125 AM UTC-04:30")
        self.assertEqual(format_reported_date("2026-10-18 10:32:00-00:00"),
                         "Oct 18, 2026 · 10:32 AM UTC-00:00")

    def test_unknown_or_invalid_reported_text_is_unchanged_and_never_logged(self):
        raw = ("Not available", "Unknown", "<b>Synthetic literal</b>",
               "2026-02-30", "2026-10-18 24:00:00", "2026-10-18 10:32+08:99",
               "2026-10-18 10:32+24:00", "18/10/2026", "")
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            self.assertEqual(format_reported_date(None), "Not available")
            for text in raw:
                self.assertEqual(format_reported_date(text), text)
        self.assertEqual(output.getvalue(), "")

    def test_promo_and_bucket_dates_format_individually_without_altering_names_or_raw_values(self):
        data = AccountData(updated_at=STAMP, expiry="2029-12-31", data_buckets=(
            AccountBucket("Synthetic: VIP data", "2 GB", "2026-11-01 23:59:59"),
            AccountBucket("Synthetic bonus", "512 MiB"),
            AccountBucket("Synthetic text allowance", "10 SMS", "2026-10-19"),
        ))
        original = asdict(data)
        self.assertEqual(format_promo_expiry(data),
                         "Synthetic: VIP data: Nov 1, 2026 · 11:59:59 PM\n"
                         "Synthetic bonus: Not available")
        self.assertEqual(asdict(data), original)
        self.assertEqual(format_promo_expiry(AccountData(updated_at=STAMP, expiry="2029-12-31")),
                         "Not available")
        promos = AccountData(updated_at=STAMP, active_promos=(
            AccountPromo("Synthetic: Plan A", "2026-11-02"), AccountPromo("Synthetic Plan B"),
        ))
        self.assertEqual(format_promo_expiry(promos),
                         "Synthetic: Plan A: Nov 2, 2026\nSynthetic Plan B: Not available")
        one = AccountData(updated_at=STAMP, active_promos=(AccountPromo("Synthetic plan", "2026-11-03"),))
        self.assertEqual(format_promo_expiry(one), "Nov 3, 2026")
        single_bucket = AccountData(updated_at=STAMP, data_buckets=(
            AccountBucket("Synthetic single bucket", "2 GB", "2026-11-04"),
        ))
        self.assertEqual(format_promo_expiry(single_bucket), "Nov 4, 2026")
        self.assertEqual(single_bucket.data_buckets[0].name, "Synthetic single bucket")
        self.assertEqual(single_bucket.data_buckets[0].expiry, "2026-11-04")
        self.assertEqual(format_promo_expiry(None), "Not available")

    def test_last_updated_uses_local_aware_calendar_without_fabricating_missing_timestamp(self):
        source = datetime(2026, 12, 31, 20, 32, tzinfo=timezone(-timedelta(hours=12)))
        local = source.astimezone()
        months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
        day = f"{months[local.month - 1]} {local.day}, {local.year}"
        clock = f"{local.hour % 12 or 12}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"
        label = format_last_updated(source)
        self.assertTrue(label.startswith("Last updated: " + day + " · " + clock))
        self.assertIn("UTC", label)
        self.assertEqual(source.utcoffset(), -timedelta(hours=12))
        self.assertEqual(format_last_updated(datetime(2026, 10, 18, 10, 32)), "")
        self.assertEqual(format_last_updated(None), "")

    def test_connection_mark_has_same_geometry_for_colors_and_dpi_scales(self):
        green, grey = connection_icon("#91efda"), connection_icon("#97a8ba")
        self.assertFalse(green.isNull())
        for ratio in (1, 2, 3):
            first = green.pixmap(QSize(20, 20), float(ratio))
            second = grey.pixmap(QSize(20, 20), float(ratio))
            self.assertEqual(first.size(), QSize(20 * ratio, 20 * ratio))
            self.assertEqual(first.devicePixelRatio(), ratio)
            images = (first.toImage(), second.toImage())
            masks = [tuple(image.pixelColor(x, y).alpha()
                           for y in range(image.height()) for x in range(image.width()))
                     for image in images]
            self.assertEqual(masks[0], masks[1])
            self.assertGreater(sum(masks[0]), 0)
            self.assertIn(0, masks[0])
        self.assertFalse(connection_icon("invalid-synthetic-color").isNull())


if __name__ == "__main__":
    unittest.main()

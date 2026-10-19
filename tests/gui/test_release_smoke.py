"""Portable-check orchestration with synthetic Qt state and no live integration."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from test_desktop import DesktopCase
from test_tray import FakeIcon
from sim_manager.ui import release_smoke


PRIVATE = "SYNTHETIC_PRIVATE_SMOKE_ERROR"


class BlankProbe:
    off_record = True
    result = True
    completed = False

    def start(self):
        self.completed = True

    def shutdown(self):
        return True, True


class ReleaseSmokeTests(DesktopCase):
    def temporary_report(self):
        directory = tempfile.TemporaryDirectory(prefix="release-smoke-", dir=Path(__file__).parent)
        self.addCleanup(directory.cleanup)
        return Path(directory.name) / "report.json"

    def test_synthetic_window_resources_tray_and_cleanup_report_only_closed_results(self):
        path = self.temporary_report()
        output = io.StringIO()
        with (patch("sim_manager.ui.release_smoke._BlankWebEngineProbe", BlankProbe),
              patch("sim_manager.ui.tray.QSystemTrayIcon", FakeIcon),
              patch("sim_manager.services.device.LiveDeviceService", side_effect=AssertionError("Live device forbidden")),
              patch("sim_manager.services.messages.LiveMessageService", side_effect=AssertionError("Live SMS forbidden")),
              patch("sim_manager.ui.preferences.QtPreferencesStore", side_effect=AssertionError("User settings forbidden")),
              redirect_stdout(output), redirect_stderr(output)):
            self.assertEqual(release_smoke.run_release_smoke(str(path)), 0)
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(set(report), {"schema", "version", "frozen", "passed", "checks", "counts"})
        self.assertEqual(set(report["checks"]), set(release_smoke._CHECKS))
        self.assertTrue(all(type(value) is bool and value for value in report["checks"].values()))
        self.assertEqual(report["counts"], {"resources": 7})
        self.assertIs(type(report["frozen"]), bool)
        self.assertNotIn(PRIVATE, path.read_text(encoding="utf-8"))
        self.assertEqual(output.getvalue(), "")

    def test_report_is_exclusive_and_private_failures_are_closed(self):
        path = self.temporary_report()
        path.write_text("Synthetic existing file", encoding="utf-8")
        with patch("sim_manager.ui.release_smoke._perform_checks") as checks:
            self.assertEqual(release_smoke.run_release_smoke(str(path)), 2)
            checks.assert_not_called()
        self.assertEqual(path.read_text(encoding="utf-8"), "Synthetic existing file")
        failed_path = path.parent / "failed.json"
        output = io.StringIO()
        with (patch("sim_manager.ui.release_smoke._perform_checks", side_effect=RuntimeError(PRIVATE)),
              redirect_stdout(output), redirect_stderr(output)):
            self.assertEqual(release_smoke.run_release_smoke(str(failed_path)), 1)
        failed = json.loads(failed_path.read_text(encoding="utf-8"))
        self.assertFalse(failed["passed"])
        self.assertTrue(all(value is False for value in failed["checks"].values()))
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn(PRIVATE, failed_path.read_text(encoding="utf-8"))

    def test_webengine_guard_blocks_every_nonblank_url_before_network(self):
        class Request:
            def __init__(self, url):
                self.url = url
                self.blocked = None
            def requestUrl(self):
                return self
            def toString(self):
                if self.url is None:
                    raise RuntimeError(PRIVATE)
                return self.url
            def block(self, blocked):
                self.blocked = blocked
        for url in ("about:blank", "https://my.dito.ph/", "https://192.168.1.1/",
                    "http://127.0.0.1/", "file:///synthetic", "data:text/plain,test", "about:srcdoc", None):
            with self.subTest(url=url):
                request = Request(url)
                release_smoke._block_request(request)
                self.assertIs(request.blocked, url != "about:blank")

    def test_probe_deletes_page_before_profile_and_shutdown_is_repeatable(self):
        events = []
        class Object:
            valid = True
            class WebAction:
                Stop = "stop"
            def __init__(self, name):
                self.name = name
            def triggerAction(self, action):
                if action != self.WebAction.Stop:
                    raise AssertionError("Unexpected stop action")
                events.append("stop " + self.name)
            def close(self):
                events.append("close " + self.name)
            def deleteLater(self):
                events.append("delete " + self.name)
                self.valid = False
        probe = release_smoke._BlankWebEngineProbe.__new__(release_smoke._BlankWebEngineProbe)
        probe.view, probe.page, probe.profile, probe.interceptor = Object("view"), Object("page"), Object("profile"), None
        with (patch("shiboken6.isValid", side_effect=lambda value: value.valid),
              patch("sim_manager.ui.release_smoke._flush_deletes")):
            self.assertEqual(probe.shutdown(), (True, True))
            self.assertEqual(probe.shutdown(), (True, True))
            partial = release_smoke._BlankWebEngineProbe.__new__(release_smoke._BlankWebEngineProbe)
            partial.page = partial.profile = partial.interceptor = None
            self.assertEqual(partial.shutdown(), (True, True))
        self.assertEqual(events, ["close view", "delete view", "stop page", "delete page", "delete profile"])

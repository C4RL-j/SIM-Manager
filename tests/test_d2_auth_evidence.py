"""Offline privacy and boundary tests for the manual public-source probe."""

from __future__ import annotations

import contextlib
import io
import hashlib
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from tools import d2_auth_evidence as probe


PRIVATE = "SYNTHETIC_PRIVATE_VALUE_123456789"
APP = "/static/js/app.5af0ce0f.js"


class PublicSourceEvidenceTests(unittest.TestCase):
    def test_literals_form_candidates_and_only_reviewed_names_leave(self):
        source = '{url:"/web/v1/login",method:"post",data:{username:"' + PRIVATE + '",password:"' + PRIVATE + '"}};localStorage.Authorization;CryptoJS.MD5(password);'
        summary = probe.summarize_auth_source(source, APP)
        self.assertEqual(summary["request_candidates"], [{"method": "POST", "endpoint": "/web/v1/login", "classification": "STATIC CANDIDATE ONLY"}])
        self.assertIn("MD5", summary["reviewed_name_references"])
        self.assertIn("password", summary["reviewed_name_references"])
        self.assertNotIn(PRIVATE, json.dumps(summary))
        self.assertEqual(summary["source"], "/opt/web" + APP)

    def test_comments_dynamic_urls_and_duplicate_keys_do_not_form_candidates(self):
        for source in (
            '// {url:"/web/v1/login",method:"post"}',
            '"{url:\\"/web/v1/login\\",method:\\"post\\"}"',
            '{url:"/web/v1/login"+suffix,method:"post"}',
            '{url:"/web/v1/login",url:dynamic,method:"post"}',
            '{url:"/web/v1/login",method:"post",method:dynamic}',
            '{url:"/web/v1/login",nested:{method:"post"}}',
        ):
            with self.subTest(source=source):
                self.assertEqual(probe.summarize_auth_source(source, APP)["request_candidates"], [])

    def test_unknown_values_and_paths_are_omitted(self):
        source = '{url:"/web/v1/login/' + PRIVATE + '",method:"post"};token="' + PRIVATE + '";'
        summary = probe.summarize_auth_source(source, PRIVATE)
        self.assertEqual(summary["source"], "omitted")
        self.assertEqual(summary["request_candidates"], [])
        self.assertNotIn(PRIVATE, json.dumps(summary))

    def test_asset_parser_accepts_exact_local_scripts_and_omits_unknown_attributes(self):
        html = '<script src="' + APP + '"></script><link href="static/js/chunk-a65ab4a6.3cfa7746.js"><script src="https://private.example/' + PRIVATE + '"></script>'
        self.assertEqual(probe.public_assets(html), [APP, "/static/js/chunk-a65ab4a6.3cfa7746.js"])

    def test_asset_parser_rejects_traversal_queries_and_external_urls(self):
        for value in (APP + "?token=" + PRIVATE, "https://example.test" + APP, "/../" + APP, "//example.test" + APP, APP + "#" + PRIVATE, "/static/js/../app.5af0ce0f.js"):
            with self.subTest(value=value):
                self.assertEqual(probe.public_assets('<script src="' + value + '"></script>'), [])

    def test_network_refuses_any_nonpublic_path_before_building_opener(self):
        for path in ("/web/v1/login", "https://example.test/", "//example.test/", APP + "?x=1"):
            with self.subTest(path=path), patch.object(probe, "_PublicConnection") as build:
                with self.assertRaises(ValueError):
                    probe.fetch_public(path, ssl.create_default_context(), 1e12)
                build.assert_not_called()

    def test_redirect_is_rejected_without_reading_target_or_body(self):
        connection = MagicMock()
        connection.sock = None
        response = connection.getresponse.return_value
        response.status = 302
        with patch.object(probe, "_PublicConnection", return_value=connection), patch.object(probe.time, "monotonic", return_value=1):
            with self.assertRaises(ValueError) as caught:
                probe.fetch_public(APP, ssl.create_default_context(), 10)
        self.assertNotIn(PRIVATE, str(caught.exception))
        response.read1.assert_not_called()
        connection.request.assert_called_once()
        connection.finish.assert_called_once()

    def test_explicit_local_relaxation_is_separate_from_system_default(self):
        normal = probe._context(None, False)
        relaxed = probe._context(None, True)
        self.assertTrue(normal.check_hostname)
        self.assertEqual(normal.verify_mode, ssl.CERT_REQUIRED)
        self.assertFalse(relaxed.check_hostname)
        self.assertEqual(relaxed.verify_mode, ssl.CERT_NONE)
        with self.assertRaises(ValueError):
            probe._context(Path(PRIVATE), True)

    def test_firmware_public_anchor_matches_peer_fingerprint_and_local_ip(self):
        path = Path(__file__).resolve().parents[1] / "src" / "sim_manager" / "resources" / "d2-server.pem"
        pem = path.read_text(encoding="ascii")
        self.assertNotIn("PRIVATE KEY", pem)
        der = ssl.PEM_cert_to_DER_cert(pem)
        self.assertEqual(hashlib.sha256(der).hexdigest(), "b80c4d8777a8894acfbcda6be4389bc8329eae1d25fbc3981ae7a6e0439d4e1b")
        details = ssl._ssl._test_decode_cert(str(path))
        self.assertIn(("IP Address", "192.168.1.1"), details["subjectAltName"])
        context = probe._context(path, False)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_source_ledger_keeps_static_evidence_separate_from_runtime_observation(self):
        path = Path(__file__).resolve().parent / "fixtures" / "d2" / "auth-source-evidence.json"
        ledger = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(ledger["classification"], "VERIFIED SOURCE")
        self.assertEqual(ledger["authentication_attempts"], 0)
        self.assertFalse(ledger["browser_state_accessed"])
        self.assertFalse(ledger["router_configuration_changes_requested"])
        self.assertGreater(len(ledger["runtime_unknowns_at_source_discovery"]), 0)
        for item in ledger["assets"].values():
            self.assertRegex(item["sha256"], r"^[a-f0-9]{64}$")
        for item in ledger["evidence"]:
            summary = probe.summarize_auth_source(item["excerpt"], "/static/js/app.5af0ce0f.js")
            for request in summary["request_candidates"]:
                self.assertEqual(request["classification"], "STATIC CANDIDATE ONLY")

    def test_source_file_output_contains_no_private_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.5af0ce0f.js"
            path.write_text('password="' + PRIVATE + '"', encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output), patch.object(probe, "fetch_public") as fetch:
                result = probe.main(["--source-file", str(path)])
            self.assertEqual(result, 0)
            self.assertNotIn(PRIVATE, output.getvalue())
            fetch.assert_not_called()

    def test_network_exception_output_is_redacted(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(probe, "fetch_public", side_effect=OSError(PRIVATE)):
            result = probe.main(["--fetch-public-assets"])
        self.assertEqual(result, 1)
        self.assertNotIn(PRIVATE, output.getvalue())

    def test_fetch_is_fixed_origin_get_without_credentials(self):
        response = MagicMock()
        response.status = 200
        response.read1.side_effect = [b"public source", b""]
        connection = MagicMock()
        connection.sock = None
        connection.getresponse.return_value = response
        with patch.object(probe, "_PublicConnection", return_value=connection) as build, patch.object(probe.time, "monotonic", return_value=1):
            source, certificate = probe.fetch_public(APP, ssl.create_default_context(), 10)
        self.assertEqual(build.call_args.args, ("192.168.1.1", 443))
        self.assertEqual(connection.request.call_args.args, ("GET", APP))
        self.assertEqual(set(key.lower() for key in connection.request.call_args.kwargs["headers"]), {"accept"})
        self.assertEqual(source, "public source")
        self.assertIsNone(certificate)

    def test_fetch_limits_body_and_obeys_total_deadline(self):
        response = MagicMock()
        response.status = 200
        response.read1.return_value = b"x" * 11
        connection = MagicMock()
        connection.sock = None
        connection.getresponse.return_value = response
        with patch.object(probe, "_PublicConnection", return_value=connection), patch.object(probe.time, "monotonic", return_value=1), patch.object(probe, "MAX_BYTES", 10):
            with self.assertRaises(ValueError):
                probe.fetch_public(APP, ssl.create_default_context(), 10)
        with patch.object(probe, "_PublicConnection") as build, patch.object(probe.time, "monotonic", return_value=11):
            with self.assertRaises(TimeoutError):
                probe.fetch_public(APP, ssl.create_default_context(), 10)
            build.assert_not_called()


if __name__ == "__main__":
    unittest.main()

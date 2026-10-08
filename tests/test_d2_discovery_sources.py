"""Offline Task 004 integration of privacy-filtered source/host metadata."""

import json
import unittest

from test_d2_discovery import PRIVATE, discovery


class DiscoverySourceSummaryTests(unittest.TestCase):
    def summary(self, query, output, status=0):
        return discovery.summarize(discovery.ProbeResult(query, status, output))

    def assert_private_omitted(self, result, *values):
        serialized = json.dumps(result)
        for value in (PRIVATE, *values):
            self.assertNotIn(value, serialized)

    def test_active_entry_source_uses_exact_reviewed_asset_extraction(self):
        output = '<script src=/static/js/app.5af0ce0f.js></script><script src="' + PRIVATE + '"></script>'
        result = self.summary("web-opt-index-source", output)
        self.assertEqual(result["source_path"], "/opt/web/views/index.html")
        self.assertEqual(result["asset_references"], ["/opt/web/static/js/app.5af0ce0f.js"])
        self.assertIn("not runtime values or read-only proof", result["meaning"])
        self.assert_private_omitted(result)

    def test_observed_get_descriptor_is_only_static_candidate(self):
        output = '{url:"/web/v1/dashboard/wirelessinfo",method:"get",token:"' + PRIVATE + '"}'
        result = self.summary("web-opt-dashboard-call-evidence", output)
        self.assertEqual(result["request_candidates"], [{
            "method": "GET", "endpoint": "/web/v1/dashboard/wirelessinfo", "status": "candidate_only",
        }])
        self.assertEqual(result["source_path"], "/opt/web/static/js/app.5af0ce0f.js")
        self.assert_private_omitted(result)

    def test_authentication_source_reports_references_without_storage_values(self):
        output = 'const x=localStorage.getItem("Authorization"); withCredentials=true; const token="' + PRIVATE + '";'
        result = self.summary("web-opt-auth-source-evidence", output)
        self.assertTrue(result["authentication"]["authorization_storage_reference"])
        self.assertTrue(result["authentication"]["with_credentials_reference"])
        self.assertEqual(result["authentication"]["credential_values"], "omitted")
        self.assert_private_omitted(result)

    def test_secrets_composed_of_known_words_are_not_operation_names(self):
        private_values = ("home.wifi", "network.get.info")
        source = 'const password="home.wifi"; const Authorization="network.get.info";'
        for query in discovery.SOURCE_FILES:
            with self.subTest(query=query):
                result = self.summary(query, source)
                self.assertEqual(result["operation_name_candidates"], [])
                self.assert_private_omitted(result, *private_values)
        index = "/www/js/config.js:home.wifi\n/www/js/config.js:network.get.info"
        result = self.summary("web-status-name-index", index)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["unreported_line_count"], 2)
        self.assert_private_omitted(result, *private_values)

    def test_template_and_active_field_indexes_share_capped_reference_parser(self):
        for query in ("web-cellular-template-references", "web-opt-cellular-field-index"):
            with self.subTest(query=query):
                result = self.summary(query, "/opt/web/static/js/app.5af0ce0f.js:17:RSRP\n" + PRIVATE)
                self.assertEqual(result["references"], [{
                    "source_path": "/opt/web/static/js/app.5af0ce0f.js", "line": 17, "term": "rsrp",
                }])
                self.assertEqual(result["omitted_reference_count"], 1)
                self.assert_private_omitted(result)

    def test_opt_file_index_omits_unknown_identifier_paths(self):
        output = "/opt/web/start.sh\n/opt/web/views/index.html\n/opt/web/" + PRIVATE
        result = self.summary("web-opt-file-index", output)
        self.assertEqual(result["source_paths"], ["/opt/web/start.sh", "/opt/web/views/index.html"])
        self.assertEqual(result["unreported_line_count"], 1)
        self.assert_private_omitted(result)

    def test_process_summary_omits_arguments_credentials_and_unknown_processes(self):
        output = "123 root /usr/sbin/cped --token=" + PRIVATE + "\n124 root /opt/web/start.sh\n125 root " + PRIVATE
        result = self.summary("web-server-processes", output)
        self.assertEqual(result["process_references"], ["/usr/sbin/cped", "/opt/web/start.sh"])
        self.assert_private_omitted(result)

    def test_listening_port_summary_masks_addresses_and_excludes_unreviewed_or_nonlisten_rows(self):
        output = (
            "0: 010200C0:01BB 00000000:0000 0A rest\n"
            "1: 010200C0:0050 00000000:0000 01 rest\n"
            "2: 010200C0:C350 00000000:0000 0A rest\n" + PRIVATE
        )
        result = self.summary("web-listening-sockets", output)
        self.assertEqual(result["observed_listening_ports"], [443])
        self.assertEqual(result["addresses"], "masked")
        self.assert_private_omitted(result, "010200C0", "C350")

    def test_config_summary_retains_only_typed_reviewed_server_settings(self):
        output = (
            "/opt/web/conf/app.conf:EnableHTTP = false\n"
            "/opt/web/conf/app_https.conf:EnableHTTPS = true\n"
            "httpsport = 443\nhttpport = 80\nrunmode = prod\n"
            "password = " + PRIVATE + "\nhttpaddr = " + PRIVATE
        )
        result = self.summary("web-opt-server-config", output)
        self.assertEqual(result["settings"], {"enablehttp": False, "enablehttps": True, "httpsport": 443, "httpport": 80, "runmode": "prod"})
        self.assert_private_omitted(result)

    def test_malformed_config_values_do_not_become_active_service_claims(self):
        result = self.summary("web-opt-server-config", "httpport = 999999\nEnableHTTPS = " + PRIVATE + "\nrunmode = unknown")
        self.assertEqual(result["settings"], {})
        self.assertIn("static config", result["meaning"])
        self.assert_private_omitted(result)

    def test_certificate_presence_does_not_disclose_certificate_content(self):
        body = "U1lOVEhFVElDX0NFUlRJRklDQVRFX1RFWFQ="
        result = self.summary("web-opt-server-certificate", "-----BEGIN CERTIFICATE-----\n" + body + "\n-----END CERTIFICATE-----")
        self.assertTrue(result["public_certificate_present"])
        self.assertEqual(result["certificate_values"], "omitted")
        self.assert_private_omitted(result, body)
        malformed = self.summary("web-opt-server-certificate", PRIVATE)
        self.assertFalse(malformed["public_certificate_present"])
        self.assert_private_omitted(malformed)

    def test_http_help_reports_only_tool_capabilities_without_network_or_private_text(self):
        output = "/usr/bin/wget\n-O output -T timeout -S --header\n" + PRIVATE
        result = self.summary("web-http-client-capability", output)
        self.assertTrue(result["wget_reference"])
        self.assertEqual(result["advertised_flags"], ["-O", "-T", "-S", "--header"])
        self.assertIn("no HTTP request executed", result["meaning"])
        self.assert_private_omitted(result)


if __name__ == "__main__":
    unittest.main()

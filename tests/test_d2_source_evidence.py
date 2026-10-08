"""Synthetic offline source fixtures; no successful telemetry responses implied."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

with patch("socket.socket", side_effect=AssertionError("Real sockets forbidden")):
    with patch("socket.create_connection", side_effect=AssertionError("Real connections forbidden")):
        from tools import d2_source_evidence as evidence


APP = "/opt/web/static/js/app.5af0ce0f.js"
VIEW = "/opt/web/views/index.html"
WIRELESS = "/web/v1/dashboard/wirelessinfo"
INTERNET = "/web/v1/dashboard/internetinfo"
PRIVATE = "SYNTHETIC_PRIVATE_TOKEN"


class SourceCase(unittest.TestCase):
    def summary(self, text, path=APP):
        return evidence.summarize_source(text, path)

    def assert_private_omitted(self, result, *values):
        serialized = json.dumps(result)
        for value in (PRIVATE, *values):
            self.assertNotIn(value, serialized)


class AssetEvidenceTests(SourceCase):
    def test_quoted_unquoted_and_self_closing_assets_resolve_to_reviewed_files(self):
        result = self.summary(
            '<script src="/static/js/app.5af0ce0f.js"></script>'
            '<script src=static/js/chunk-a65ab4a6.3cfa7746.js></script>'
            '<link href="/static/js/chunk-libs.4f4c4243.js" />',
            VIEW,
        )
        self.assertEqual(result["asset_references"], sorted([
            APP, "/opt/web/static/js/chunk-a65ab4a6.3cfa7746.js",
            "/opt/web/static/js/chunk-libs.4f4c4243.js",
        ]))

    def test_legacy_relative_asset_and_exact_known_asset_literal_are_supported(self):
        legacy = self.summary('<script src="js/ajax.js"></script>', "/www/index.html")
        self.assertEqual(legacy["asset_references"], ["/www/js/ajax.js"])
        literal = self.summary('const modulePath = "' + APP + '";')
        self.assertEqual(literal["asset_references"], [APP])

    def test_remote_traversal_query_fragment_and_encoded_assets_are_rejected(self):
        for reference in (
            "https://private.example/static/js/app.5af0ce0f.js",
            "//private.example/static/js/app.5af0ce0f.js",
            "/static/js/app.5af0ce0f.js?token=" + PRIVATE,
            "/static/js/app.5af0ce0f.js#" + PRIVATE,
            "../static/js/app.5af0ce0f.js",
            "/static/./js/app.5af0ce0f.js",
            "/static/%6as/app.5af0ce0f.js",
            r"\static\js\app.5af0ce0f.js",
            "/static/js/" + PRIVATE + ".js",
        ):
            with self.subTest(reference=reference):
                result = self.summary('<script src="' + reference + '"></script>', VIEW)
                self.assertEqual(result["asset_references"], [])
                self.assert_private_omitted(result, "private.example")

    def test_duplicate_assets_are_deduplicated(self):
        result = self.summary('<script src="' + APP + '"></script>' * 3, VIEW)
        self.assertEqual(result["asset_references"], [APP])

    def test_unknown_source_path_is_omitted(self):
        result = self.summary("", "/opt/web/" + PRIVATE + ".js")
        self.assertEqual(result["source_path"], "omitted")
        self.assert_private_omitted(result)

    def test_missing_src_and_partial_markup_do_not_invent_assets(self):
        for text in ('<script src></script>', '<script src="/static/js/app.', '<script>'):
            with self.subTest(text=text):
                self.assertEqual(self.summary(text, VIEW)["asset_references"], [])

    def test_assets_inside_javascript_and_html_comments_are_ignored(self):
        text = (
            '// "' + APP + '"\n'
            '/* "' + APP + '" */\n'
            '<!-- <script src="' + APP + '"></script> -->'
        )
        self.assertEqual(self.summary(text, VIEW)["asset_references"], [])


class RequestCandidateTests(SourceCase):
    def test_verb_and_url_in_same_object_are_candidate_evidence_only(self):
        result = self.summary('client({url:"' + WIRELESS + '",method:"get"});')
        self.assertEqual(result["request_candidates"], [{
            "method": "GET", "endpoint": WIRELESS, "status": "candidate_only",
        }])
        self.assertEqual(result["endpoint_references"], [WIRELESS])
        self.assertEqual(result["meaning"], evidence.MEANING)
        self.assertIn("not runtime values or read-only proof", result["meaning"])

    def test_ajax_type_and_quoted_property_keys_are_supported(self):
        result = self.summary('ajax({"url":"' + INTERNET + '","type":"GET"});')
        self.assertEqual(result["request_candidates"], [{
            "method": "GET", "endpoint": INTERNET, "status": "candidate_only",
        }])

    def test_post_and_delete_are_distinguished_without_becoming_read_proof(self):
        for verb in ("POST", "DELETE"):
            with self.subTest(verb=verb):
                result = self.summary('{url:"' + WIRELESS + '",method:"' + verb + '"}')
                self.assertEqual(result["request_candidates"], [{
                    "method": verb, "endpoint": WIRELESS, "status": "candidate_only",
                }])
                self.assertIn("not runtime values or read-only proof", result["meaning"])

    def test_neighboring_objects_cannot_lend_method_to_endpoint(self):
        text = 'first({url:"' + WIRELESS + '"}); second({method:"GET"});'
        result = self.summary(text)
        self.assertEqual(result["request_candidates"], [])
        self.assertEqual(result["endpoint_references"], [WIRELESS])

    def test_nested_object_cannot_lend_method_to_parent_endpoint(self):
        for text in (
            '{url:"' + WIRELESS + '",options:{method:"GET"}}',
            '{method:"GET",options:{url:"' + WIRELESS + '"}}',
        ):
            with self.subTest(text=text):
                self.assertEqual(self.summary(text)["request_candidates"], [])

    def test_missing_null_unexpected_and_unknown_endpoint_values_are_not_requests(self):
        for text in (
            "{}", "{url:null,method:'GET'}", "{url:7,method:'GET'}",
            "{url:['" + WIRELESS + "'],method:'GET'}",
            "{url:'" + WIRELESS + "',method:null}",
            "{url:'" + WIRELESS + "',method:['GET']}",
            "{url:'" + WIRELESS + "',method:'PATCH'}",
            "{url:'/unknown/" + PRIVATE + "',method:'GET'}",
        ):
            with self.subTest(text=text):
                result = self.summary(text)
                self.assertEqual(result["request_candidates"], [])
                self.assert_private_omitted(result)

    def test_duplicate_url_or_verb_properties_are_rejected(self):
        for suffix in (
            ',url:"' + INTERNET + '"', ',method:"POST"', ',type:"GET"',
            ',url:null', ',method:null', ',method:requestMethod',
        ):
            with self.subTest(suffix=suffix):
                text = '{url:"' + WIRELESS + '",method:"GET"' + suffix + '}'
                self.assertEqual(self.summary(text)["request_candidates"], [])

    def test_dynamic_url_or_method_expression_is_not_promoted_to_fixed_request(self):
        for text in (
            '{url:"' + WIRELESS + '"+suffix,method:"GET"}',
            '{url:"' + WIRELESS + '",method:"GET"+suffix}',
            '{url:"' + WIRELESS + '",method:"GET".toLowerCase()}',
            '{url:"' + WIRELESS + '"?first:second,method:"GET"}',
        ):
            with self.subTest(text=text):
                self.assertEqual(self.summary(text)["request_candidates"], [])

    def test_incomplete_objects_do_not_produce_complete_request_candidates(self):
        for text in ('{url:"' + WIRELESS + '",method:"GET"', '{url:"' + WIRELESS):
            with self.subTest(text=text):
                self.assertEqual(self.summary(text)["request_candidates"], [])

    def test_commented_requests_and_endpoint_literals_are_ignored(self):
        object_text = '{url:"' + WIRELESS + '",method:"GET"}'
        for text in ('// ' + object_text, '/* ' + object_text + ' */', '<!-- ' + object_text + ' -->'):
            with self.subTest(text=text):
                result = self.summary(text)
                self.assertEqual(result["request_candidates"], [])
                self.assertEqual(result["endpoint_references"], [])

    def test_plain_strings_templates_and_escaped_literals_do_not_supply_requests(self):
        for text in (
            "const sample = '{url:\"" + WIRELESS + "\",method:\"GET\"}';",
            '`{url:"' + WIRELESS + '",method:"GET"}`',
            '{url:"\\/web/v1/dashboard/wirelessinfo",method:"GET"}',
        ):
            with self.subTest(text=text):
                self.assertEqual(self.summary(text)["request_candidates"], [])

    def test_identical_candidates_are_deduplicated(self):
        text = '{url:"' + WIRELESS + '",method:"GET"};' * 5
        self.assertEqual(len(self.summary(text)["request_candidates"]), 1)


class TelemetryNameAndPrivacyTests(SourceCase):
    def test_structural_field_names_are_canonical_and_values_omitted(self):
        text = (
            'data.RSRP; data["RSRQ"]; const fields={SINR:-7,iccid:"8988000000000000001",'
            'imsi:"515000000000001",msisdn:"09900000001",plmn:"51500",'
            'password:"' + PRIVATE + '"};'
        )
        result = self.summary(text)
        self.assertEqual(result["telemetry_fields"], ["iccid", "imsi", "msisdn", "plmn", "rsrp", "rsrq", "sinr"])
        self.assert_private_omitted(result, "8988000000000000001", "515000000000001", "09900000001", "51500")
        self.assertNotIn("carrier", result)

    def test_bare_words_labels_and_stringified_json_do_not_become_fields(self):
        text = "rsrp; const label='imsi'; const sample='{\"iccid\":\"private\"}'; ['sinr'];"
        self.assertEqual(self.summary(text)["telemetry_fields"], [])

    def test_missing_null_unexpected_field_values_still_only_prove_names(self):
        text = "const sample={rsrp:null,rsrq:[],sinr:{unexpected:true},iccid:false};"
        result = self.summary(text)
        self.assertEqual(result["telemetry_fields"], ["iccid", "rsrp", "rsrq", "sinr"])
        self.assertEqual(result["other_values"], "omitted")
        self.assertIn("not runtime values", result["meaning"])

    def test_unknown_keys_and_nested_authentication_values_are_not_exposed(self):
        text = (
            'const response={"' + PRIVATE + '":"' + PRIVATE + '",'
            'auth:{cookie:"' + PRIVATE + '",token:"' + PRIVATE + '"},'
            'sms:{body:"OTP 123456"},imsi:"515000000000001"};'
        )
        result = self.summary(text)
        self.assertEqual(result["telemetry_fields"], ["imsi"])
        self.assert_private_omitted(result, "123456", "515000000000001")

    def test_template_directives_and_fixed_field_names_are_evidence_only(self):
        text = (
            '<% getobject "SIM" %><% leaf iccid %><% getsingle rsrp %>'
            '<? path operatorname ?><? endgetobject ?>'
        )
        result = self.summary(text, "/www/page/status/status_dongle.shtml")
        self.assertEqual(result["template_getters"], ["endgetobject", "getobject", "getsingle", "leaf", "path"])
        self.assertEqual(result["template_field_names"], ["iccid", "operatorname", "rsrp"])
        self.assertIn("not runtime values or read-only proof", result["meaning"])

    def test_unknown_or_commented_template_directives_do_not_supply_evidence(self):
        text = '<% set imsi "' + PRIVATE + '" %><!-- <% getobject iccid %> -->'
        result = self.summary(text)
        self.assertEqual(result["template_getters"], [])
        self.assertEqual(result["template_field_names"], [])
        self.assert_private_omitted(result)

    def test_javascript_comments_do_not_supply_field_names(self):
        result = self.summary('// data.iccid;\n/* const value={imsi:"' + PRIVATE + '"}; */')
        self.assertEqual(result["telemetry_fields"], [])
        self.assert_private_omitted(result)

    def test_source_must_be_text_and_errors_omit_invalid_input(self):
        for value in (None, 9, [], {PRIVATE: PRIVATE}):
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ValueError) as error:
                    self.summary(value)
                self.assertNotIn(PRIVATE, str(error.exception))

    def test_input_bound_omits_names_and_private_values_beyond_scan_limit(self):
        text = " " * evidence.MAX_SOURCE_CHARS + 'data.imsi;const token="' + PRIVATE + '";'
        result = self.summary(text)
        self.assertTrue(result["input_truncated"])
        self.assertEqual(result["telemetry_fields"], [])
        self.assert_private_omitted(result)

    def test_empty_input_has_explicit_empty_evidence_and_no_truncation(self):
        result = self.summary("")
        for key in ("asset_references", "telemetry_fields", "template_getters", "template_field_names", "endpoint_references", "request_candidates"):
            self.assertEqual(result[key], [])
        self.assertFalse(result["input_truncated"])


class SourceReferenceTests(SourceCase):
    def test_known_path_term_and_optional_line_are_canonical_and_deduplicated(self):
        result = evidence.summarize_references(
            APP + ':14:RSRP\n' + APP + ':14:rsrp\n' + APP + ':imsi\n'
        )
        self.assertEqual(result["references"], [
            {"source_path": APP, "term": "imsi"},
            {"source_path": APP, "term": "rsrp", "line": 14},
        ])
        self.assertEqual(result["omitted_reference_count"], 0)
        self.assertEqual(result["meaning"], evidence.MEANING)

    def test_unknown_paths_terms_values_and_malformed_lines_are_counted_only(self):
        text = (
            "/opt/web/" + PRIVATE + ".js:rsrp\n" + APP + ':' + PRIVATE + '\n'
            + APP + ':0:imsi\n' + APP + ':-1:imsi\n'
            + APP + ':iccid=8988000000000000001\n' + PRIVATE + '\n'
        )
        result = evidence.summarize_references(text)
        self.assertEqual(result["references"], [])
        self.assertEqual(result["omitted_reference_count"], 6)
        self.assert_private_omitted(result, "8988000000000000001")

    def test_list_cap_retains_omitted_count(self):
        text = "\n".join(APP + ':' + str(line) + ':rsrp' for line in range(1, evidence.MAX_ITEMS + 4))
        result = evidence.summarize_references(text)
        self.assertEqual(len(result["references"]), evidence.MAX_ITEMS)
        self.assertEqual(result["omitted_reference_count"], 3)

    def test_reference_input_bound_does_not_scan_tail(self):
        result = evidence.summarize_references(" " * evidence.MAX_SOURCE_CHARS + '\n' + APP + ':imsi')
        self.assertTrue(result["input_truncated"])
        self.assertEqual(result["references"], [])

    def test_null_reference_input_fails_without_raw_value(self):
        with self.assertRaises(ValueError):
            evidence.summarize_references(None)


class RecordedShapeFixtureTests(SourceCase):
    fixtures = Path(__file__).parent / "fixtures" / "d2"

    def test_synthetic_entry_fixture_covers_observed_unquoted_asset_forms(self):
        result = self.summary((self.fixtures / "admin-entry.html").read_text(encoding="utf-8"), VIEW)
        self.assertEqual(result["asset_references"], [APP, "/opt/web/static/js/chunk-libs.4f4c4243.js"])

    def test_synthetic_request_fixture_preserves_seven_observed_get_descriptors(self):
        result = self.summary((self.fixtures / "admin-requests.js").read_text(encoding="utf-8"))
        expected = sorted([
            "/web/v1/dashboard/wirelessinfo", "/web/v1/dashboard/internetinfo",
            "/web/v1/dashboard/waninfo", "/web/v1/dashboard/deviceinfo",
            "/web/v1/status/wanstatus", "/web/v1/setting/network/pinmanagement/simcardinfo",
            "/web/v1/setting/deviceinfo",
        ])
        self.assertEqual(result["request_candidates"], [
            {"method": "GET", "endpoint": endpoint, "status": "candidate_only"}
            for endpoint in expected
        ])
        self.assertEqual(result["telemetry_fields"], sorted([
            "rsrp0", "rsrp1", "uiccid", "usimstatus", "simcardstate", "retriespin",
            "pincheckenabled", "ecellid", "connectstatus", "connectmode", "connectionstatus",
            "devicemodel", "productmodel", "hardwareversion", "softwareversion", "routerversion",
            "runningtime", "ubootversion", "serialnumber", "ipaddress", "subnetmask", "macaddress", "imei",
        ]))
        self.assertIn("not runtime values", result["meaning"])

    def test_observed_unauthorized_fixture_contains_only_confirmed_status_and_field_types(self):
        shape = json.loads((self.fixtures / "unauthorized-response-shape.json").read_text(encoding="utf-8"))
        self.assertEqual(shape, {"http_status": 401, "body_field_types": {"code": "number", "msg": "string"}})
        self.assertNotIn("body", shape)
        self.assertNotIn("code", shape)


if __name__ == "__main__":
    unittest.main()

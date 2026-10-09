"""Synthetic MyDITO URL and auth-only request boundaries; no network calls."""

import unittest

from sim_manager.carriers.dito.auth_policy import (
    AUTH_REQUESTS,
    LOGIN_URL,
    PROBE_SOURCE,
    authenticated_route,
    observer_source,
    request_allowed,
    trusted_origin,
)


class DitoAuthPolicyTests(unittest.TestCase):
    def test_official_origin_and_explicit_https_port(self):
        self.assertTrue(trusted_origin(LOGIN_URL))
        self.assertTrue(trusted_origin("https://my.dito.ph:443/"))

    def test_hostile_and_untrusted_origins_fail_closed(self):
        for value in (
            "http://my.dito.ph/", "https://my.dito.ph.evil.example/",
            "https://evil.example/my.dito.ph/", "https://sub.my.dito.ph/",
            "https://my.dito.ph./", "https://my.dito.ph:8443/",
            "https://username@my.dito.ph/", "https://my.dito.ph@evil.example/",
            "https://my.dito.ph\\@evil.example/", "https://my.dito.ph\n/",
            " https://my.dito.ph/", "https://my.dito.ph:/../", "//my.dito.ph/",
            "file:///my.dito.ph", "javascript:alert(1)", "data:text/html,hello",
            "https://192.168.1.1/", "https://my.dito.ph:invalid/", "", None,
        ):
            with self.subTest(value=value):
                self.assertFalse(trusted_origin(value))

    def test_success_route_is_exact_and_has_no_private_query(self):
        self.assertTrue(authenticated_route("https://my.dito.ph/pto/home"))
        for path in ("/", "/pto/home/", "/pto/home?token=SYNTHETIC_PRIVATE", "/pto/home#x", "/dashboard"):
            with self.subTest(path=path):
                self.assertFalse(authenticated_route("https://my.dito.ph" + path))

    def test_evidenced_api_paths_require_the_evidenced_method(self):
        for method, path in AUTH_REQUESTS:
            with self.subTest(path=path):
                self.assertTrue(request_allowed("https://my.dito.ph" + path, method))
                for wrong in {"GET", "POST", "DELETE", "PUT", "PATCH", "HEAD", "OPTIONS", "get"} - {method}:
                    self.assertFalse(request_allowed("https://my.dito.ph" + path, wrong))

    def test_manual_sign_in_sms_action_is_the_only_allowed_sms_request(self):
        # These are synthetic structural values, never user identifiers.
        self.assertTrue(request_allowed("https://my.dito.ph/ecare/webs/message/sms/1/9999999999", "POST"))
        for path in (
            "/ecare/webs/message/sms/2/9999999999",
            "/ecare/webs/message/sms/3/9999999999",
            "/ecare/webs/message/sms/1/not-a-number",
            "/ecare/webs/message/sms/1/9999999999/delete",
            "/ecare/webs/message/sms/captcha/send",
        ):
            with self.subTest(path=path):
                self.assertFalse(request_allowed("https://my.dito.ph" + path, "POST"))

    def test_captcha_image_is_bounded_and_read_only(self):
        url = "https://my.dito.ph/ecare/webs/captcha/SYNTHETIC_REQUEST_SN"
        self.assertTrue(request_allowed(url, "GET"))
        self.assertFalse(request_allowed(url, "POST"))
        self.assertFalse(request_allowed(url + "/nested", "GET"))
        self.assertFalse(request_allowed("https://my.dito.ph/ecare/webs/captcha/" + "x" * 129, "GET"))

    def test_public_first_party_assets_are_read_only(self):
        for path in (
            "/umi.bf77fdf1.js", "/p__Login.a8b21259.async.js",
            "/common.76853765.chunk.css", "/assets/favicon.png",
            "/assets/example/font.woff2", "/lib/DXPNudges.umd.js",
        ):
            with self.subTest(path=path):
                self.assertTrue(request_allowed("https://my.dito.ph" + path, "GET"))
                self.assertFalse(request_allowed("https://my.dito.ph" + path, "POST"))

    def test_asset_suffix_cannot_allow_an_account_api(self):
        for path in (
            "/ecare/webs/account/example/balance.js", "/unverified/api.js",
            "/assets/../ecare/account.js", "/assets/%2e%2e/private.js",
            "/assets//private.js", "/lib/./private.js", "/assets/private.html",
        ):
            with self.subTest(path=path):
                self.assertFalse(request_allowed("https://my.dito.ph" + path, "GET"))

    def test_protected_account_view_scripts_cannot_bootstrap_account_data(self):
        for path in (
            "/layouts__BaseLayout.90e0e6a7.async.js",
            "/p__Home.d0391f07.async.js",
            "/layouts__BaseLayout.abcdef12.async.js",
            "/p__Home.abcdef12.async.js?cache=synthetic",
        ):
            for method in ("GET", "POST"):
                with self.subTest(path=path, method=method):
                    self.assertFalse(request_allowed("https://my.dito.ph" + path, method))
        # Authentication's own script and the success milestone remain usable.
        self.assertTrue(request_allowed("https://my.dito.ph/p__Login.a8b21259.async.js", "GET"))
        self.assertTrue(request_allowed("https://my.dito.ph/pto/home", "GET"))
        self.assertTrue(authenticated_route("https://my.dito.ph/pto/home"))

    def test_account_data_and_actions_remain_denied(self):
        for path in (
            "/ecare/webs/subs/qrySubsDetail?prodInstIds=SYNTHETIC",
            "/ecare/webs/cust/qryUserInfo/SYNTHETIC",
            "/ecare/webs/account/SYNTHETIC/balance",
            "/ecare/webs/balance/balInfo/glSumInfo", "/ecare/webs/offer/promo/detail",
            "/ecare/webs/password/resetSubsPwd", "/dxp/loyalty/v1/memberships/info",
            "/ecare/user/currentInfo", "/ecare/webs/payMethod/submit",
        ):
            for method in ("GET", "POST"):
                with self.subTest(path=path, method=method):
                    self.assertFalse(request_allowed("https://my.dito.ph" + path, method))

    def test_external_telemetry_debugging_and_router_requests_remain_denied(self):
        for url in (
            "https://unpkg.com/vconsole@latest/dist/vconsole.min.js",
            "https://www.googletagmanager.com/gtag/js", "https://192.168.1.1/",
            "https://smartbrosettings.net/", "https://evil.example/umi.js",
        ):
            self.assertFalse(request_allowed(url, "GET"))

    def test_navigation_and_invalid_types_fail_closed(self):
        self.assertTrue(request_allowed(LOGIN_URL, "GET"))
        self.assertTrue(request_allowed("https://my.dito.ph/pto/home", "GET"))
        self.assertFalse(request_allowed(LOGIN_URL + "?schemaUrl=private", "GET"))
        self.assertFalse(request_allowed(LOGIN_URL, None))
        self.assertFalse(request_allowed(LOGIN_URL, "POST"))

    def test_packaged_observer_and_probe_are_available_without_browser_imports(self):
        source = observer_source()
        self.assertIn("loginSuccess === true", source)
        self.assertIn("__simManagerDitoAuthObserver", PROBE_SOURCE)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("document.cookie", source)
        self.assertNotIn("console.", source)


if __name__ == "__main__":
    unittest.main()

"""Offline safety and privacy checks for the manually invoked discovery tool.

All transcripts and identifiers are synthetic. Real socket creation is blocked;
capture checks use temporary directories and never retain hardware responses.
"""

from collections import deque
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import signal
import socket
import tempfile
import threading
import traceback
import unittest
from unittest.mock import patch

from test_d2_router import FakeSocket, OfflineCase, router

with patch("socket.socket", side_effect=AssertionError("Real sockets forbidden")):
    with patch(
        "socket.create_connection",
        side_effect=AssertionError("Real connections forbidden"),
    ):
        from tools import d2_discovery as discovery


READ_ONLY_QUERIES = {'ubus-path': 'command -v ubus',
 'ubus-help': 'ubus -h',
 'ubus-objects': 'ubus -t 5 list',
 'cped-schema': 'ubus -t 5 -v list cped',
 'firmware-release': 'cat /etc/openwrt_release',
 'web-file-index': 'find /www -maxdepth 4 -type f',
 'web-entry-source': 'cat /www/index.html',
 'web-ajax-source': 'cat /www/js/ajax.js',
 'web-init-source': 'cat /www/js/init.js',
 'web-tri-source': 'cat /www/js/tri.js',
 'web-project-source': 'cat /www/js/project.js',
 'web-dongle-status-source': 'cat /www/page/status/status_dongle.shtml',
 'web-device-status-source': 'cat /www/page/status/status_info.shtml',
 'web-wan-status-source': 'cat /www/page/status/status_wannetwork.shtml',
 'web-hidden-source': 'cat /www/page/hidden_noauth/index.html',
 'web-utils-source': 'cat /www/js/t_utils.js',
 'web-menu-source': 'cat /www/js/menu.js',
 'web-project-menu-source': 'cat /www/js/project_menu.js',
 'web-menu-template-source': 'cat /www/menu.shtml',
 'web-cellular-template-references': "find /www -maxdepth 4 -type f \\( -name '*.shtml' -o -name '*.html' -o "
                                     "-name '*.js' -o -name '*.cgi' \\) -exec grep -H -i -n -oE "
                                     "'rssi|rsrp|rsrq|sinr|earfcn|iccid|imsi|msisdn|plmn|mcc|mnc|operator|WANDongleInterfaceConfig|cped|ubus|ajax|XMLHttpRequest' "
                                     '{} \\;',
 'web-server-processes': 'ps',
 'web-listening-sockets': 'cat /proc/net/tcp /proc/net/tcp6',
 'web-opt-start-source': 'cat /opt/web/start.sh',
 'web-opt-file-index': 'find /opt/web -maxdepth 4 -type f',
 'web-opt-index-source': 'cat /opt/web/views/index.html',
 'web-opt-index-template-source': 'cat /opt/web/views/index.tpl',
 'web-opt-server-config': 'grep -E '
                          "'^[[:space:]]*(appname|httpaddr|httpport|httpsaddr|httpsport|EnableHTTP|EnableHTTPS|runmode)[[:space:]]*=' "
                          '/opt/web/conf/app.conf /opt/web/conf/app_https.conf',
 'web-opt-server-certificate': 'cat /opt/web/conf/server.crt',
 'web-opt-app-source-evidence': "tr ';{}' '\\n' < /opt/web/static/js/app.5af0ce0f.js | grep -iE "
                                "'rsrp|rsrq|sinr|rssi|earfcn|iccid|imsi|msisdn|plmn|cped|ubus|sms.get.inboxdata|network.get|sim.get'",
 'web-opt-request-catalog': "tr ';{}' '\\n' < /opt/web/static/js/app.5af0ce0f.js | grep -E "
                            "'url:|baseURL|Authorization|withCredentials|X-Token|csrf'",
 'web-opt-auth-source-evidence': "tr ';{}' '\\n' < /opt/web/static/js/app.5af0ce0f.js | grep -B 4 -A 5 -E "
                                 "'Authorization|withCredentials|localStorage.getItem|sessionStorage.getItem'",
 'web-opt-dashboard-call-evidence': "tr ';{}' '\\n' < /opt/web/static/js/app.5af0ce0f.js | grep -B 6 -A 10 "
                                    '-E '
                                    '\'url:"/web/v1/(dashboard/(wirelessinfo|internetinfo|waninfo|deviceinfo)|status/wanstatus|setting/network/pinmanagement/simcardinfo|setting/deviceinfo)"\'',
 'web-opt-dashboard-view-evidence': "tr ';{}' '\\n' < /opt/web/static/js/chunk-a65ab4a6.3cfa7746.js | grep "
                                    '-i -B 5 -A 8 -E '
                                    "'rsrp|rsrq|sinr|rssi|iccid|imsi|plmn|simstatus|wirelessinfo|internetinfo|waninfo|deviceinfo|simcardinfo'",
 'web-opt-cellular-field-index': 'grep -H -i -oE '
                                 "'iccid|imsi|msisdn|plmn|rsrp|rsrq|sinr|rssi|earfcn|pci|simstate|simstatus|pinstate|operatorname|networktype|apn|wirelessinfo|internetinfo|waninfo|deviceinfo' "
                                 '/opt/web/static/js/app.5af0ce0f.js '
                                 '/opt/web/static/js/chunk-a65ab4a6.3cfa7746.js '
                                 '/opt/web/static/js/chunk-ff19fe88.a86a0aee.js '
                                 '/opt/web/static/js/chunk-508c212a.59fd7df1.js',
 'web-http-client-capability': 'command -v wget; wget --help',
 'web-config-source': 'cat /www/js/config.js',
 'web-page-source': 'cat /www/js/page.js',
 'web-sms-source-index': "find /www -maxdepth 4 -type f \\( -name '*.js' -o -name '*.html' \\) -exec grep -l "
                         "'sms.get.inboxdata' {} \\;",
 'web-status-name-index': "find /www -maxdepth 4 -type f \\( -name '*.js' -o -name '*.html' \\) -exec grep "
                          '-H -oE '
                          "'(sim|network|lte|wan|modem|device|system|internet)\\.(get|status|info)[a-z0-9_.]*' "
                          '{} \\;',
 'ip-addresses': 'ip address show',
 'ip-routes': 'ip route show',
 'usb-descriptors': 'for d in /sys/bus/usb/devices/*; do for f in idVendor idProduct manufacturer product; '
                    'do if [ -f "$d/$f" ]; then printf "%s %s=" "${d##*/}" "$f"; cat "$d/$f"; fi; done; done',
 'web-capability-references': "find /www -maxdepth 4 -type f \\( -name '*.js' -o -name '*.html' \\) -exec "
                              'grep -H -i -oE '
                              "'iccid|imsi|msisdn|plmn|mcc|mnc|rsrp|rsrq|sinr|rssi|earfcn|roaming|registration|quectel|apn|ipv4|ipv6|operator' "
                              '{} \\;',
 'ipv6-routes': 'ip -f inet6 route show',
 'resolver-state': 'cat /etc/resolv.conf',
 'configured-apn-presence': "grep -E '^[[:space:]]*option[[:space:]]+apn[[:space:]]' /etc/config/network",
 'usb-network-binding': 'v4dev="$(ip route show | sed -n \'s/^default .*dev \\([^ ]*\\).*/\\1/p\')"; '
                        'v6dev="$(ip -f inet6 route show | sed -n \'s/^default .*dev \\([^ '
                        ']*\\).*/\\1/p\')"; for n in /sys/class/net/*; do if [ -e "$n/device" ]; then printf '
                        '"%s|%s|" "${n##*/}" "$(readlink -f "$n/device")"; if [ "${n##*/}" = "$v4dev" ]; '
                        'then printf v4; fi; if [ "${n##*/}" = "$v6dev" ]; then printf v6; fi; printf "\\n"; '
                        'fi; done'}

PRIVATE = "SYNTHETIC_PRIVATE_TOKEN"


def frame(payload="", status=0):
    return (
        discovery.BEGIN + "\r\n" + payload + "\r\n"
        + discovery.EXIT + str(status) + "__\r\n"
        + discovery.END + "\r\n"
    )


class DiscoverySocket(FakeSocket):
    """Keep the idle banner reads separate from fixed-command responses."""

    def __init__(self, clock, response=(), banner=(b"synthetic shell\r\n# ",)):
        super().__init__(clock)
        self.phase = "banner"
        self.phases = {
            "banner": deque(banner),
            "wakeup": deque((b"# ",)),
            "response": deque(response),
        }

    def sendall(self, data):
        super().sendall(data)
        if data == b"\r\n":
            self.phase = "wakeup"
        elif data.startswith(b"printf "):
            self.phase = "response"

    def recv(self, size):
        self.receives = self.phases[self.phase]
        return super().recv(size)


class CommandAndFrameTests(unittest.TestCase):
    def test_only_reviewed_read_only_queries_are_available(self):
        self.assertEqual(discovery.QUERIES, READ_ONLY_QUERIES)

    def test_unknown_query_and_shell_injection_are_rejected(self):
        for query in ("", "AT+CSQ", "reboot", "ubus-path; reboot", "../firmware-release"):
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    discovery.frame_command(query)

    def test_fixed_command_is_framed_without_arbitrary_arguments(self):
        command = discovery.frame_command("ubus-path")
        self.assertEqual(
            command,
            (
                "printf '\\n" + discovery.BEGIN + "\\n'; command -v ubus; "
                + "printf '\\n" + discovery.EXIT + "%s__\\n" + discovery.END
                + "\\n' \"$?\"\r\n"
            ).encode("ascii"),
        )

    def test_echo_and_unframed_shell_text_are_excluded(self):
        output = (
            PRIVATE + "\r\n# " + discovery.frame_command("ubus-path").decode()
            + frame("/sbin/ubus") + PRIVATE
        )
        result = discovery.parse_frame("ubus-path", output)
        self.assertEqual(result.output.strip(), "/sbin/ubus")
        self.assertEqual(result.exit_code, 0)
        self.assertNotIn(PRIVATE, result.output)

    def test_command_echo_alone_cannot_be_a_complete_frame(self):
        with self.assertRaises(router.RouterResponseError):
            discovery.parse_frame("ubus-path", discovery.frame_command("ubus-path").decode())

    def test_json_and_multiline_shell_response_are_preserved_as_data(self):
        payload = '{"cmd":{"arg":"String"}}\n# synthetic shell text\n[]'
        result = discovery.parse_frame("cped-schema", frame(payload))
        self.assertEqual(result.output.strip(), payload)

    def test_nonzero_shell_status_is_retained(self):
        result = discovery.parse_frame("ubus-path", frame("not found", 127))
        self.assertEqual(result.exit_code, 127)

    def test_missing_or_invalid_frame_status_is_rejected_without_payload_leak(self):
        outputs = (
            PRIVATE,
            discovery.BEGIN + "\n" + PRIVATE,
            discovery.BEGIN + "\n" + discovery.END + "\n",
            discovery.BEGIN + "\n" + PRIVATE + "\n" + discovery.END + "\n",
            frame(PRIVATE, 256),
            frame(PRIVATE, -1),
            frame(PRIVATE, "0; reboot"),
        )
        for output in outputs:
            with self.subTest(output=output):
                try:
                    discovery.parse_frame("cped-schema", output)
                except router.RouterResponseError as error:
                    self.assertNotIn(PRIVATE, "".join(traceback.format_exception(error)))
                else:
                    self.fail("Expected an invalid frame to fail closed")

    def test_result_repr_omits_raw_payload(self):
        self.assertNotIn(PRIVATE, repr(discovery.ProbeResult("ubus-path", 0, PRIVATE)))


class ProbeTransportTests(OfflineCase):
    def fake_probe(self, response=(), banner=(b"synthetic shell\r\n# ",)):
        sock = DiscoverySocket(self.clock, response=response, banner=banner)
        self.connection.side_effect = None
        self.connection.return_value = sock
        return sock

    def test_reuses_transport_for_one_fixed_query_and_closes_socket(self):
        command = discovery.frame_command("ubus-path")
        sock = self.fake_probe((command, frame("/sbin/ubus").encode()))
        with patch.object(router, "fetch_sms_response", side_effect=AssertionError("SMS read forbidden")):
            result = discovery.run_query("ubus-path")
        self.assertEqual(result.output.strip(), "/sbin/ubus")
        self.assertEqual(sock.sent, [b"\r\n", command])
        self.connection.assert_called_once_with(("192.168.1.1", 2323), timeout=3.0)
        self.assertTrue(sock.closed)
        self.assertTrue(all(0 < timeout <= 0.1 for _, timeout in sock.io_timeouts))

    def test_echo_disabled_fragmented_frame_uses_shared_telnet_decoder(self):
        wire = (
            bytes((255, 251, 1)) + frame("/sbin/ubus").encode()
            + b'{"private":"' + PRIVATE.encode() + b'"}'
        )
        sock = self.fake_probe(tuple(bytes((byte,)) for byte in wire))
        result = discovery.run_query("ubus-path")
        self.assertEqual(result.output.strip(), "/sbin/ubus")
        self.assertNotIn(PRIVATE, result.output)
        self.assertIn(bytes((255, 254, 1)), sock.sent)
        self.assertTrue(sock.closed)

    def test_pre_cancelled_query_never_connects(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaises(router.RouterCancelledError):
            discovery.run_query("ubus-path", stop_event=stop)
        self.connection.assert_not_called()

    def test_invalid_query_host_port_and_timeout_never_connect(self):
        options = (
            {"query": "reboot"},
            {"host": "router.invalid"},
            {"host": "192.168.1.1; reboot"},
            {"port": 0},
            {"port": 65536},
            {"timeout": 0},
            {"timeout": -1},
            {"timeout": 61},
            {"timeout": float("nan")},
            {"timeout": float("inf")},
        )
        for option in options:
            with self.subTest(option=option):
                kwargs = dict(option)
                query = kwargs.pop("query", "ubus-path")
                with self.assertRaises(ValueError):
                    discovery.run_query(query, **kwargs)
        self.connection.assert_not_called()

    def test_login_prompt_stops_before_any_shell_command(self):
        sock = self.fake_probe(banner=(b"login: " + PRIVATE.encode(),))
        with self.assertRaises(router.RouterLoginRequiredError):
            discovery.run_query("ubus-path")
        self.assertEqual(sock.sent, [])
        self.assertTrue(sock.closed)

    def test_delayed_login_prompt_stops_before_discovery_command(self):
        for prompt in (b"login: ", b"Password: "):
            with self.subTest(prompt=prompt):
                sock = self.fake_probe()
                sock.phases["wakeup"] = deque((prompt + PRIVATE.encode(),))
                with self.assertRaises(router.RouterLoginRequiredError):
                    discovery.run_query("ubus-path")
                self.assertEqual(sock.sent, [b"\r\n"])
                self.assertTrue(sock.closed)

    def test_one_deadline_bounds_missing_completion_and_cleanup(self):
        sock = self.fake_probe()
        started = self.clock.now
        with self.assertRaises(router.RouterTimeoutError):
            discovery.run_query("ubus-path", timeout=1.5)
        self.assertLess(self.clock.now - started, 1.8)
        self.assertTrue(sock.closed)

    def test_cooperative_cancellation_during_response_closes_socket(self):
        stop = threading.Event()

        def cancel(_):
            stop.set()
            return b"unfinished response"

        sock = self.fake_probe((cancel,))
        with self.assertRaises(router.RouterCancelledError):
            discovery.run_query("ubus-path", stop_event=stop)
        self.assertTrue(sock.closed)

    def test_keyboard_interrupt_during_response_still_closes_socket(self):
        sock = self.fake_probe((KeyboardInterrupt(),))
        with self.assertRaises(KeyboardInterrupt):
            discovery.run_query("ubus-path")
        self.assertTrue(sock.closed)

    def test_raw_byte_limit_applies_to_discovery_responses(self):
        sock = self.fake_probe((b"x" * (discovery.MAX_BYTES + 1),))
        with self.assertRaises(router.RouterResponseError):
            discovery.run_query("ubus-path")
        self.assertTrue(sock.closed)

    def test_disconnect_and_os_failure_are_sanitized_and_closed(self):
        for failure, expected in (
            (b"", router.RouterDisconnectedError),
            (ConnectionResetError(PRIVATE), router.RouterDisconnectedError),
            (OSError(PRIVATE), router.RouterConnectionError),
        ):
            with self.subTest(failure=type(failure).__name__):
                sock = self.fake_probe((failure,))
                try:
                    discovery.run_query("ubus-path")
                except expected as error:
                    self.assertNotIn(PRIVATE, "".join(traceback.format_exception(error)))
                else:
                    self.fail("Expected sanitized discovery failure")
                self.assertTrue(sock.closed)


class DiscoveryPrivacyTests(unittest.TestCase):
    def rendered(self, query, output):
        return json.dumps(discovery.summarize(discovery.ProbeResult(query, 0, output)))

    def test_unstructured_values_are_omitted_from_normal_summaries(self):
        for query in READ_ONLY_QUERIES:
            with self.subTest(query=query):
                output = "password=" + PRIVATE + "\n8988000000000000001\n09900000001\nOTP 123456"
                rendered = self.rendered(query, output)
                for sensitive in (PRIVATE, "8988000000000000001", "09900000001", "123456"):
                    self.assertNotIn(sensitive, rendered)

    def test_unknown_object_names_are_not_trusted_as_safe_console_values(self):
        rendered = self.rendered("ubus-objects", "cped\n" + PRIVATE + "\n")
        self.assertNotIn(PRIVATE, rendered)

    def test_unknown_schema_method_and_argument_keys_are_not_printed(self):
        for output in (
            '  "' + PRIVATE + '":{"cmd":"String"}',
            '  "cmd":{"' + PRIVATE + '":"String"}',
            '  "cmd":{"arg":"' + PRIVATE + '"}',
        ):
            with self.subTest(output=output):
                self.assertNotIn(PRIVATE, self.rendered("cped-schema", output))

    def test_firmware_looking_secrets_are_not_printed_verbatim(self):
        output = "DISTRIB_DESCRIPTION='" + PRIVATE + "'\nDISTRIB_ID='OpenWrt'"
        self.assertNotIn(PRIVATE, self.rendered("firmware-release", output))

    def test_malformed_schema_json_does_not_echo_raw_line(self):
        output = '  "cmd":{"arg": ' + PRIVATE + "}\nnot JSON " + PRIVATE
        self.assertNotIn(PRIVATE, self.rendered("cped-schema", output))

    def test_known_ubus_metadata_is_available_without_unknown_values(self):
        objects = discovery.summarize(
            discovery.ProbeResult("ubus-objects", 0, "cped\nnetwork.interface.wan\n" + PRIVATE)
        )
        self.assertEqual(objects["objects"], ["cped", "network.interface.wan"])
        schema = discovery.summarize(
            discovery.ProbeResult("cped-schema", 0, '  "cmd":{"cmd":"String","arg":"String"}')
        )
        self.assertEqual(schema["methods"], {"cmd": {"cmd": "String", "arg": "String"}})

    def test_reviewed_firmware_fields_preserve_numeric_release(self):
        output = (
            "DISTRIB_ID='OpenWrt'\nDISTRIB_RELEASE='23.05.3'\n"
            "DISTRIB_TARGET='ramips/mt7621'\nDISTRIB_DESCRIPTION='" + PRIVATE + "'"
        )
        result = discovery.summarize(discovery.ProbeResult("firmware-release", 0, output))
        self.assertEqual(
            result["release"],
            {"DISTRIB_ID": "OpenWrt", "DISTRIB_RELEASE": "23.05.3", "DISTRIB_TARGET": "ramips/mt7621"},
        )
        self.assertNotIn(PRIVATE, json.dumps(result))

    def test_help_reports_only_known_option_and_operation_names(self):
        result = discovery.summarize(
            discovery.ProbeResult("ubus-help", 0, "Usage: ubus -t <timeout> -v\n list [path]\n call <path>\n" + PRIVATE)
        )
        self.assertEqual(result["advertised"], ["-t", "-v", "list", "call"])
        self.assertNotIn(PRIVATE, json.dumps(result))


class DiscoveryCapabilitySummaryTests(unittest.TestCase):
    """Summaries retain observable shapes without claiming cellular semantics."""

    def summary(self, query, output, status=0):
        return discovery.summarize(discovery.ProbeResult(query, status, output))

    def assert_private_values_omitted(self, result, *values):
        rendered = json.dumps(result)
        for value in (PRIVATE, *values):
            self.assertNotIn(value, rendered)

    def test_source_index_omits_unknown_paths_and_reports_their_count(self):
        output = "/www/js/config.js\n/www/js/page.js\n/www/js/" + PRIVATE + ".js\n"
        for query in ("web-file-index", "web-sms-source-index"):
            with self.subTest(query=query):
                result = self.summary(query, output)
                self.assertEqual(result["source_paths"], ["/www/js/config.js", "/www/js/page.js"])
                self.assertEqual(result["unreported_line_count"], 1)
                self.assert_private_values_omitted(result)

    def test_static_source_candidates_do_not_expose_config_values(self):
        output = (
            'const requests = ["sim.get.info", "network.getstatus", "sms.get.inboxdata"];\n'
            'const password = "' + PRIVATE + '";\n'
            'const imsi = "515000000000001";\n'
        )
        for query in ("web-config-source", "web-page-source"):
            with self.subTest(query=query):
                result = self.summary(query, output)
                self.assertEqual(result["operation_name_candidates"], ["sms.get.inboxdata"])
                self.assertEqual(result["source_line_count"], 3)
                self.assert_private_values_omitted(result, "515000000000001")
                self.assertNotIn("operator", result)
                self.assertNotIn("carrier", result)

    def test_status_name_index_requires_reviewed_source_and_candidate_components(self):
        output = (
            "/www/js/config.js:sim.get.info\n"
            "/www/js/" + PRIVATE + ".js:sim.get.info\n"
            "/www/js/config.js:sim.get." + PRIVATE + "\n"
        )
        result = self.summary("web-status-name-index", output)
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["unreported_line_count"], 3)
        self.assert_private_values_omitted(result)

    def test_capability_references_are_counts_without_source_or_field_values(self):
        output = (
            "/www/js/config.js:ICCID\n/www/js/config.js:iccid\n"
            "/www/js/" + PRIVATE + ".js:plmn\n"
            "/www/js/config.js:515000000000001\n"
        )
        result = self.summary("web-capability-references", output)
        self.assertEqual(result["field_name_references"], {"iccid": 2, "plmn": 1})
        self.assertEqual(result["matching_source_count"], 2)
        self.assertIn("not observed cellular values", result["meaning"])
        self.assert_private_values_omitted(result, "515000000000001", "/www/js/config.js")

    def test_ip_addresses_expose_families_scopes_and_flags_without_ip_or_mac(self):
        output = (
            "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state UP\n"
            "    link/ether 02:00:00:00:00:01 brd ff:ff:ff:ff:ff:ff\n"
            "    inet 192.0.2.7/24 brd 192.0.2.255 scope global eth0\n"
            "    inet6 2001:db8::7/64 scope global\n"
            "    inet6 fe80::7/64 scope link\n"
        )
        result = self.summary("ip-addresses", output)
        self.assertEqual(result["interfaces"], [{
            "interface": "eth0",
            "flags": ["BROADCAST", "MULTICAST", "UP", "LOWER_UP"],
            "addresses": [
                {"family": 4, "scope": "global", "prefix_length": 24, "address": "masked"},
                {"family": 6, "scope": "global", "prefix_length": 64, "address": "masked"},
                {"family": 6, "scope": "link", "prefix_length": 64, "address": "masked"},
            ],
        }])
        self.assertEqual(result["cellular_interface_binding"], "unverified")
        self.assert_private_values_omitted(result, "192.0.2.7", "192.0.2.255", "2001:db8::7", "fe80::7", "02:00:00:00:00:01")

    def test_unknown_interface_preserves_neutral_state_with_name_omitted(self):
        output = (
            "3: " + PRIVATE + ": <UP,LOWER_UP> mtu 1500 state UP\n"
            "    inet 198.51.100.7/30 scope global " + PRIVATE + "\n"
        )
        result = self.summary("ip-addresses", output)
        self.assertEqual(result["unreported_interface_count"], 1)
        self.assertEqual(result["interfaces"], [{
            "interface": "omitted", "flags": ["UP", "LOWER_UP"],
            "addresses": [{"family": 4, "scope": "global", "prefix_length": 30, "address": "masked"}],
        }])
        self.assert_private_values_omitted(result, "198.51.100.7")

    def test_invalid_ip_addresses_and_unknown_flags_are_not_promoted(self):
        output = (
            "2: eth0: <UP," + PRIVATE + "> mtu 1500\n"
            "    inet 999.0.2.7/24 scope global eth0\n"
            "    inet6 2001:db8::7/999 scope global\n"
        )
        result = self.summary("ip-addresses", output)
        self.assertEqual(result["interfaces"], [{"interface": "eth0", "flags": ["UP"], "addresses": []}])
        self.assert_private_values_omitted(result, "999.0.2.7", "2001:db8::7")

    def test_unknown_dotted_interface_addresses_do_not_attach_to_previous_interface(self):
        output = (
            "2: eth0: <UP> mtu 1500\n"
            "    inet 192.0.2.7/24 scope global eth0\n"
            "3: " + PRIVATE + ".100: <UP,LOWER_UP> mtu 1500\n"
            "    inet 198.51.100.7/24 scope global " + PRIVATE + ".100\n"
        )
        result = self.summary("ip-addresses", output)
        self.assertEqual(result["unreported_interface_count"], 1)
        self.assertEqual(len(result["interfaces"]), 2)
        self.assertEqual(result["interfaces"][0]["interface"], "eth0")
        self.assertEqual(len(result["interfaces"][0]["addresses"]), 1)
        self.assertEqual(result["interfaces"][1]["interface"], "omitted")
        self.assertEqual(result["interfaces"][1]["addresses"], [
            {"family": 4, "scope": "global", "prefix_length": 24, "address": "masked"},
        ])
        self.assert_private_values_omitted(result, "192.0.2.7", "198.51.100.7")

    def test_unparseable_interface_header_cannot_inherit_previous_address_target(self):
        output = (
            "2: eth0: <UP> mtu 1500\n"
            "    inet 192.0.2.7/24 scope global eth0\n"
            "3: invalid header " + PRIVATE + "\n"
            "    inet 198.51.100.7/24 scope global unknown\n"
        )
        result = self.summary("ip-addresses", output)
        self.assertEqual(result["unreported_interface_count"], 1)
        self.assertEqual(len(result["interfaces"]), 1)
        self.assertEqual(len(result["interfaces"][0]["addresses"]), 1)
        self.assert_private_values_omitted(result, "192.0.2.7", "198.51.100.7")

    def test_ipv4_routes_mask_gateway_and_count_unknown_default_interfaces(self):
        output = (
            "default via 192.0.2.1 dev eth0 metric 10\n"
            "default via 198.51.100.1 dev " + PRIVATE + "\n"
            "192.0.2.0/24 dev eth0 src 192.0.2.7\n"
        )
        result = self.summary("ip-routes", output)
        self.assertEqual(result["ipv4_default_routes"], [{"interface": "eth0", "gateway": "masked"}])
        self.assertEqual(result["unreported_default_route_count"], 1)
        self.assertEqual(result["cellular_interface_binding"], "unverified")
        self.assert_private_values_omitted(result, "192.0.2.1", "198.51.100.1", "192.0.2.7")

    def test_ipv6_routes_mask_gateway_and_retain_route_family(self):
        output = (
            "default via 2001:db8::1 dev wwan0 metric 1024\n"
            "default via fe80::1 dev " + PRIVATE + " metric 2048\n"
        )
        result = self.summary("ipv6-routes", output)
        self.assertEqual(result["ipv6_default_routes"], [{"interface": "wwan0", "gateway": "masked"}])
        self.assertEqual(result["unreported_default_route_count"], 1)
        self.assertEqual(result["cellular_interface_binding"], "unverified")
        self.assert_private_values_omitted(result, "2001:db8::1", "fe80::1")

    def test_usb_descriptors_report_reviewed_metadata_without_serial(self):
        output = (
            "1-1 idVendor=2C7C\n1-1 idProduct=0123\n1-1 manufacturer=Quectel\n"
            "1-1 product=EG060V-EAAA\n1-1 serial=" + PRIVATE + "\n"
        )
        result = self.summary("usb-descriptors", output)
        self.assertEqual(result["devices"], {"1-1": {
            "idVendor_present": True, "idVendor": "2c7c",
            "idProduct_present": True, "idProduct": "0123",
            "manufacturer_present": True, "manufacturer": "Quectel",
            "product_present": True, "product": "EG060V-EAAA",
        }})
        self.assert_private_values_omitted(result, "serial")

    def test_unknown_usb_strings_retain_presence_without_values(self):
        output = (
            "1-1 idVendor=" + PRIVATE + "\n1-1 idProduct=FFFF\n"
            "1-1 manufacturer=" + PRIVATE + "\n1-1 product=" + PRIVATE + "\n"
            + PRIVATE + " product=EG060V-EAAA\n"
        )
        result = self.summary("usb-descriptors", output)
        self.assertEqual(result["devices"], {"1-1": {
            "idVendor_present": True, "idProduct_present": True, "idProduct": "ffff",
            "manufacturer_present": True, "product_present": True,
        }})
        self.assert_private_values_omitted(result)

    def test_identifier_like_usb_product_cannot_bypass_model_allowlist(self):
        identifier = "515000000000001"
        result = self.summary("usb-descriptors", "1-1 product=EG" + identifier + "\n")
        self.assertEqual(result["devices"], {"1-1": {"product_present": True}})
        self.assert_private_values_omitted(result, identifier)

    def test_usb_network_binding_correlates_bus_and_default_route_families(self):
        output = (
            "wwan0|/sys/devices/platform/usb1/1-1/1-1:1.4|v4v6\n"
            "usb0|/sys/devices/platform/usb1/1-2/1-2:1.0|v4\n"
            "wwan1|/sys/devices/platform/usb1/1-2/1-2.1/1-2.1:1.0|v6\n"
        )
        result = self.summary("usb-network-binding", output)
        self.assertEqual(result["usb_network_interfaces"], [
            {"interface": "wwan0", "usb_device": "1-1", "ipv4_default": True, "ipv6_default": True},
            {"interface": "usb0", "usb_device": "1-2", "ipv4_default": True, "ipv6_default": False},
            {"interface": "wwan1", "usb_device": "1-2.1", "ipv4_default": False, "ipv6_default": True},
        ])
        self.assertIn("not SIM or registration evidence", result["meaning"])

    def test_usb_binding_omits_unknown_names_and_private_parent_path(self):
        output = PRIVATE + "|/sys/devices/" + PRIVATE + "/usb1/1-1/1-1:1.4|\n"
        result = self.summary("usb-network-binding", output)
        self.assertEqual(result["usb_network_interfaces"], [
            {"interface": "omitted", "usb_device": "1-1", "ipv4_default": False, "ipv6_default": False},
        ])
        self.assert_private_values_omitted(result, "/sys/devices/")

    def test_malformed_usb_binding_rows_do_not_become_device_evidence(self):
        output = (
            "wwan0|/sys/devices/usb1/1-1/1-1:1.4|v4v6|extra\n"
            "wwan0|/sys/devices/usb1/1-1/1-1:1.4|" + PRIVATE + "\n"
            "wwan0|/sys/devices/usb1/1-1/1-1:1.4\n"
            "not a binding " + PRIVATE + "\n"
        )
        result = self.summary("usb-network-binding", output)
        self.assertEqual(result["usb_network_interfaces"], [])
        self.assert_private_values_omitted(result)

    def test_non_usb_network_devices_are_not_reported_as_usb_bindings(self):
        output = (
            "eth0|/sys/devices/platform/synthetic-ethernet|v4\n"
            "wlan0|/sys/devices/pci0000:00/0000:00:00.0|v6\n"
        )
        result = self.summary("usb-network-binding", output)
        self.assertEqual(result["usb_network_interfaces"], [])

    def test_resolver_retains_only_valid_address_families(self):
        output = (
            "nameserver 192.0.2.53\nnameserver 2001:db8::53\n"
            "nameserver " + PRIVATE + "\nsearch " + PRIVATE + "\n"
        )
        result = self.summary("resolver-state", output)
        self.assertEqual(result["nameserver_families"], [4, 6])
        self.assertEqual(result["nameserver_addresses"], "masked")
        self.assertEqual(result["cellular_dns_binding"], "unverified")
        self.assert_private_values_omitted(result, "192.0.2.53", "2001:db8::53")

    def test_apn_declarations_are_counted_without_values_or_active_context_claim(self):
        output = "\toption apn '" + PRIVATE + "'\n  option apn 'private.example'\n"
        result = self.summary("configured-apn-presence", output)
        self.assertEqual(result["apn_declaration_count"], 2)
        self.assertTrue(result["source_read_succeeded"])
        self.assertEqual(result["apn_values"], "omitted")
        self.assertIn("not active PDP/APN proof", result["meaning"])
        self.assert_private_values_omitted(result, "private.example")

    def test_apn_query_failure_is_retained_and_cannot_be_read_as_successful_absence(self):
        result = self.summary("configured-apn-presence", "grep: " + PRIVATE, status=2)
        self.assertEqual(result["exit_code"], 2)
        self.assertFalse(result["source_read_succeeded"])
        self.assertEqual(result["apn_declaration_count"], 0)
        self.assertNotIn("apn_absent", result)
        self.assert_private_values_omitted(result)


class DiscoveryCliAndCaptureTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket", side_effect=AssertionError("Real sockets forbidden")))
        self.enterContext(patch("socket.create_connection", side_effect=AssertionError("Real connections forbidden")))
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        self.enterContext(redirect_stdout(self.stdout))
        self.enterContext(redirect_stderr(self.stderr))
        self.signals = self.enterContext(patch.object(discovery.signal, "signal", return_value="previous"))

    def test_list_queries_is_inert_and_contains_only_fixed_commands(self):
        with patch.object(discovery, "run_query") as run:
            self.assertEqual(discovery.main(["--list-queries"]), 0)
        run.assert_not_called()
        self.signals.assert_not_called()
        self.assertEqual(json.loads(self.stdout.getvalue()), READ_ONLY_QUERIES)

    def test_browser_script_is_offline_and_does_not_install_signal_or_capture(self):
        with patch.object(discovery, "run_query") as run:
            with patch.object(discovery, "capture_raw") as capture:
                self.assertEqual(discovery.main(["--browser-script"]), 0)
        run.assert_not_called()
        capture.assert_not_called()
        self.signals.assert_not_called()
        expected = Path(discovery.__file__).with_name("d2_browser_probe.js").read_text(encoding="utf-8")
        self.assertEqual(self.stdout.getvalue(), expected)

    def test_browser_script_rejects_hardware_query_and_raw_capture_combinations(self):
        for options in (["--query", "ubus-path"], ["--capture-raw"]):
            with self.subTest(options=options):
                with patch.object(discovery, "run_query") as run:
                    with patch.object(discovery, "capture_raw") as capture:
                        with self.assertRaises(SystemExit) as error:
                            discovery.main(["--browser-script", *options])
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()
                capture.assert_not_called()

    def test_hardware_access_requires_explicit_valid_query(self):
        for args in ([], ["--query", "reboot"], ["--command", "AT+CSQ"]):
            with self.subTest(args=args):
                with patch.object(discovery, "run_query") as run:
                    with self.assertRaises(SystemExit) as error:
                        discovery.main(args)
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()

    def test_default_console_output_never_captures_raw_response(self):
        result = discovery.ProbeResult("ubus-path", 0, PRIVATE)
        with patch.object(discovery, "run_query", return_value=result) as run:
            with patch.object(discovery, "capture_raw") as capture:
                self.assertEqual(discovery.main(["--query", "ubus-path"]), 0)
        capture.assert_not_called()
        self.assertNotIn(PRIVATE, self.stdout.getvalue() + self.stderr.getvalue())
        self.assertIsInstance(run.call_args.kwargs["stop_event"], threading.Event)
        self.assertEqual(self.signals.call_args, ((signal.SIGINT, "previous"),))

    def test_raw_capture_requires_explicit_flag(self):
        result = discovery.ProbeResult("ubus-path", 0, PRIVATE)
        with patch.object(discovery, "run_query", return_value=result):
            with patch.object(discovery, "capture_raw") as capture:
                self.assertEqual(discovery.main(["--query", "ubus-path", "--capture-raw"]), 0)
        capture.assert_called_once_with(result)
        self.assertNotIn(PRIVATE, self.stdout.getvalue() + self.stderr.getvalue())

    def test_nonzero_remote_exit_is_a_cli_failure(self):
        result = discovery.ProbeResult("ubus-path", 127, PRIVATE)
        with patch.object(discovery, "run_query", return_value=result):
            self.assertEqual(discovery.main(["--query", "ubus-path"]), 1)
        self.assertNotIn(PRIVATE, self.stdout.getvalue() + self.stderr.getvalue())

    def test_cli_errors_omit_sensitive_exception_values_and_restore_signal(self):
        for error in (router.RouterResponseError(PRIVATE), OSError(PRIVATE), ValueError(PRIVATE)):
            with self.subTest(error=type(error).__name__):
                with patch.object(discovery, "run_query", side_effect=error):
                    self.assertEqual(discovery.main(["--query", "ubus-path"]), 1)
                self.assertNotIn(PRIVATE, self.stdout.getvalue() + self.stderr.getvalue())
                self.assertEqual(self.signals.call_args, ((signal.SIGINT, "previous"),))

    def test_ctrl_c_sets_cooperative_stop_and_returns_cancelled_status(self):
        def interrupt(query, **options):
            handler = self.signals.call_args.args[1]
            handler(signal.SIGINT, None)
            self.assertTrue(options["stop_event"].is_set())
            raise router.RouterCancelledError(PRIVATE)

        with patch.object(discovery, "run_query", side_effect=interrupt):
            self.assertEqual(discovery.main(["--query", "ubus-path"]), 130)
        self.assertNotIn(PRIVATE, self.stdout.getvalue() + self.stderr.getvalue())
        self.assertEqual(self.signals.call_args, ((signal.SIGINT, "previous"),))

    def test_keyboard_interrupt_returns_cancelled_status(self):
        with patch.object(discovery, "run_query", side_effect=KeyboardInterrupt()):
            self.assertEqual(discovery.main(["--query", "ubus-path"]), 130)
        self.assertEqual(self.signals.call_args, ((signal.SIGINT, "previous"),))

    def test_cancellation_after_query_prevents_raw_capture_and_summary(self):
        def cancelled_result(query, **options):
            options["stop_event"].set()
            return discovery.ProbeResult(query, 0, PRIVATE)

        with patch.object(discovery, "run_query", side_effect=cancelled_result):
            with patch.object(discovery, "capture_raw") as capture:
                self.assertEqual(discovery.main(["--query", "ubus-path", "--capture-raw"]), 130)
        capture.assert_not_called()
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertNotIn(PRIVATE, self.stderr.getvalue())

    def test_explicit_raw_capture_writes_only_fixed_ignored_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "artifacts" / "d2-private"
            (root / ".gitignore").write_text(discovery.RAW_IGNORE_RULE + "\n", encoding="utf-8")
            with patch.object(discovery, "PROJECT_ROOT", root):
                with patch.object(discovery, "RAW_DIRECTORY", raw):
                    discovery.capture_raw(discovery.ProbeResult("ubus-path", 0, PRIVATE))
            files = list(raw.iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_text(encoding="utf-8"), PRIVATE)
            self.assertEqual(files[0].parent, raw)

    def test_missing_ignore_rule_prevents_raw_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "artifacts" / "d2-private"
            (root / ".gitignore").write_text("*.log\n", encoding="utf-8")
            with patch.object(discovery, "PROJECT_ROOT", root):
                with patch.object(discovery, "RAW_DIRECTORY", raw):
                    with self.assertRaises(ValueError):
                        discovery.capture_raw(discovery.ProbeResult("ubus-path", 0, PRIVATE))
            self.assertFalse(raw.exists())

    def test_arbitrary_capture_directory_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".gitignore").write_text(discovery.RAW_IGNORE_RULE + "\n", encoding="utf-8")
            unsafe = root / "tracked-fixtures"
            with patch.object(discovery, "PROJECT_ROOT", root):
                with patch.object(discovery, "RAW_DIRECTORY", unsafe):
                    with self.assertRaises(ValueError):
                        discovery.capture_raw(discovery.ProbeResult("ubus-path", 0, PRIVATE))
            self.assertFalse(unsafe.exists())


if __name__ == "__main__":
    unittest.main()

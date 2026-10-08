"""Manual, read-only D2 discovery. Not imported by the application.

Only reviewed, fixed commands are supported. Method discovery does not establish
that a vendor method is safe to call. Normal output is an allowlisted summary;
raw transcripts are transient unless --capture-raw is explicitly supplied.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import ipaddress
import json
from pathlib import Path
import re
import signal
import socket
import sys
import threading
import time
import uuid

from sim_manager.devices.d2 import router

if __package__:
    from . import d2_source_evidence as evidence
else:
    import d2_source_evidence as evidence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIRECTORY = PROJECT_ROOT / 'artifacts' / 'd2-private'
RAW_IGNORE_RULE = '/artifacts/d2-private/'
BEGIN = '__SIM_MANAGER_PROBE_BEGIN__'
END = '__SIM_MANAGER_PROBE_END__'
EXIT = '__SIM_MANAGER_PROBE_EXIT_'
MAX_BYTES = 256 * 1024

# Fixed metadata, static-file reads, and documented network show operations.
# No vendor methods, configuration setters, modem device nodes, or SMS reads.
# Flags for later metadata probes must first be checked against ubus-help.
QUERIES = {
    'ubus-path': 'command -v ubus',
    'ubus-help': 'ubus -h',
    'ubus-objects': 'ubus -t 5 list',
    'cped-schema': 'ubus -t 5 -v list cped',
    'firmware-release': 'cat /etc/openwrt_release',
    'web-file-index': 'find /www -maxdepth 4 -type f',
    'web-entry-source': 'cat /www/index.html',
    # These script references were observed directly in index.html (Task 004).
    'web-ajax-source': 'cat /www/js/ajax.js',
    'web-init-source': 'cat /www/js/init.js',
    'web-tri-source': 'cat /www/js/tri.js',
    'web-project-source': 'cat /www/js/project.js',
    # Status templates were observed in the fixed /www file listing.
    'web-dongle-status-source': 'cat /www/page/status/status_dongle.shtml',
    'web-device-status-source': 'cat /www/page/status/status_info.shtml',
    'web-wan-status-source': 'cat /www/page/status/status_wannetwork.shtml',
    'web-hidden-source': 'cat /www/page/hidden_noauth/index.html',
    'web-utils-source': 'cat /www/js/t_utils.js',
    'web-menu-source': 'cat /www/js/menu.js',
    'web-project-menu-source': 'cat /www/js/project_menu.js',
    'web-menu-template-source': 'cat /www/menu.shtml',
    'web-cellular-template-references': "find /www -maxdepth 4 -type f \\( -name '*.shtml' -o -name '*.html' -o -name '*.js' -o -name '*.cgi' \\) -exec grep -H -i -n -oE 'rssi|rsrp|rsrq|sinr|earfcn|iccid|imsi|msisdn|plmn|mcc|mnc|operator|WANDongleInterfaceConfig|cped|ubus|ajax|XMLHttpRequest' {} \\;",
    'web-server-processes': 'ps',
    'web-listening-sockets': 'cat /proc/net/tcp /proc/net/tcp6',
    # /opt/web/start.sh was observed in process metadata; read, never execute.
    'web-opt-start-source': 'cat /opt/web/start.sh',
    'web-opt-file-index': 'find /opt/web -maxdepth 4 -type f',
    'web-opt-index-source': 'cat /opt/web/views/index.html',
    'web-opt-index-template-source': 'cat /opt/web/views/index.tpl',
    'web-opt-server-config': "grep -E '^[[:space:]]*(appname|httpaddr|httpport|httpsaddr|httpsport|EnableHTTP|EnableHTTPS|runmode)[[:space:]]*=' /opt/web/conf/app.conf /opt/web/conf/app_https.conf",
    'web-opt-server-certificate': 'cat /opt/web/conf/server.crt',
    'web-opt-app-source-evidence': "tr ';{}' '\\n' < /opt/web/static/js/app.5af0ce0f.js | grep -iE 'rsrp|rsrq|sinr|rssi|earfcn|iccid|imsi|msisdn|plmn|cped|ubus|sms.get.inboxdata|network.get|sim.get'",
    'web-opt-request-catalog': "tr ';{}' '\\n' < /opt/web/static/js/app.5af0ce0f.js | grep -E 'url:|baseURL|Authorization|withCredentials|X-Token|csrf'",
    'web-opt-auth-source-evidence': "tr ';{}' '\\n' < /opt/web/static/js/app.5af0ce0f.js | grep -B 4 -A 5 -E 'Authorization|withCredentials|localStorage.getItem|sessionStorage.getItem'",
    'web-opt-dashboard-call-evidence': "tr ';{}' '\\n' < /opt/web/static/js/app.5af0ce0f.js | grep -B 6 -A 10 -E 'url:\"/web/v1/(dashboard/(wirelessinfo|internetinfo|waninfo|deviceinfo)|status/wanstatus|setting/network/pinmanagement/simcardinfo|setting/deviceinfo)\"'",
    'web-opt-dashboard-view-evidence': "tr ';{}' '\\n' < /opt/web/static/js/chunk-a65ab4a6.3cfa7746.js | grep -i -B 5 -A 8 -E 'rsrp|rsrq|sinr|rssi|iccid|imsi|plmn|simstatus|wirelessinfo|internetinfo|waninfo|deviceinfo|simcardinfo'",
    'web-opt-cellular-field-index': "grep -H -i -oE 'iccid|imsi|msisdn|plmn|rsrp|rsrq|sinr|rssi|earfcn|pci|simstate|simstatus|pinstate|operatorname|networktype|apn|wirelessinfo|internetinfo|waninfo|deviceinfo' /opt/web/static/js/app.5af0ce0f.js /opt/web/static/js/chunk-a65ab4a6.3cfa7746.js /opt/web/static/js/chunk-ff19fe88.a86a0aee.js /opt/web/static/js/chunk-508c212a.59fd7df1.js",
    'web-http-client-capability': 'command -v wget; wget --help',
    # Paths directly observed in web-file-index; static source, never executed.
    'web-config-source': 'cat /www/js/config.js',
    'web-page-source': 'cat /www/js/page.js',
    'web-sms-source-index': "find /www -maxdepth 4 -type f \\( -name '*.js' -o -name '*.html' \\) -exec grep -l 'sms.get.inboxdata' {} \\;",
    'web-status-name-index': "find /www -maxdepth 4 -type f \\( -name '*.js' -o -name '*.html' \\) -exec grep -H -oE '(sim|network|lte|wan|modem|device|system|internet)\\.(get|status|info)[a-z0-9_.]*' {} \\;",
    # Observational ip 'show' forms: busybox.net/downloads/BusyBox.html.
    'ip-addresses': 'ip address show',
    'ip-routes': 'ip route show',
    # Linux USB ABI metadata only; deliberately exclude serial/device nodes.
    'usb-descriptors': 'for d in /sys/bus/usb/devices/*; do for f in idVendor idProduct manufacturer product; do if [ -f "$d/$f" ]; then printf "%s %s=" "${d##*/}" "$f"; cat "$d/$f"; fi; done; done',
    'web-capability-references': "find /www -maxdepth 4 -type f \\( -name '*.js' -o -name '*.html' \\) -exec grep -H -i -oE 'iccid|imsi|msisdn|plmn|mcc|mnc|rsrp|rsrq|sinr|rssi|earfcn|roaming|registration|quectel|apn|ipv4|ipv6|operator' {} \\;",
    'ipv6-routes': 'ip -f inet6 route show',
    'resolver-state': 'cat /etc/resolv.conf',
    # Filter only APN declarations; never dump credentials/configuration.
    'configured-apn-presence': "grep -E '^[[:space:]]*option[[:space:]]+apn[[:space:]]' /etc/config/network",
    # Correlate already observed default routes with USB device symlinks. Shell
    # variables are session-local; no network/configuration writes are performed.
    'usb-network-binding': 'v4dev="$(ip route show | sed -n \'s/^default .*dev \\([^ ]*\\).*/\\1/p\')"; v6dev="$(ip -f inet6 route show | sed -n \'s/^default .*dev \\([^ ]*\\).*/\\1/p\')"; for n in /sys/class/net/*; do if [ -e "$n/device" ]; then printf "%s|%s|" "${n##*/}" "$(readlink -f "$n/device")"; if [ "${n##*/}" = "$v4dev" ]; then printf v4; fi; if [ "${n##*/}" = "$v6dev" ]; then printf v6; fi; printf "\\n"; fi; done',
}
SOURCE_FILES = {
    'web-entry-source': '/www/index.html',
    'web-config-source': '/www/js/config.js',
    'web-page-source': '/www/js/page.js',
    'web-ajax-source': '/www/js/ajax.js',
    'web-init-source': '/www/js/init.js',
    'web-tri-source': '/www/js/tri.js',
    'web-project-source': '/www/js/project.js',
    'web-dongle-status-source': '/www/page/status/status_dongle.shtml',
    'web-device-status-source': '/www/page/status/status_info.shtml',
    'web-wan-status-source': '/www/page/status/status_wannetwork.shtml',
    'web-hidden-source': '/www/page/hidden_noauth/index.html',
    'web-utils-source': '/www/js/t_utils.js',
    'web-menu-source': '/www/js/menu.js',
    'web-project-menu-source': '/www/js/project_menu.js',
    'web-menu-template-source': '/www/menu.shtml',
    'web-opt-start-source': '/opt/web/start.sh',
    'web-opt-index-source': '/opt/web/views/index.html',
    'web-opt-index-template-source': '/opt/web/views/index.tpl',
    'web-opt-app-source-evidence': '/opt/web/static/js/app.5af0ce0f.js',
    'web-opt-request-catalog': '/opt/web/static/js/app.5af0ce0f.js',
    'web-opt-auth-source-evidence': '/opt/web/static/js/app.5af0ce0f.js',
    'web-opt-dashboard-call-evidence': '/opt/web/static/js/app.5af0ce0f.js',
    'web-opt-dashboard-view-evidence': '/opt/web/static/js/chunk-a65ab4a6.3cfa7746.js',
}
KNOWN_OBJECTS = frozenset({
    'cped', 'system', 'network', 'network.device', 'network.interface',
    'network.interface.lan', 'network.interface.wan', 'network.interface.wan6',
    'network.interface.wwan', 'network.interface.wwan6', 'network.wireless',
    'session', 'service', 'uci', 'file', 'log', 'iwinfo', 'hostapd', 'dnsmasq',
})
KNOWN_METHODS = frozenset({'cmd', 'list', 'status', 'info', 'board'})
KNOWN_ARGUMENTS = frozenset({'cmd', 'arg', 'name', 'interface', 'device', 'verbose'})
SOURCE_WORDS = frozenset({
    'www', 'html', 'htm', 'js', 'json', 'lua', 'css', 'cgi', 'bin', 'lib',
    'static', 'assets', 'scripts', 'script', 'src', 'app', 'api', 'main',
    'index', 'home', 'common', 'config', 'configuration', 'status', 'system',
    'network', 'internet', 'wan', 'sim', 'lte', 'modem', 'device', 'router',
    'signal', 'login', 'settings', 'utils', 'util', 'service', 'services',
    'vendor', 'bundle', 'runtime', 'min', 'cpe', 'cped', 'web', 'webui',
    'controller', 'controllers', 'page', 'pages', 'components', 'angular',
    'jquery', 'bootstrap', 'require', 'public', 'dist', 'build', 'ui', 'view',
    'views', 'mobile', 'pc', 'desktop', 'sms', 'message', 'messages', 'net',
    'info', 'detail', 'basic', 'ubus', 'sys', 'sysinfo', 'netinfo', 'devinfo',
    'radio', 'cellular', 'connection', 'connect', 'statistics', 'dial',
    'dialup', 'information', 'setting', 'dashboard', 'overview', 'com',
    'tools', 'content', 'contents', 'management', 'manager', 'wifi', 'wlan',
})
REVIEWED_OPERATION_NAMES = frozenset({'sms.get.inboxdata'})


@dataclass(frozen=True)
class ProbeResult:
    query: str
    exit_code: int
    output: str = field(repr=False)


def _remaining(deadline: float, stop_event: threading.Event) -> float:
    router._check_cancelled(stop_event)
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise router.RouterTimeoutError('Discovery query deadline exceeded.') from None
    return remaining


def command_for(query: str) -> str:
    if query not in QUERIES:
        raise ValueError('Unknown discovery query.') from None
    return QUERIES[query]


def frame_command(query: str) -> bytes:
    # printf writes only to the Telnet stream. Capturing $? is observational.
    return (
        f"printf '\\n{BEGIN}\\n'; {command_for(query)}; "
        f"printf '\\n{EXIT}%s__\\n{END}\\n' \"$?\"\r\n"
    ).encode('ascii')


def parse_frame(query: str, output: str) -> ProbeResult:
    """Exclude command echo, prompts, and output outside the marked frame."""
    command_for(query)
    lines = output.splitlines()
    try:
        begin = lines.index(BEGIN)
        end = lines.index(END, begin + 1)
    except ValueError:
        raise router.RouterResponseError('Incomplete discovery frame.') from None
    if end <= begin + 1:
        raise router.RouterResponseError('Missing discovery command status.') from None
    status = re.fullmatch(re.escape(EXIT) + r'(\d{1,3})__', lines[end - 1])
    if status is None or int(status[1]) > 255:
        raise router.RouterResponseError('Invalid discovery command status.') from None
    return ProbeResult(query, int(status[1]), '\n'.join(lines[begin + 1:end - 1]))


def _source_path(value: str) -> bool:
    words = re.split(r'[/._-]', re.sub(r'([a-z])([A-Z])', r'\1_\2', value.lstrip('/')).lower())
    return value.startswith('/www/') and value.endswith(('.js', '.html', '.htm', '.lua', '.json')) and all(word in SOURCE_WORDS for word in words)


def _interface_name(value: str) -> bool:
    return value in ('lo', 'br-lan', 'wan', 'wan6', 'lte', 'wwan') or bool(re.fullmatch(r'(eth|wlan|ra|wwan|usb|rmnet_data|rmnet|apcli|ppp|br|ccmni|mhi)\d{1,2}', value))


def run_query(
    query: str,
    *,
    host: str = router.ROUTER_HOST,
    port: int = router.ROUTER_PORT,
    timeout: float = 8.0,
    stop_event: threading.Event | None = None,
) -> ProbeResult:
    """Run one fixed query; reuse the characterized transport without SMS reads."""
    command = frame_command(query)  # Reject unknown commands before connecting.
    try:
        ipaddress.ip_address(host)  # Avoid unresolved hostname worker accumulation.
    except ValueError:
        raise ValueError('Discovery host must be a literal IP address.') from None
    if not 1 <= port <= 65535 or not 0 < timeout <= 60:
        raise ValueError('Invalid discovery port or timeout.') from None
    stop = stop_event if stop_event is not None else threading.Event()
    deadline = router._deadline(timeout)
    decoder = router.TelnetDecoder()
    options = dict(decoder=decoder, stop_event=stop, max_response_bytes=MAX_BYTES)
    sock = None
    try:
        # These private helpers are deliberately reused only in a development
        # tool; Task 003 does not add a production arbitrary-command interface.
        sock = router._connect(host, port, min(3.0, _remaining(deadline, stop)), stop)
        banner = router.receive_some(sock, min(0.7, _remaining(deadline, stop)), **options)
        if 'login:' in banner.lower() or 'password:' in banner.lower():
            raise router.RouterLoginRequiredError('Discovery requires an existing direct shell.')
        router._send(sock, b'\r\n', stop)
        wakeup = router.receive_some(sock, min(0.25, _remaining(deadline, stop)), **options)
        if 'login:' in wakeup.lower() or 'password:' in wakeup.lower():
            raise router.RouterLoginRequiredError('Discovery requires an existing direct shell.')
        _remaining(deadline, stop)
        router._send(sock, command, stop)
        output = router.receive_until_marker_printed(sock, END, deadline=deadline, **options)
        _remaining(deadline, stop)
        return parse_frame(query, output)
    except router.RouterError:
        raise
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
        router._check_cancelled(stop)
        raise router.RouterDisconnectedError('Discovery connection interrupted.') from None
    except (socket.timeout, TimeoutError):
        router._check_cancelled(stop)
        raise router.RouterTimeoutError('Discovery query timed out.') from None
    except OSError:
        router._check_cancelled(stop)
        raise router.RouterConnectionError('Discovery connection failed.') from None
    finally:
        router._close_socket(sock)


def summarize(result: ProbeResult) -> dict:
    """Fail closed: do not print arbitrary banners, shell text, or unknown values."""
    summary: dict = {'query': result.query, 'command': command_for(result.query), 'exit_code': result.exit_code}
    lines = result.output.splitlines()
    if result.query == 'ubus-path':
        summary['ubus_found'] = any(line in ('/bin/ubus', '/sbin/ubus', '/usr/bin/ubus', '/usr/sbin/ubus') for line in lines)
    elif result.query == 'ubus-help':
        # Extract only known option/operation names, never whole help/error lines.
        summary['advertised'] = [word for word in ('-t', '-v', 'list', 'call') if re.search(r'(?<!\S)' + re.escape(word) + r'(?![A-Za-z])', result.output)]
    elif result.query == 'ubus-objects':
        summary['objects'] = sorted({line for line in lines if line in KNOWN_OBJECTS})
        summary['unreported_line_count'] = sum(bool(line.strip()) and line not in KNOWN_OBJECTS for line in lines)
    elif result.query == 'cped-schema':
        methods = {}
        for line in lines:
            match = re.fullmatch(r'\s*"([A-Za-z_][A-Za-z0-9_.-]{0,79})":(\{.*\})\s*', line)
            if match is None or match[1] not in KNOWN_METHODS:
                continue
            try:
                fields = json.loads(match[2])
            except (ValueError, RecursionError):
                continue
            if isinstance(fields, dict):
                methods[match[1]] = {key: value for key, value in fields.items() if key in KNOWN_ARGUMENTS and value in ('String', 'Integer', 'Boolean', 'Array', 'Table')}
        summary['methods'] = methods
    elif result.query == 'firmware-release':
        release = {}
        for line in lines:
            match = re.fullmatch(r"(DISTRIB_ID|DISTRIB_RELEASE|DISTRIB_REVISION|DISTRIB_TARGET|DISTRIB_DESCRIPTION)=['\"]?([A-Za-z0-9][A-Za-z0-9_. /-]{0,79})['\"]?", line)
            if match:
                key, value = match[1], match[2]
                if (
                    key == 'DISTRIB_ID' and value in ('OpenWrt', 'LEDE')
                    or key == 'DISTRIB_RELEASE' and (value == 'SNAPSHOT' or re.fullmatch(r'\d{1,2}\.\d{1,2}(?:\.\d{1,2})?(?:-rc\d)?', value))
                    or key == 'DISTRIB_REVISION' and re.fullmatch(r'r\d{1,6}-[0-9a-f]{7,12}', value)
                    or key == 'DISTRIB_TARGET' and value in ('ramips/mt7621', 'ipq40xx/generic', 'ipq60xx/generic', 'mediatek/filogic')
                ):
                    release[key] = value
        summary['release'] = release
    elif result.query in ('web-file-index', 'web-sms-source-index'):
        # Source paths are metadata, but unknown/hash/identifier-like components
        # are still omitted. Do not dump arbitrary directory names.
        paths = []
        for line in lines:
            if _source_path(line):
                paths.append(line)
        summary['source_paths'] = sorted(set(paths))
        summary['unreported_line_count'] = sum(bool(line.strip()) and line not in paths for line in lines)
    elif result.query in SOURCE_FILES:
        # Inspect literal operation names only, never emit full source/config.
        # Finding a getter name is not proof that executing it is read-only.
        # Component vocabularies admit arbitrary literals such as credentials
        # equal to "home.wifi". Export exact reviewed names only.
        candidates = {
            match[1] for match in re.finditer(r'''["']([a-z][a-z0-9_.-]{2,79})["']''', result.output)
            if match[1] in REVIEWED_OPERATION_NAMES
        }
        summary['operation_name_candidates'] = sorted(candidates)
        summary['recognized_terms'] = [word for word in ('ubus', 'cped', 'sms.get.inboxdata', 'sim', 'network', 'signal', 'wan', 'modem', 'ajax', 'XMLHttpRequest') if word in result.output]
        summary['source_line_count'] = len(lines)
        summary.update(evidence.summarize_source(result.output, SOURCE_FILES[result.query]))
        if result.query == 'web-opt-auth-source-evidence':
            summary['authentication'] = {
                'authorization_storage_reference': 'localStorage' in result.output and 'Authorization' in result.output,
                'with_credentials_reference': 'withCredentials' in result.output,
                'credential_values': 'omitted',
                'meaning': 'static reference only; not authenticated request verification',
            }
    elif result.query in ('web-cellular-template-references', 'web-opt-cellular-field-index'):
        summary.update(evidence.summarize_references(result.output))
    elif result.query == 'web-opt-file-index':
        summary['source_paths'] = sorted(set(lines) & evidence.KNOWN_PATHS)
        summary['unreported_line_count'] = sum(bool(line.strip()) and line not in evidence.KNOWN_PATHS for line in lines)
    elif result.query == 'web-server-processes':
        summary['process_references'] = [name for name in ('/usr/sbin/cped', 'uhttpd', '/opt/web/start.sh') if name in result.output]
        summary['meaning'] = 'process text references only; no command execution'
    elif result.query == 'web-listening-sockets':
        ports = set()
        for line in lines:
            columns = line.split()
            if len(columns) > 3 and columns[3] == '0A':
                match = re.fullmatch(r'[0-9A-Fa-f]+:([0-9A-Fa-f]{4})', columns[1])
                if match and int(match[1], 16) in (23, 53, 80, 443, 2323, 5547, 7547, 8080):
                    ports.add(int(match[1], 16))
        summary['observed_listening_ports'] = sorted(ports)
        summary['addresses'] = 'masked'
    elif result.query == 'web-opt-server-config':
        settings = {}
        for line in lines:
            match = re.search(r'(EnableHTTP|EnableHTTPS|httpport|httpsport|runmode)\s*=\s*(\S+)\s*$', line, re.IGNORECASE)
            if not match:
                continue
            key, value = match[1].lower(), match[2].lower()
            if key in ('enablehttp', 'enablehttps') and value in ('true', 'false'):
                settings[key] = value == 'true'
            elif key in ('httpport', 'httpsport') and value.isascii() and value.isdecimal() and 0 < int(value) <= 65535:
                settings[key] = int(value)
            elif key == 'runmode' and value in ('dev', 'prod', 'test'):
                settings[key] = value
        summary['settings'] = settings
        summary['meaning'] = 'static config; listening sockets and requests verify active service'
    elif result.query == 'web-opt-server-certificate':
        summary['public_certificate_present'] = bool(re.fullmatch(r'\s*-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]+-----END CERTIFICATE-----\s*', result.output))
        summary['certificate_values'] = 'omitted'
    elif result.query == 'web-http-client-capability':
        summary['wget_reference'] = bool(re.search(r'^/(?:usr/)?bin/wget$', result.output, re.MULTILINE))
        summary['advertised_flags'] = [flag for flag in ('-O', '-T', '-S', '--header') if flag in result.output]
        summary['meaning'] = 'capability help only; no HTTP request executed'
    elif result.query == 'web-status-name-index':
        found = []
        for line in lines:
            path, separator, candidate = line.rpartition(':')
            if separator and _source_path(path) and candidate in REVIEWED_OPERATION_NAMES:
                found.append({'source': path, 'candidate': candidate})
        summary['candidates'] = [dict(pair) for pair in sorted({tuple(item.items()) for item in found})]
        summary['unreported_line_count'] = sum(bool(line.strip()) for line in lines) - len(found)
    elif result.query == 'ip-addresses':
        interfaces = []
        current = None
        unreported = 0
        for line in lines:
            match = re.match(r'^\d+: ([^\s:@]+)(?:@[^:]+)?: <([^>]+)>', line)
            if match:
                flags = [flag for flag in match[2].split(',') if flag in ('UP', 'LOWER_UP', 'NO-CARRIER', 'BROADCAST', 'MULTICAST', 'LOOPBACK', 'POINTOPOINT')]
                current = {'interface': 'omitted', 'flags': flags, 'addresses': []}
                if _interface_name(match[1]):
                    current['interface'] = match[1]
                else:
                    unreported += 1
                interfaces.append(current)
                continue
            if re.match(r'^\d+:', line):
                current = None  # An unrecognized header cannot inherit addresses.
                unreported += 1
                continue
            address = re.match(r'\s+(inet6?) ([0-9a-fA-F:./]+) .*\bscope (host|link|global)\b', line)
            if address and current is not None:
                try:
                    parsed = ipaddress.ip_interface(address[2])
                except ValueError:
                    continue
                current['addresses'].append({'family': parsed.version, 'scope': address[3], 'prefix_length': parsed.network.prefixlen, 'address': 'masked'})
        summary['interfaces'] = [item for item in interfaces if item['interface'] != 'omitted' or item['addresses']]
        summary['unreported_interface_count'] = unreported
        summary['cellular_interface_binding'] = 'unverified'
    elif result.query in ('ip-routes', 'ipv6-routes'):
        defaults = []
        unreported = 0
        for line in lines:
            match = re.search(r'^default\b.*\bdev ([A-Za-z0-9_-]+)(?:\s|$)', line)
            if match and _interface_name(match[1]):
                defaults.append({'interface': match[1], 'gateway': 'masked'})
            elif line.startswith('default'):
                unreported += 1
        summary['ipv6_default_routes' if result.query == 'ipv6-routes' else 'ipv4_default_routes'] = defaults
        summary['unreported_default_route_count'] = unreported
        summary['cellular_interface_binding'] = 'unverified'
    elif result.query == 'usb-descriptors':
        devices = {}
        for line in lines:
            match = re.fullmatch(r'([0-9]{1,2}-[0-9.]{1,8}|usb[0-9]{1,2}) (idVendor|idProduct|manufacturer|product)=(.*)', line)
            if not match:
                continue
            bus, key, value = match.groups()
            record = devices.setdefault(bus, {})
            record[key + '_present'] = True
            if key in ('idVendor', 'idProduct') and re.fullmatch(r'[0-9a-fA-F]{4}', value):
                record[key] = value.lower()
            elif key == 'manufacturer' and value in ('Quectel', 'Quectel Wireless Solutions', 'Qualcomm', 'MediaTek', 'Linux Foundation'):
                record[key] = value
            elif key == 'product' and re.fullmatch(r'EG\d{2,3}[A-Z]?(?:-[A-Z]{1,6})?', value):
                record[key] = value
        summary['devices'] = devices
    elif result.query == 'web-capability-references':
        known = frozenset('iccid imsi msisdn plmn mcc mnc rsrp rsrq sinr rssi earfcn roaming registration quectel apn ipv4 ipv6 operator'.split())
        references = {}
        source_count = set()
        for line in lines:
            path, separator, term = line.rpartition(':')
            if separator and term.lower() in known:
                references[term.lower()] = references.get(term.lower(), 0) + 1
                source_count.add(path)
        summary['field_name_references'] = references
        summary['matching_source_count'] = len(source_count)
        summary['meaning'] = 'static source references, not observed cellular values or safe getter proof'
    elif result.query == 'resolver-state':
        families = []
        for line in lines:
            match = re.fullmatch(r'\s*nameserver\s+(\S+)\s*', line)
            if match:
                try:
                    families.append(ipaddress.ip_address(match[1]).version)
                except ValueError:
                    continue
        summary['nameserver_families'] = families
        summary['nameserver_addresses'] = 'masked'
        summary['cellular_dns_binding'] = 'unverified'
    elif result.query == 'configured-apn-presence':
        summary['source_read_succeeded'] = result.exit_code == 0
        summary['apn_declaration_count'] = sum(bool(re.match(r'\s*option\s+apn\s+', line)) for line in lines)
        summary['apn_values'] = 'omitted'
        summary['meaning'] = 'configuration declarations only, not active PDP/APN proof'
    elif result.query == 'usb-network-binding':
        bindings = []
        for line in lines:
            columns = line.split('|')
            if len(columns) != 3 or columns[2] not in ('', 'v4', 'v6', 'v4v6'):
                continue
            name, path, defaults = columns
            bus = re.findall(r'/([0-9]{1,2}-[0-9]{1,2}(?:\.[0-9]{1,2})*)(?:/|:)', path)
            if bus:
                bindings.append({'interface': name if _interface_name(name) else 'omitted', 'usb_device': bus[-1], 'ipv4_default': 'v4' in defaults, 'ipv6_default': 'v6' in defaults})
        summary['usb_network_interfaces'] = bindings
        summary['meaning'] = 'kernel topology/default-route correlation; not SIM or registration evidence'
    summary['other_values'] = 'omitted'
    return summary


def capture_raw(result: ProbeResult) -> None:
    """Explicit opt-in only; a fixed ignored directory, never an arbitrary path."""
    if RAW_IGNORE_RULE not in (PROJECT_ROOT / '.gitignore').read_text(encoding='utf-8').splitlines():
        raise ValueError('Private capture ignore rule is missing.') from None
    if RAW_DIRECTORY.resolve() != PROJECT_ROOT / 'artifacts' / 'd2-private':
        raise ValueError('Private capture directory is unsafe.') from None
    RAW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    target = RAW_DIRECTORY / (uuid.uuid4().hex + '.txt')
    with target.open('x', encoding='utf-8') as stream:
        stream.write(result.output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query', choices=tuple(QUERIES))
    parser.add_argument('--list-queries', action='store_true')
    parser.add_argument('--browser-script', action='store_true', help='Print the fixed offline-prepared browser probe; makes no connection.')
    parser.add_argument('--host', default=router.ROUTER_HOST)
    parser.add_argument('--port', type=int, default=router.ROUTER_PORT)
    parser.add_argument('--timeout', type=float, default=8.0)
    parser.add_argument('--capture-raw', action='store_true', help='Explicitly save sensitive raw output in the ignored private directory.')
    args = parser.parse_args(argv)
    if args.list_queries:
        print(json.dumps(QUERIES, indent=2))
        return 0
    if args.browser_script:
        if args.query is not None or args.capture_raw:
            parser.error('--browser-script cannot be combined with a query or capture')
        print(Path(__file__).with_name('d2_browser_probe.js').read_text(encoding='utf-8'), end='')
        return 0
    if args.query is None:
        parser.error('--query is required for hardware access')
    stop = threading.Event()
    previous = signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        result = run_query(args.query, host=args.host, port=args.port, timeout=args.timeout, stop_event=stop)
        router._check_cancelled(stop)
        if args.capture_raw:
            capture_raw(result)
        print(json.dumps(summarize(result), indent=2))
        return 0 if result.exit_code == 0 else 1
    except (router.RouterCancelledError, KeyboardInterrupt):
        stop.set()
        print('Discovery cancelled; connection closed.', file=sys.stderr)
        return 130
    except router.RouterError as error:
        print(f'Discovery failed: {type(error).__name__}. No raw response printed.', file=sys.stderr)
        return 1
    except (ValueError, OSError):
        print('Discovery failed: invalid options or local capture unavailable.', file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGINT, previous)


if __name__ == '__main__':
    raise SystemExit(main())

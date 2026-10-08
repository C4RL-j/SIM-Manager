"""Pure, privacy-filtered firmware source evidence for manual development probes.

This module does not run JavaScript, contact hardware, or establish that a request
is read-only. Only reviewed names and paths can leave these functions.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import PurePosixPath
import re

MAX_SOURCE_CHARS = 1024 * 1024
MAX_ITEMS = 128

REVIEWED_ASSETS = frozenset({
    '/opt/web/static/js/chunk-libs.4f4c4243.js',
    '/opt/web/static/js/app.5af0ce0f.js',
    '/opt/web/static/js/chunk-a65ab4a6.3cfa7746.js',
    '/opt/web/static/js/chunk-ff19fe88.a86a0aee.js',
    '/opt/web/static/js/chunk-elementUI.4ce7bdc2.js',
    '/opt/web/static/js/reload.min.js',
    '/opt/web/static/js/chunk-508c212a.59fd7df1.js',
    '/www/js/ajax.js', '/www/js/init.js', '/www/js/tri.js',
    '/www/js/t_utils.js', '/www/js/menu.js', '/www/js/project.js',
    '/www/js/project_menu.js', '/www/js/jquery.js', '/www/js/config.js',
    '/www/js/page.js',
})
KNOWN_PATHS = REVIEWED_ASSETS | frozenset({
    '/opt/web/views/index.html', '/opt/web/views/index.tpl',
    '/opt/web/start.sh', '/opt/web/conf/app.conf', '/opt/web/conf/app_https.conf',
    '/www/index.html', '/www/menu.shtml', '/www/page/hidden_noauth/index.html',
    '/www/page/status/status_dongle.shtml',
    '/www/page/status/status_info.shtml',
    '/www/page/status/status_wannetwork.shtml',
})
REQUEST_ENDPOINTS = frozenset({
    '/web/v1/dashboard/wirelessinfo',
    '/web/v1/dashboard/internetinfo',
    '/web/v1/dashboard/waninfo',
    '/web/v1/dashboard/deviceinfo',
    '/web/v1/status/wanstatus',
    '/web/v1/setting/network/pinmanagement/simcardinfo',
    '/web/v1/setting/deviceinfo',
})
TELEMETRY_FIELDS = frozenset({
    'rsrp', 'rsrq', 'sinr', 'rssi', 'earfcn', 'iccid', 'imsi', 'msisdn',
    'plmn', 'mcc', 'mnc', 'apn', 'pci', 'cellid', 'cell_id', 'band',
    'rat', 'roaming', 'registration', 'simstate', 'simstatus', 'pinstate',
    'operator', 'operatorname', 'networktype', 'ipv4', 'ipv6',
    'wirelessinfo', 'internetinfo', 'waninfo', 'deviceinfo', 'wanstatus',
    'simcardinfo',
    # Property names directly observed in the active firmware views. Their
    # literal/runtime values are never copied into this static summary.
    'rsrp0', 'rsrp1', 'uiccid', 'usimstatus', 'simcardstate', 'retriespin',
    'pincheckenabled', 'ecellid', 'connectstatus', 'connectmode',
    'connectionstatus', 'devicemodel', 'productmodel', 'hardwareversion',
    'softwareversion', 'routerversion', 'runningtime', 'ubootversion',
    'serialnumber', 'ipaddress', 'subnetmask', 'macaddress', 'imei',
})
TEMPLATE_DIRECTIVES = frozenset({
    'getobject', 'getobject_noop', 'endgetobject', 'getsingle', 'getuser',
    'leaf', 'path',
})
REFERENCE_TERMS = TELEMETRY_FIELDS | TEMPLATE_DIRECTIVES | frozenset({
    'cped', 'ubus', 'ajax', 'xmlhttprequest', 'wandongleinterfaceconfig',
})
MEANING = 'static source evidence; not runtime values or read-only proof'

# A small lexical filter, not a JavaScript parser. Whole comments and strings
# are recognized before punctuation, so their contents cannot supply properties.
_TOKEN = re.compile(
    r'(?P<comment>//[^\r\n]*|/\*[\s\S]*?\*/)'
    r'|(?P<string>"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')'
    r'|(?P<template>`(?:\\.|[^`\\])*`)'
    r'|(?P<identifier>[A-Za-z_$][A-Za-z0-9_$]*)'
    r'|(?P<space>\s+)|(?P<punctuation>.)',
    re.DOTALL,
)
_TEMPLATE = re.compile(r'<\?(.*?)\?>|<%(.*?)%>', re.DOTALL)


def _bounded(text: str) -> tuple[str, bool]:
    if not isinstance(text, str):
        raise ValueError('Source evidence requires text.') from None
    return text[:MAX_SOURCE_CHARS], len(text) > MAX_SOURCE_CHARS


def _tokens(text: str) -> list[tuple[str, str]]:
    tokens = []
    for match in _TOKEN.finditer(text):
        kind = match.lastgroup
        value = match[0]
        if kind in ('space', 'comment', 'template'):
            continue
        if kind == 'string':
            # Escaped/dynamic strings need a richer source investigation. Never
            # decode them opportunistically into endpoint or credential values.
            value = value[1:-1] if '\\' not in value else ''
        tokens.append((kind, value))
    return tokens


def _asset_path(value: str, source_path: str) -> str | None:
    if (
        not value or any(ord(ch) < 33 for ch in value)
        or any(ch in value for ch in ('?', '#', '\\', '%'))
        or value.startswith('//') or ':' in value
        or any(part in ('.', '..') for part in value.split('/'))
    ):
        return None
    if value in REVIEWED_ASSETS:
        return value
    if source_path not in KNOWN_PATHS:
        return None
    root = '/opt/web' if source_path.startswith('/opt/web/') else '/www'
    if value.startswith('/'):
        candidate = root + value
    elif root == '/opt/web' and value.startswith('static/'):
        candidate = root + '/' + value
    else:
        candidate = str(PurePosixPath(source_path).parent / value)
    return candidate if candidate in REVIEWED_ASSETS else None


class _Assets(HTMLParser):
    def __init__(self, source_path: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_path = source_path
        self.references: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attribute = 'src' if tag == 'script' else 'href' if tag == 'link' else None
        if attribute is None:
            return
        for name, value in attrs:
            if name == attribute and value is not None:
                path = _asset_path(value, self.source_path)
                if path is not None:
                    self.references.add(path)

    handle_startendtag = handle_starttag


def _properties(tokens: list[tuple[str, str]]) -> set[str]:
    fields = set()
    for index, (kind, value) in enumerate(tokens):
        name = value.lower()
        if kind not in ('identifier', 'string') or name not in TELEMETRY_FIELDS:
            continue
        before = tokens[index - 1][1] if index else ''
        after = tokens[index + 1][1] if index + 1 < len(tokens) else ''
        member = kind == 'identifier' and before == '.'
        key = after == ':' and before in ('{', ',')
        bracket = (
            kind == 'string' and before == '[' and after == ']'
            and index >= 2 and (
                tokens[index - 2][0] == 'identifier'
                or tokens[index - 2][1] in (']', ')')
            )
        )
        if member or key or bracket:
            fields.add(name)
    return fields


def _requests(tokens: list[tuple[str, str]]) -> list[dict[str, str]]:
    frames: list[dict[str, list[str | None]]] = []
    found = set()
    for index, (kind, value) in enumerate(tokens):
        if kind == 'punctuation' and value == '{':
            frames.append({'url': [], 'method': []})
        elif kind == 'punctuation' and value == '}':
            if not frames:
                continue
            frame = frames.pop()
            if len(frame['url']) == len(frame['method']) == 1:
                endpoint, raw_method = frame['url'][0], frame['method'][0]
                if endpoint is None or raw_method is None:
                    continue
                method = raw_method.upper()
                if endpoint in REQUEST_ENDPOINTS and method in ('GET', 'POST', 'DELETE'):
                    found.add((method, endpoint))
        elif (
            frames and kind in ('identifier', 'string')
            and value in ('url', 'method', 'type')
            and index > 0 and tokens[index - 1][1] in ('{', ',')
            and index + 2 < len(tokens) and tokens[index + 1][1] == ':'
        ):
            # Count every occurrence, including nonliteral duplicate keys. A
            # literal prefix followed by concatenation is not an exact URL.
            literal = None
            if (
                tokens[index + 2][0] == 'string' and index + 3 < len(tokens)
                and tokens[index + 3][1] in (',', '}')
            ):
                literal = tokens[index + 2][1]
            frames[-1]['url' if value == 'url' else 'method'].append(literal)
    return [
        {'method': method, 'endpoint': endpoint, 'status': 'candidate_only'}
        for method, endpoint in sorted(found)[:MAX_ITEMS]
    ]


def summarize_source(text: str, source_path: str) -> dict:
    """Return reviewed static names only; unknown literals/source are omitted."""
    bounded, truncated = _bounded(text)
    # HTMLParser ignores these, and the lexical/template passes must do so too.
    bounded = re.sub(r'<!--[\s\S]*?(?:-->|$)', '', bounded)
    path = source_path if isinstance(source_path, str) and source_path in KNOWN_PATHS else 'omitted'
    assets = _Assets(path)
    assets.feed(bounded)
    tokens = _tokens(bounded)
    for kind, value in tokens:
        if kind == 'string':
            asset = _asset_path(value, path)
            if asset is not None:
                assets.references.add(asset)
    directives = set()
    template_fields = set()
    comment_spans = [
        (match.start(), match.end()) for match in _TOKEN.finditer(bounded)
        if match.lastgroup == 'comment'
    ]
    comment_index = 0
    for block in _TEMPLATE.finditer(bounded):
        while comment_index < len(comment_spans) and comment_spans[comment_index][1] <= block.start():
            comment_index += 1
        if comment_index < len(comment_spans) and comment_spans[comment_index][0] <= block.start() < comment_spans[comment_index][1]:
            continue
        body = block[1] if block[1] is not None else block[2]
        head = re.match(r'\s*([A-Za-z_][A-Za-z0-9_]*)\b', body)
        if head is None or head[1].lower() not in TEMPLATE_DIRECTIVES:
            continue
        directives.add(head[1].lower())
        template_fields.update(
            word.lower() for word in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', body)
            if word.lower() in TELEMETRY_FIELDS
        )
    return {
        'source_path': path,
        'asset_references': sorted(assets.references)[:MAX_ITEMS],
        'telemetry_fields': sorted(_properties(tokens) | template_fields)[:MAX_ITEMS],
        'template_getters': sorted(directives)[:MAX_ITEMS],
        'template_field_names': sorted(template_fields)[:MAX_ITEMS],
        'endpoint_references': sorted({
            value for kind, value in tokens
            if kind == 'string' and value in REQUEST_ENDPOINTS
        })[:MAX_ITEMS],
        'request_candidates': _requests(tokens),
        'input_truncated': truncated,
        'meaning': MEANING,
        'other_values': 'omitted',
    }


def summarize_references(text: str) -> dict:
    """Summarize fixed grep path[:line]:term records, omitting unknown records."""
    bounded, truncated = _bounded(text)
    records = set()
    omitted = 0
    for line in bounded.splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'(/[^:\r\n]+):(?:(\d{1,7}):)?([A-Za-z][A-Za-z0-9_]*)', line)
        if match is None or match[1] not in KNOWN_PATHS or match[3].lower() not in REFERENCE_TERMS:
            omitted += 1
            continue
        number = int(match[2]) if match[2] is not None else None
        if number is not None and number <= 0:
            omitted += 1
            continue
        records.add((match[1], number, match[3].lower()))
    ordered = sorted(records, key=lambda item: (item[0], item[1] or 0, item[2]))
    references = []
    for path, number, term in ordered[:MAX_ITEMS]:
        record = {'source_path': path, 'term': term}
        if number is not None:
            record['line'] = number
        references.append(record)
    return {
        'references': references,
        'omitted_reference_count': omitted + max(0, len(ordered) - MAX_ITEMS),
        'input_truncated': truncated,
        'meaning': MEANING,
        'other_values': 'omitted',
    }

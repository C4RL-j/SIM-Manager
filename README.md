# SIM Manager

A lightweight Windows SIM management application in development. Tasks 001–004 are complete within their approved scopes: the Python package and D2 SMS transport have offline characterization and reliability coverage, and read-only hardware/firmware discovery has an evidence report and manual development probes. Seven firmware-evidenced telemetry GETs were verified through a sanitized report from the user's authenticated Brave session. Python 3.11 or newer is required. Task 005 has not begun.

## Current scope

The only device implementation is `sim_manager.devices.d2.router`, originally copied from the read-only legacy reference at `../old/D2-desktop/router.py`. It uses the existing Telnet/UBus inbox path. The default `192.168.1.1:2323` endpoint, three-record read, exact UBus command, and fixed historical marker remain unchanged.

The transport now preserves Telnet state across reads, recognizes a terminated standalone completion-marker line with command echo enabled or disabled, bounds raw received bytes, uses monotonic deadlines, supports cooperative cancellation, and emits generic errors without raw exception chains. Marker text inside command echoes or JSON strings cannot complete a read. Response processing stops at the marker line; trailing JSON or Telnet bytes in the same receive are ignored.

`fetch_sms_response` keeps its five existing positional parameters and adds keyword-only `stop_event` and `max_response_bytes`. An optional event with `is_set()` requests cancellation, reported as `RouterCancelledError`. The default byte limit is 1 MiB per read phase (banner, wake-up, command response), including Telnet control bytes. EOF or a reset raises `RouterDisconnectedError`, a subclass of `RouterConnectionError`.

SMS envelopes remain raw. Stringified or otherwise loosely shaped `data` is preserved, and the last successful outer envelope can still win over a later error envelope. Response selection prevents nested SMS objects from overriding valid or malformed outer envelopes. Transparent-wrapper fallback remains when no top-level envelope exists; traversal stops at any dictionary containing both `code` and `msg`, including error envelopes. The public JSON extraction helper still enumerates nested objects. Message normalization and stronger payload-schema validation are deferred.

The production package includes no GUI, carrier account integration, or SIM/signal/carrier detection. Importing it does not connect to a router. No runtime dependencies or browser packages are required. A separate manual development probe supports Task 003/004 discovery; it never runs at application startup.

```text
src/sim_manager/
├── __init__.py
└── devices/
    ├── __init__.py
    └── d2/
        ├── __init__.py
        └── router.py
tests/
├── test_d2_discovery.py
├── test_d2_discovery_sources.py
├── test_d2_source_evidence.py
├── test_d2_router.py
├── test_d2_router_reliability.py
├── test_d2_browser_probe.js          # separate Node development-probe tests
└── fixtures/d2/                     # sanitized observations/synthetic source
tools/
├── d2_discovery.py
├── d2_source_evidence.py
└── d2_browser_probe.js
```

## Offline verification

From this repository root in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -B -m unittest discover -s tests -v
```

The suite uses only the Python standard library, synthetic socket transcripts, and controlled clocks. Tests block real socket construction and replace the connection factory; they require no router, browser, package installation, or personal data. Characterization tests retain selected legacy behavior, and regression tests cover the deliberate Task 002 changes. Task 003 verification passed all 139 tests (78 transport and 61 discovery tests) with site packages disabled using `python -S -B -m unittest discover -s tests -v`. Passing offline tests does not establish compatibility with any router firmware.

The separate browser development probe has offline tests using Node's built-in test runner:

```powershell
node --test tests/test_d2_browser_probe.js
```

No npm packages are required. The Python standard-library suite remains independent of Node and browser packages; it does not execute these JavaScript tests.

Task 004 verification passed 190 Python tests and 36 Node tests, including the supplied sanitized authenticated-report fixture. The development source summaries were intentionally tightened to omit arbitrary dotted string values; production transport behavior and all 78 original transport tests remain unchanged.

## Transport assumptions

The supported path requires an already available direct Telnet shell and the existing `cped` UBus SMS command. Login prompts are rejected; the transport does not enable a shell, authenticate, or discover router/modem capabilities. Task 003 confirmed the default direct shell and standalone-line framing for read-only discovery queries. It did not read SMS, validate the historical SMS marker or payload forms on hardware, or test other firmware versions.

Balanced malformed JSON or shell noise can be skipped. An unclosed leading brace is treated as an incomplete outer object; the parser rejects that response rather than searching inside it for a nested success. Router output must therefore avoid unclosed brace-like shell noise before its response. Telnet option-refusal replies remain best effort: their socket errors are swallowed as in the legacy transport, while cancellation/deadline checks still bound processing.

Cancellation and deadlines use short socket polls (up to 0.5 seconds normally, 0.1 seconds with `stop_event`). Short cancellation polls preserve the legacy 0.5-second idle wait for banner/wake-up reads, capped by their respective 0.7/0.25-second phase deadlines. Connection setup uses a daemon worker and caller polls of at most 0.05 seconds. The caller can abandon a blocked connection attempt, and a late socket is closed. The OS DNS call itself cannot be interrupted; repeated abandoned DNS calls can temporarily accumulate daemon workers. No blocking worker join is required for shutdown.

Diagnostic logs and exception output must mask or omit full phone numbers/MSISDNs, IMSIs, ICCIDs, OTPs, sensitive SMS bodies, authentication cookies, tokens, and passwords. Returned SMS data is sensitive and must not be logged wholesale.

## Manual read-only discovery

From the repository root with `PYTHONPATH=src`, list the fixed reviewed queries without hardware access:

```powershell
python -S -B tools/d2_discovery.py --list-queries
```

An explicit `--query` invocation contacts the router. The development tool permits only reviewed read-only queries, uses bounded timeouts/output, and supports Ctrl+C. Normal output omits unknown values and sensitive identifiers. It does not change router settings, invoke guessed vendor/AT commands, or build production detection logic.

Task 004 inspected firmware/web assets first, then verified only getters evidenced by the router's own admin interface. Future status-page discovery may use an existing legitimate router session; passwords, cookies, and tokens must not be logged or stored in the repository. Configuration controls and requests with uncertain side effects remain out of scope. Any observed PLMN/operator values remain neutral evidence; carrier mapping and Task 005 are deferred.

For a legitimate signed-in Brave router tab, print the fixed browser probe offline:

```powershell
python -S -B tools/d2_discovery.py --browser-script
```

Manual execution in that tab's DevTools Console sends only seven firmware-evidenced same-origin GETs. The firmware uses `localStorage.Authorization` and an Authorization header with its credentials interceptor; the probe reuses that session inside the tab and never exports cookies/tokens. No browser-storage or router-setting writes are requested. It accepts only the local HTTPS router origins listed in the script, rejects redirects, enforces a 20-second total deadline and 256 KiB per-response limit, and can be stopped with `SIM_MANAGER_D2_PROBE.cancel()`.

Only a sanitized summary should be shared. Identifier/address/APN/cell values are masked; arbitrary operator/model/version text and unknown values are omitted. Narrow status enums, bands, signal values, and neutral PLMN digit strings may be retained without carrier interpretation. The user manually ran the probe inside the signed-in Brave tab because this environment had no browser connector or exposed remote-debugging port/pipe. All seven GETs returned HTTP/body code 200 with object data, without exporting authorization material.

The report verifies raw `Ready`/`READY`, `Connected`, and `LTE` labels, band string `1/28`, signal strings, and masked identifier field types. Masks hide even empty strings, so identifier contents/validity and cellular address assignment are unknown. Radio units, registration/roaming, actual operator/PLMN, APN/PDP, modem firmware revision, absent/PIN-locked SIM states, and other firmware variants remain unverified. `wirelessinfo` exported no allowlisted fields; that does not prove empty raw data. No production telemetry API or carrier mapping was added.

Raw responses are transient unless `--capture-raw` is explicitly requested. That flag saves sensitive data only under the ignored `artifacts/d2-private/` directory; never commit or paste those captures into documentation. It was not used for hardware in Tasks 003/004. See the [D2 hardware capability report](docs/devices/D2-HARDWARE-CAPABILITIES.md) for historical shell queries, firmware provenance, the authenticated GET ledger, and field statuses. Only GET/read operations were requested; firmware-internal side effects were not audited.

The `pyproject.toml` declares a setuptools build backend for future packaging. Building/installing the distribution requires that build tool; source imports and the offline test command above do not.

See [WORKFLOW.md](docs/WORKFLOW.md) for repository boundaries and verification, [AGENTS.md](AGENTS.md) for security/development rules, and the [active foundation plan](plans/active/000-foundation-reboot.md) for findings and deferred tasks.

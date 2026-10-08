# Development workflow

The repository root is `C:\PROJECTs\SIM-manager_workspace\sim-manager`. Run project commands there. Initialize Git only in this directory; never initialize Git at the workspace root or include `../old/D2-desktop/` in this repository.

The legacy tree is read-only reference material. Copy approved reusable code into `src/sim_manager/`; never import from the legacy tree at runtime. Compare before/after file lists and SHA-256 hashes when verifying that legacy files remain unchanged.

Read `AGENTS.md`, the relevant docs, and the active plan before changing code. Implement only the approved task. Tasks 001–004 completed the transport foundation and scoped read-only hardware/firmware telemetry discovery. Production detection, message normalization, carrier/account features, GUI work, and Task 005 remain deferred; discovery completion does not authorize that future implementation.

## Offline transport tests

Use Python 3.11 or later. The transport has no runtime dependencies, and its tests use only the standard library. No package installation, GUI/browser package, or router connection is needed:

```powershell
# Working directory: sim-manager
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -B -m unittest discover -s tests -v
```

The characterization/regression suite uses synthetic socket responses and controlled clocks. It must never open a live connection. `-B` prevents bytecode files during verification. Hardware probing and browser/account work are outside Task 002. Regression cases must distinguish intentional changes from preserved legacy behavior, including echo-disabled completion, Telnet fragmentation, bounded output, cancellation, disconnects, and sanitized errors. Keep coverage for trailing bytes after the completion line, malformed outer envelopes, and wrapper traversal that stops at response envelopes.

Task 002 verification passed 78 tests on Python 3.13.15 with site packages disabled using `python -S -B -m unittest discover -s tests -v`. Keep the 0.5-second idle wait for banner/wake-up reads within their 0.7/0.25-second phase deadlines; receive polls of up to 0.1 seconds when cancellation is enabled must not shorten that idle wait.

Task 003 verification passed 139 tests on the same interpreter with site packages disabled: the original 78 transport tests plus 61 discovery tests. The production transport and original tests were unchanged. Discovery tests cover the fixed query registry, fragmented framing, cancellation/deadlines/cleanup, privacy summaries, raw-capture confinement, and inert manual invocation.

Run the browser development probe's separate offline JavaScript tests with Node's built-in runner:

```powershell
node --test tests/test_d2_browser_probe.js
```

No npm dependencies or live router/browser are required. Python transport/discovery tests remain standard-library tests and do not depend on Node or run the JavaScript suite.

Task 004 verification passed 190 Python tests in 0.974 seconds and 36 Node tests in 693.5684 ms; `node --check tools/d2_browser_probe.js` also passed. Coverage includes the supplied sanitized authenticated-report fixture and explicitly synthetic hidden values. Two earlier development-summary expectations changed with an intentional privacy tightening and a new privacy regression; the original 78 transport tests and production package remain unchanged. The capability report records source provenance, initial unauthenticated checks, and seven successful authenticated GET observations from the signed-in Brave tab.

## Review and privacy

Run the relevant offline suite, review `git diff` and `git status`, and verify the legacy hashes before reporting completion. Include newly created files in the review; ordinary `git diff` does not show untracked file contents. Do not commit unless explicitly requested.

Diagnostic logs and exception output must mask or omit full phone numbers/MSISDNs, IMSIs, ICCIDs, OTPs, sensitive SMS bodies, authentication cookies, tokens, and passwords. Do not retain real messages, account data, or credentials in tests or fixtures.

## Task 003 hardware discovery

Use `tools/d2_discovery.py` only through explicit manual invocation. `--list-queries` is offline; `--query` contacts hardware using a fixed reviewed read-only command. Method/schema names alone do not establish safe execution. Find firmware/legacy evidence before adding or calling a vendor getter. Do not guess AT commands, read SMS merely for discovery, modify APN/PDP/network/band/SIM/configuration state, restart services, reconnect data, reboot, or install router software.

The default query deadline is 8 seconds, with a 256 KiB raw-wire cap per read phase and Ctrl+C cooperative cancellation. Normal output allows only reviewed metadata and omits unknown values; parse/error fallback must never dump raw text. Raw output requires the explicit `--capture-raw` flag and is confined to the ignored `artifacts/d2-private/` directory. Keep that directory untracked and do not use its contents as shared fixtures.

Record exact executed commands, their read-only basis, exit status, source/path, masked response shape, observed fields, units, and firmware assumptions in `docs/devices/D2-HARDWARE-CAPABILITIES.md`. Use VERIFIED, INFERRED, NOT FOUND, and UNTESTED per field. Missing evidence, failed access, and privacy-omitted values do not establish absent capabilities. Keep operator/PLMN evidence neutral and separate from later carrier interpretation.

Run all offline transport and discovery/parser tests, review diff/whitespace, verify unchanged legacy paths/hashes, and check that no raw captures are tracked. Document the actual manual hardware queries and confirm they contain no router setting changes.

## Task 004 cellular telemetry discovery

Inspect the router's firmware/web assets for actual request construction and response fields before invoking any candidate. Where practical, observe requests generated by status pages through an existing legitimate local admin session. Do not interact with configuration controls, store/log the router password, or expose cookies/tokens. Only extend the fixed discovery allowlist after evidence establishes a read operation; no arbitrary shell/UBus/CGI/RPC/AT interface is permitted.

For each candidate record source/page/path, exact request/method, read-only basis, authentication requirements, response shape, observed fields, state-change observation, and classification. A field name or getter-like name alone is insufficient. If safety is unresolved, leave the candidate untested and explicitly describe its safety as unverified. Never execute set/save/apply/update/modify/connect/disconnect/restart/reset/reboot/SMS-send/SMS-delete/APN/RAT/band/PIN operations or modem commands with unknown side effects.

Use only sanitized observed shapes for offline fixtures. Test missing/null fields, unexpected types, partial/malformed responses, observed firmware variations, and sensitive-value redaction without hardware. Keep runtime observations separate from inferred units/status semantics. PLMN/operator values remain neutral evidence; no carrier mapping or production detection is authorized. If no safe getter is found, document that limit without inventing a fallback.

If the legitimate session is available only in Brave, `python -S -B tools/d2_discovery.py --browser-script` prints the fixed `tools/d2_browser_probe.js` offline. Manual execution in the already signed-in local HTTPS admin tab sends only the seven evidenced GETs. The source-confirmed `localStorage.Authorization` value becomes an Authorization header inside that same origin; cookies/tokens are never exported, pasted into this environment, or written to files. Do not dump browser storage or attach raw network responses.

The browser probe accepts only its fixed local router origins, rejects redirects, requests no storage/configuration writes, and supports `SIM_MANAGER_D2_PROBE.cancel()`. Its total deadline is 20 seconds with a 256 KiB limit per response. Share only the sanitized report: identifiers, addresses, APN, and cell IDs masked; arbitrary operator/model/version/unknown strings omitted; narrowly allowed enums/bands/signals and neutral PLMN strings retained without interpretation. Source-confirmed field keys become runtime evidence only when actually observed.

Task 004's received report has seven HTTP/body-code-200 object responses and 49 typed fields. It verifies raw Ready/Connected/LTE labels, band/signal strings, and identifier field presence/types. Masks hide empty strings as well as populated ones; do not claim valid/non-empty identifiers or cellular addresses. PCI and PIN-retry values remain omitted strings. `wirelessinfo` exported no allowlisted fields, which does not prove empty raw data. Actual operator/PLMN, registration/roaming, APN/PDP, radio units, modem firmware revision, absent/locked SIM states, and other firmware variants remain unverified. Only two endpoints were separately checked unauthenticated and returned 401; the other five used the session without isolated authentication-requirement tests. GET-only `state_changes_requested=false` records requested operations, not an audit of firmware-internal side effects.

Run all existing offline tests plus new parser/discovery tests. Verify legacy hashes, unchanged production transport behavior, no router setting changes, no tracked sensitive captures, and passing diff/whitespace checks. Task 005 must remain unstarted.

Update the active plan with results and limitations. Keep the foundation plan under `plans/active/` while later foundation tasks remain outstanding; finishing Task 004 does not finish the whole plan.

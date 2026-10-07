# 000 — SIM Manager foundation reboot

Date: 2026-10-07

Status: Audit complete; Task 001 complete and verified; Task 002 and later not started

Scope: Historical repository audit, Task 001 package/transport baseline, and future migration plan

## Decision

Keep the existing Python D2 Telnet/UBus SMS transport as the migration starting point. Copy it into `sim-manager/` with offline characterization tests before changing its behavior. Build small device, carrier, service, storage, and UI boundaries around the code that is actually present. Do not transplant the legacy desktop controller or rewrite the router protocol to establish those boundaries.

`old/` remains read-only reference material. “Remove” below means exclude from the new application, never delete or edit the reference tree. The original audit created this plan only. The approved Task 001 adds a minimal package and offline transport characterization without repairing legacy imports, installing dependencies, contacting hardware, or implementing features.

The new application repository is `C:\PROJECTs\SIM-manager_workspace\sim-manager`. Git must be initialized inside `sim-manager/` only, never at the workspace root. `../old/D2-desktop/` must never be added to the new repository. Preserve the legacy tree and verify its file list and SHA-256 hashes before/after extraction.

Initial implementation targets D2 and DITO. Smart/TNT/Smart Bro must fit the same interfaces later, but Smart features are deferred to roadmap Phase 4. SMS sending was inspected for reuse; it is absent and is not a Phase 1 requirement in the current roadmap.

## Sources and audit boundaries

Read `sim-manager/AGENTS.md` and all six files under `sim-manager/docs/`: `PROJECT.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `WORKFLOW.md`, `carriers/DITO.md`, and `carriers/SMART.md`. At the original audit, `WORKFLOW.md` and `carriers/SMART.md` were empty and workflow rules came from `AGENTS.md`. Task 001 adds reproducible offline commands to `WORKFLOW.md` and the current package boundary to `ARCHITECTURE.md`.

Inspected the entire supplied file tree, all 20 legacy Python source modules, all 15 test modules, the README, three batch launchers, and PyInstaller specification. References such as `old/D2-desktop/router.py:210` use paths relative to the workspace root and line numbers from this snapshot.

Findings describe checked-in code, not live hardware or the current MyDITO website. The legacy README calls the router path working, but this audit did not verify a router connection, modem firmware, carrier session, DOM behavior, or packaged executable. Tests referencing missing modules describe intended behavior rather than supplied implementations.

## 1. Repository map at the original audit

```text
SIM-manager_workspace/
├── old/
│   └── D2-desktop/                 # 40 files; read-only reference
│       ├── app.py                  # delegates to desktop.main
│       ├── desktop.py              # pywebview/WebView2 controller, 1,981 lines
│       ├── home_dashboard.py       # HOME model, HTML/CSS/JS overlay
│       ├── router.py               # D2 Telnet/UBus inbox transport
│       ├── otp.py                  # DITO OTP extraction and timestamps
│       ├── dito_otp_helper.py       # standalone earlier router/OTP prototype
│       ├── legacy_app.py           # earlier Tkinter OTP GUI
│       ├── dashboard_inspector.py  # MyDITO DOM heuristics and reports
│       ├── account_snapshot.py     # models, parsers, extraction, formatting
│       ├── login_automation.py     # MyDITO phone entry and Continue automation
│       ├── mydito_focus.py         # MyDITO login/OTP focus and scrolling
│       ├── otp_page_detection.py   # OTP DOM detection and state machine
│       ├── otp_autofill.py          # single/segmented OTP entry
│       ├── otp_submit.py            # submission and authentication heuristics
│       ├── auth_number.py           # login state constants
│       ├── user_settings.py         # saved numbers and JSON persistence
│       ├── saved_number_dialog.py   # DITO-specific Tkinter modal dialog
│       ├── dashboard_formatting.py  # quantities, percentages, ages, expiry
│       ├── clipboard_privacy.py     # conditional cleanup predicate
│       ├── windows_clipboard.py     # Win32 Unicode clipboard operations
│       ├── tests/                   # 15 unittest files; 215 test methods
│       ├── README.txt
│       ├── DITO Desktop.spec
│       └── run_dito_*.bat           # three launchers
└── sim-manager/
    ├── AGENTS.md
    ├── docs/
    │   ├── PROJECT.md
    │   ├── ARCHITECTURE.md          # high-level layer diagram only
    │   ├── ROADMAP.md
    │   ├── WORKFLOW.md             # empty
    │   └── carriers/
    │       ├── DITO.md
    │       └── SMART.md            # empty
    ├── src/                        # empty at audit start
    └── plans/
        ├── active/                 # this plan added by the audit
        └── completed/              # empty
```

There was no root `AGENTS.md` or root `docs/`; the project instructions were under `sim-manager/`. No Git metadata, dependency manifest, lockfile, CI configuration, or reproducible installation instructions were supplied. At that time `git status --short` failed because the workspace was not a Git repository. `watcher.py` and `account_cache.py` were absent everywhere in the supplied tree despite imports and tests. This historical map and inventory are retained as audit evidence; the Task 001 additions are listed in section 7.

## 2. Capability inventory: existing code versus gaps

| Requested area | Supplied implementation and evidence | Reuse decision / missing work |
| --- | --- | --- |
| D2 router communication | `router.py:45` Telnet negotiation; `:87` banner reads; `:107` completion marker; `:140` UBus command; `:150` shell JSON extraction; `:210` socket orchestration; error types at `:25`. Defaults to `192.168.1.1:2323`. | Keep as the device transport seed. Expects a pre-existing direct shell; no discovery, model/firmware verification, HTTP client, or Telnet authentication implementation. |
| Quectel modem communication | No Quectel driver, AT transport, serial-port code, modem identification, or EG060-specific parser exists. | The documented EG060V-EAAA target is not an implemented capability. First investigate what D2 exposes through its existing `cped` service; introduce direct modem transport only if evidenced and necessary. |
| SIM detection | No physical SIM state, PIN state, ICCID/IMSI, or installed-SIM identification query exists. | Build from verified device responses later. Saved phone numbers and a DITO SMS sender do not detect the inserted SIM. |
| Carrier detection | No device-backed carrier recognition exists. | Build normalized carrier recognition from reliable device/SIM evidence. Phone-number format, router branding, SMS sender, and a MyDITO account session are insufficient proof. |
| Network information | No registration, operator, roaming, RAT, band, cell, or network query exists. | New device capability after discovery; represent unavailable fields explicitly. |
| Signal information | No RSSI, RSRP, RSRQ, SINR, or signal-strength query exists. Search hits for “signal” are browser heuristics, not modem measurements. | New device capability with verified units, missing-value semantics, and fixtures. |
| SMS reading | `router.py:140` issues `sms.get.inboxdata` using `StartPos:0` and default `ReadNum:3`; `:196` selects a success envelope. | Keep wire command and parsing knowledge. Full inbox paging, normalized messages, and robust payload validation are missing. Newest-first ordering is assumed rather than established. |
| SMS sending | No send command, recipient/body encoding, delivery state, or send UI exists. No delete or explicit mark-read operation either. | Build only in a later scoped task after command/encoding discovery. Do not invent UBus or AT commands. |
| OTP detection | `otp.py:14` `OTPInfo`; `:55` timestamp parsing; `:77` `find_latest_dito_otp`; tests in `test_otp.py`. | Keep metadata/freshness concepts. Move the DITO sender/exact English phrase rule into the DITO adapter; normalize device SMS separately. |
| OTP watching | Desktop/Tkinter code imports `watcher`; `tests/test_watcher.py` expects injected fetchers, freshness, new-message identity, timeout, and error handling. Callers pass `stop_event` for cancellation, which those watcher tests do not cover. | Implementation is missing. Recover from an authoritative source if available; otherwise implement a service later using reviewed tests as specifications, adding cancellation coverage. |
| Account information | `account_snapshot.py:169` interprets MyDITO DOM reports for main data, buckets, calls, and expiry. | Reuse parsers behind DITO. Load balance, remaining texts, and rewards are always `None` at `:215`; there is no complete normalized active-promo API. |
| UI | WebView2 shell, HOME allowance cards, number picker, status/age badges, progress bars, expiry warnings, native hotkeys, and Tkinter dialogs. | Reuse selected widgets/styles/model ideas. Current UI is DITO-specific and shares the remote carrier DOM. Build the neutral application shell separately. |
| Configuration/storage | `user_settings.py` provides versioned JSON, local app-data paths, validation, saved-number operations, and atomic replacement. Desktop configures a persistent WebView2 profile. | Reuse mechanisms after schema/identity fixes. Router endpoint configuration, safe account-scoped caching, explicit logout, and session isolation are absent. `account_cache.py` is missing. |

## 3. File disposition

| Keep or refactor | Destination / reason |
| --- | --- |
| `router.py` | Copy into the new D2 device package first. Preserve command construction, timing, echo-marker workaround, and public error semantics until characterized. No DITO dependency is needed for inbox transport. |
| `otp.py` | Split D2 payload decoding from carrier matching. Retain metadata and timestamp utilities with explicit clock policy; place DITO matching in `carriers/dito/`. |
| `user_settings.py` | Retain JSON validation and atomic writes. Extract generic Philippine phone normalization/masking; keep MyDITO login-number conversion inside DITO. Replace dual saved-number/SIM schema before import. |
| `account_snapshot.py` | Separate neutral result models from MyDITO row heuristics and browser polling. Preserve unknown/partial/error distinctions; add account binding and provenance before caching. |
| `dashboard_formatting.py` | Reuse small pure formatting helpers after correcting unit/time assumptions. Move carrier-specific interpretation out of shared presentation. |
| `clipboard_privacy.py`, `windows_clipboard.py` | Keep as optional Windows platform utilities; fix conditional-clear race before using cleanup in the new app. |
| `home_dashboard.py` | Reuse allowance cards, status/age/expiry presentation and view-model ideas against normalized service results. Replace injection into the remote document and DITO labels/mailboxes. |
| `desktop.py` | Extract limited platform/browser setup (`NativeHotkey`, app-data path, TLS/debug settings). Replace the monolithic orchestration with small services and a thin UI controller. |
| `dashboard_inspector.py`, `login_automation.py`, `mydito_focus.py`, `otp_page_detection.py`, `otp_autofill.py`, `otp_submit.py`, `auth_number.py` | Keep as Phase 2 DITO reference and selective reuse candidates. They belong behind the DITO integration/session boundary. Their heuristics are not a validated current carrier API. |
| `saved_number_dialog.py` | Retain validated user-intent/result patterns if useful. Adapt copy and event-loop integration only when settings UI is implemented. |
| Existing tests | Migrate relevant behavior tests with the code they protect. Decouple pure tests from desktop/cache imports; distinguish normalizer tests and script-string assertions from actual browser integration tests. |

Exclude `dito_otp_helper.py`, `legacy_app.py`, old `app.py`, old batch launchers, and the unchanged `DITO Desktop.spec` from the new runtime. They duplicate flows, target old branding/entry points, or assume unmanaged Python on PATH. Keep their files as reference. Use the packaging recipe only as later build guidance. Do not copy raw-output debugging, automatic clipboard copy from the standalone helper, a global legacy account cache, or DITO-specific HOME/MYDITO navigation into the new generic UI.

## 4. Technical debt and risky assumptions

### Resolve before presenting a reliable migrated device path

1. **Incomplete legacy runtime.** `desktop.py:13`, `:16`, `:28` imports `webview`, missing `account_cache`, and missing `watcher`. Installing pywebview alone cannot restore this snapshot. Do not use fake replacement modules to claim the legacy suite or application works.
2. **Direct-shell dependency.** `router.py:210` assumes a reachable unencrypted Telnet shell on port 2323 and rejects a login prompt. A TCP connection does not establish D2 model identity or modem/SIM health. Treat shell availability as a supported configuration requirement; do not enable shells, alter firmware, bypass authentication, or guess credentials as part of migration.
3. **Fragmented Telnet negotiation.** `handle_telnet_bytes` at `router.py:45` has no state between receives. A split IAC/option sequence is lost; subnegotiation is not fully handled. An offline fake-socket probe confirmed split negotiation bytes can leak into payload. Add characterization and regression cases before a narrow stateful-parser fix.
4. **Echo/marker and timeout assumptions.** `router.py:107` requires two occurrences of a static marker because the shell echoes commands. Echo-disabled shells can time out after a successful command; disconnects can be reported as timeouts. Reads use wall-clock deadlines and repeatedly rescan unbounded accumulated output. Characterize echo, split markers, disconnects, truncation, and timeout boundaries; then introduce monotonic deadlines, bounded output, and explicit completion/error handling where justified.
5. **Input and response validation.** `build_sms_command` at `router.py:140` interpolates `read_num` and `marker`; future configurable inputs require validation and safe quoting. `get_sms_response` at `:196` validates only `code`, `msg`, and presence of `data`, not its shape. `otp.py:100` calls `.strip()` on unchecked body/sender values. Malformed data must produce sanitized typed failures rather than crash polling. Do not expose a generic arbitrary-shell-command API.
6. **Limited inbox window and OTP clock policy.** The first match in three records is called “latest” without sorting (`otp.py:77`). Freshness uses a fixed 150-second threshold and naive host-local time (`:10`, `:25`). Router/SMS time zone, clock skew, missing dates, ID reuse, SIM changes, and actual OTP expiration are unverified. Keep expiry policy configurable within the service/carrier boundary and define behavior for unknown times.

### Resolve before account/UI/storage migration

7. **False availability.** `desktop.py:229` passes `router_status="Available"` without probing. The new UI must reflect a real device result and distinguish disconnected, unavailable, unsupported, and unknown states.
8. **Remote DOM is also the application surface.** `home_dashboard.py:261` embeds the local model, including full saved numbers from `desktop.py:244`, into JavaScript; `home_dashboard.py:486` appends the app shell to the carrier document. Remote-page scripts can read those entries and change the `window.__ditoDesktop*` request flags (`:106`). Keep app UI/data on a local app-owned surface and the carrier browser session on a separate trusted surface. Preserve `js_api=None` for remote content (`desktop.py:1960`).
9. **Missing origin checks and DOM ambiguity.** Browser automation operates on the active document without an official-origin allowlist. OTP field selection uses first-match/first-six heuristics; `otp_autofill.py:412` can retain an earlier success after verification reports failure. Before Phase 2 reuse, enforce trusted origin/navigation state, unique intended fields, verification, and cancellation on navigation/account changes. Keep manual authentication as a functional fallback; never automate around CAPTCHA/security challenges.
10. **Possible detection feedback.** `dashboard_inspector.py:141` scans global visible document elements without excluding the injected app overlay. Its dashboard evidence at `:170` may therefore include locally rendered cached account text. This is a static risk, not a reproduced live failure. Isolating the UI prevents this feedback; browser fixtures must ensure app-created text cannot establish authentication or fresh account data.
11. **Session persistence is not session lifecycle.** `desktop.py:1855` and `:1970` provide a persistent local WebView2 profile. There is no established logout/invalidation implementation, account-separated profile design, or verified session lifetime. A cached snapshot with `authenticated=True` must never establish a current logged-in state. Use legitimate user-authenticated carrier sessions; keep browser-managed credentials outside JSON settings and the repository.
12. **Saved account entries are not detected SIMs.** `UserSettings.remembered_number` returns the first saved entry even if `active_sim_id` selects another (`user_settings.py:48`). Stored `sims` and `saved_numbers` duplicate truth (`:202`); deletion preserves nondefault SIM entries (`:435`) and reload can reconstruct deleted numbers (`:249`). “Remember off” preserves serialized numbers (`:409`). Define selection, disable-remember, forget, and delete separately; use one canonical schema. Do not silently import old settings or overwrite the old app-data directory.
13. **Account/cache identity is absent.** `AccountSnapshot` at `account_snapshot.py:68` has no carrier/account/SIM binding, and the controller uses one default cache path (`desktop.py:161`). A chosen MyDITO account may differ from the SIM in the router. Bind future cached account data to its actual carrier account/profile; keep device SIM identity separate. On SIM/account change, cancel obsolete work and invalidate the relevant view. Do not attach old global balances to a newly detected SIM.
14. **Incomplete and potentially overlapping allowances.** `account_snapshot.py:201` requires main data, buckets, and calls for success; valid data-only accounts can remain partial. Main-data matching recognizes all/open-access labels (`:276`) while bucket exclusion only recognizes mobile-data labels (`:290`), risking overlapping displays. Load/text fields are unimplemented. Preserve carrier categories and unknowns; do not sum overlapping buckets or fabricate zero balances/promos.
15. **Time/unit semantics.** `account_snapshot.py:82` produces naive English-display expiry dates while capture times are aware UTC; `dashboard_formatting.py:99` strips or attaches timezone information during comparisons. Data parsing permits arbitrary alphabetic units, and formatting assumes MB/GB with a 1024 conversion (`dashboard_formatting.py:10`). Establish observed carrier units and time zone before computing percentages, expiry, or totals; preserve source display strings where interpretation is uncertain.
16. **Concurrency, repeated rendering, and clipboard ownership.** `DesktopController` has multiple threads, shared mutable authentication state, and browser locks; shutdown joins have shorter limits than possible router operations (`desktop.py:1813`). Its polling loop rerenders the overlay every 0.75 seconds (`desktop.py:436`), rebuilding contents (`home_dashboard.py:527`) even without data changes. Extract bounded, cancellable service operations, serialize browser work, and render on relevant state changes; prevent results from prior SIM/account/navigation generations updating a new view. Clipboard cleanup reads and clears in separate opens (`windows_clipboard.py:128`), so a user clipboard update can be erased between them. Compare/clear under one clipboard lock before reuse.
17. **Documentation/build/coverage gaps.** README describes older phases and says account data is not cached, while `desktop.py:1535` calls cache saving. No direct checked-in router transport tests or hardware fixtures exist. Most browser tests normalize results or inspect script strings without executing JavaScript against a real DOM. No reproducible dependency/build setup exists. Preserve useful tests while documenting their limits; avoid another broad browser-helper framework while core behavior is still uncertain.

## 5. Comparison with `docs/ARCHITECTURE.md`

The documented stack is UI → Services → Carrier abstraction (DITO/Smart) → Device abstraction (D2/Quectel), with information flowing upward. `AGENTS.md` clarifies that device behavior must not leak into carrier adapters, carrier behavior must not leak into UI, and the UI consumes normalized operations such as `get_carrier()`, `get_signal()`, `get_messages()`, `get_data_balance()`, `get_load_balance()`, and `get_active_promos()`.

| Intended boundary | Current structure | Migration alignment |
| --- | --- | --- |
| Device | `router.py` is already largely carrier-independent, but only exposes raw SMS envelopes. The older helper duplicates it. | Keep one D2 implementation; own Telnet, UBus, device payload parsing, and hardware capability errors here. |
| Carrier | DITO behavior is spread across OTP parsing, settings, browser scripts, account extraction, controller, and UI. No carrier abstraction exists. | Place DITO OTP/content/account interpretation and official-site integration behind one adapter boundary consuming normalized device/service inputs. |
| Services | Polling, login sequencing, cancellation, cache updates, clipboard actions, and view changes live in `DesktopController`; watcher/cache implementations are missing. | Extract small orchestration services with injected device/carrier dependencies and clear state/results. |
| UI | Desktop and HOME directly know MyDITO DOM, account parser/cache types, saved identities, and automatic login actions. UI is injected into the carrier page. | Build local Overview/Data/Messages/Settings views consuming service results. Labels and available actions follow adapter capabilities. |
| Storage/shared models | Versioned settings exist, but identifiers, sources, timestamps, and schema ownership are inconsistent. | Keep storage independent of browser/carrier parsing; share small neutral result types with provenance and explicit unknowns. |

The architecture document specifies no package layout or detailed call graph. The proposed layout below implements its boundaries without changing the architecture in this task. Clarify during foundation implementation that generic device reads (signal/SMS/network) can be orchestrated by services without adding carrier-specific wrappers; carrier adapters consume normalized messages when their own rules require them. Carrier account results remain separate from router information and locally measured usage.

## 6. Proposed target layout — future implementation only

```text
sim-manager/
├── pyproject.toml                  # Python package, dependencies, tooling
├── src/sim_manager/
│   ├── __init__.py
│   ├── main.py                     # composition/startup only
│   ├── models.py                   # small normalized results and statuses
│   ├── config.py                   # endpoint and polling configuration
│   ├── devices/
│   │   ├── base.py                 # minimal contract actually needed
│   │   └── d2/
│   │       ├── router.py           # first copy of legacy transport
│   │       └── sms.py              # verified envelope/message normalization
│   ├── carriers/
│   │   ├── base.py                 # carrier identity/capability contract
│   │   └── dito/
│   │       ├── adapter.py
│   │       ├── otp.py
│   │       └── mydito/             # browser/account integration, Phase 2
│   ├── services/                   # device refresh, messages, OTP, accounts
│   ├── storage/                    # settings; account cache when needed
│   ├── platform/                   # optional Win32 clipboard/hotkeys
│   └── ui/                         # local, carrier-independent presentation
├── tests/                          # focused unit/contract/browser tests
├── docs/
└── plans/
```

Create folders/modules only when their task needs them. No separate Quectel driver, Smart implementation, plugin registry, event bus, database, or new UI framework is justified by this audit. Retaining Python and selectively reusing pywebview/WebView2 avoids a technology rewrite; the eventual browser dependency can be loaded for authenticated account work rather than device-only startup. Evaluate startup/memory/package size when that integration is runnable, without assuming another framework is lighter.

Normalized results should carry explicit status, observation time, units where applicable, and source (`device`, `carrier`, or `local_measurement`). Account results also need account/profile binding and freshness; cache origin is a presentation/storage state, not proof of authentication. Unknown/unsupported/failed values must stay distinct from valid zero values. Choose small typed records and only the contracts needed by the first implementation, rather than designing every future feature upfront.

Approved requirements for later tasks, not implemented in Task 001:

- Shared OTP watcher services consume a carrier-provided matcher/predicate. They must not import DITO OTP logic directly.
- Carrier detection uses cellular/SIM/operator information, not router branding. A Smart-branded D2 does not establish that the inserted SIM uses Smart.
- Normalized allowance models support data-only products and non-expiring products; calls/text allowances and expiry must not be mandatory evidence of a valid account result.
- Future transport hardening supports cooperative cancellation and monotonic deadlines.

Diagnostic logs and exception output must mask or omit full phone numbers/MSISDNs, IMSIs, ICCIDs, OTPs, SMS bodies containing sensitive information, authentication cookies, tokens, and passwords. Tests and fixtures use synthetic values. This documentation rule does not authorize wire-protocol changes during the Task 001 extraction.

## 7. Safest staged migration

### Task 001 — package scaffold and preserve the D2 SMS transport

**Complete and verified.** Affected layers: device, minimal project configuration, documentation, and tests. The minimal Python package and offline characterization suite are in place. `old/D2-desktop/router.py` was copied byte-for-byte into `src/sim_manager/devices/d2/router.py`, preserving its existing call signature/defaults, UBus command, socket pacing, marker workaround, exception classes, and response-selection behavior. The old source remains untouched and is never imported at runtime by the new package.

Task 001 creates only the `sim_manager`, `devices`, and `devices/d2` package namespaces, the preserved `devices/d2/router.py`, a standard-library offline test suite, and minimal project metadata/documentation. `pyproject.toml` uses setuptools, requires Python 3.11 or later, and declares no runtime dependencies. `README.md` and `.gitignore` support using this baseline; there is no application entry point, GUI/browser dependency, carrier/account implementation, SIM/signal detection, or hardware probing.

Acceptance criteria:

- Package imports and test discovery work independently of `old/`, MyDITO, missing watcher/cache modules, and a browser dependency.
- Synthetic fake-socket transcripts cover the exact inbox command, Telnet refusals/escaped IAC, echoed command plus final marker, fragmented payload/marker, nested/stringified JSON with escaped braces, empty/malformed response, login prompt, refusal, connect/response timeout, and early disconnect.
- Known weaknesses are documented explicitly; do not bless broken negotiation or unvalidated payload behavior as desired permanent contracts. Add regressions with the focused fixes in Task 002 rather than silently changing extraction semantics.
- Tests exercise the whole fetch/error path with injected or mocked sockets and clock; they do not contact hardware or record real SMS, OTPs, SIM identifiers, credentials, or raw account data.
- Review the new files against the legacy copy. No feature UI, carrier login, Smart code, modem commands, or broad abstractions enter this task.

Run from `sim-manager/` without installation:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -B -m unittest discover -s tests -v
```

Final test results, legacy-copy comparison, hash verification, diff review, and Git status are recorded after verification in section 8. Task 002 has not begun.

### Task 002 — narrowly harden transport and normalize messages

Fix characterized fragmentation/validation/deadline/buffer issues in the new copy only, with explicit regression tests and documented interface decisions. Keep the working UBus protocol. Add cooperative cancellation and monotonic deadlines when hardening transport. Add validated endpoint configuration and normalize message records/IDs/timestamps without applying DITO rules. Distinguish no messages, malformed payload, unavailable shell, and transport failure. Validate full-inbox ordering/paging before claiming a complete inbox; preserve the three-record OTP read option.

Check available authoritative sources for the missing watcher/cache modules before rebuilding their behavior. If recovered, audit them under the same rules; if unavailable, mark them as new implementations. Neither is required to validate the extracted transport.

### Task 003 — establish device capabilities with evidence

Use targeted read-only inspection on a supported D2 setup to identify model/firmware/modem, SIM state, network registration/operator/RAT, and signal commands available through the router. Record documented/observed behavior in sanitized fixtures and device docs. Never guess Quectel AT commands or hidden endpoints from the modem name. Implement each verified read behind the device contract; unsupported capabilities fail gracefully. Keep router reachability, SIM readiness, and network registration distinct. Carrier detection must use cellular/SIM/operator information rather than router branding.

### Task 004 — DITO core services

Add DITO recognition from verified device evidence and a carrier adapter with explicit unknown/unsupported states. Move the existing DITO OTP rule into that adapter over normalized messages. Shared OTP watcher services must accept a carrier-provided matcher/predicate rather than importing DITO OTP logic directly. Recover or implement the missing polling service with injected clock/fetcher, baseline/new-message handling, freshness, bounded retry, cancellation, and SIM-change reset. Port reviewed OTP/watcher tests and add missing ordering/malformed/time-zone cases. No MyDITO automation or Smart account features are needed for Phase 1.

### Task 005 — local storage and minimal neutral UI

Reuse atomic settings persistence with a single canonical saved-account schema and `%LOCALAPPDATA%/SIM Manager` paths. Preserve old app-data files; any future import must be explicit, validate input, resolve deletion/selection semantics, and never carry over authentication material or an unbound global account cache. Keep detected SIM identity separate from user-entered account numbers.

Build a local shell and the smallest device/messages/status presentation needed to exercise DITO core. Reuse useful cards/formatters but remove hardcoded availability and MyDITO-specific presentation decisions. The UI routes I/O through services; device, carrier, and storage adapters own their respective I/O. Device/status errors must leave the application usable. Complete the Data/Overview/Messages/Settings experience according to roadmap Phase 3; a minimal earlier shell is only for validating the Phase 1 path.

### Task 006 — authenticated MyDITO adapter and account views

Proceed with roadmap Phase 2 after the device/services path works. Reuse selected existing browser scripts and account parsers inside the DITO integration. Use an official user-authenticated browser surface isolated from local app data, with trusted-origin checks, manual fallback, and no security bypass. Investigate actual session lifetime, endpoints/DOM behavior, and challenges rather than treating legacy guesses as facts.

Implement session persistence, logout, expiration recovery, refresh, and verified account fields incrementally. First fix time/unit interpretation and partial-account success rules; add source/account binding before implementing cache storage. Normalized allowance models must support data-only and non-expiring products without requiring calls, texts, or expiry. Use browser-executed sanitized fixtures for ambiguous inputs, navigation, overlay exclusion, rejected/expired OTPs, and account switching. Preserve last known values as visibly cached/stale; never display local usage as an official carrier balance. Keep optional OTP autofill/submission out until its verification and session binding are established.

### Later tasks

Add the Smart adapter and Smart/TNT/Smart Bro recognition in Phase 4 using the same normalized contracts. Introduce outbound SMS only after verified device-command/encoding discovery and an explicit feature task. Multi-SIM profiles, local usage history, notifications, broader hardware support, and packaging polish follow the roadmap. Rebuild launch/build commands for SIM Manager with declared dependencies and verify WebView2 runtime handling when browser integration is included.

## 8. Verification record and implementation gates

### Historical audit baseline

Audit baseline on Python 3.13.15:

```powershell
# Working directory: old/D2-desktop; -B prevents bytecode writes.
python -B -m unittest discover -s tests -v
```

Result: **75 tests passed; six test modules failed to import**. Unittest reports 81 entries because each failed module contributes one error entry. Static inspection counts 215 test methods; the whole legacy suite did not execute. Import errors affect `test_account_cache`, `test_desktop_autofill`, `test_desktop_helpers`, `test_home_dashboard`, `test_login_automation`, and `test_watcher`. Causes are absent local modules `account_cache`/`watcher` and unavailable external `webview` in this environment. All 35 supplied Python files parse successfully. No dependencies were installed and no browser/router was launched.

An additional isolated `test_otp.py` run passed 6/6. Offline probes confirmed split-Telnet-negotiation loss, acceptance of malformed envelope `data`, and failure on nonstring SMS content. These are audit observations, not new checked-in tests or evidence of live-device compatibility.

For each later implementation task: run the focused tests and package/import/start checks appropriate to its scope, verify graceful error behavior, inspect the change against this plan, and update relevant docs. Use opt-in hardware checks after offline tests; record the tested D2 firmware/configuration without retaining personal data. Keep browser/account tests independent from device tests. Update `ARCHITECTURE.md` with actual boundaries and `WORKFLOW.md` with reproducible commands once established. Move this plan to `plans/completed/` only after its foundation implementation scope is fulfilled; this audit does not mark the roadmap foundation phase complete.

File-integrity verification for the original audit used before/after SHA-256 hashes and tree comparison because Git metadata was absent. Result: this plan was the only added file; all 47 pre-existing files, including all 40 legacy files and the existing project instructions/docs, remained unchanged. No bytecode artifacts were created.

### Task 001 verification

Verified on Python 3.13.15:

- `python -B -m unittest discover -s tests -v`: **30 tests passed**.
- `python -S -B -m unittest discover -s tests -v`: **30 tests passed**, with site packages disabled. Both runs use `PYTHONPATH=src` from the new repository root; they neither import nor execute legacy files.
- Package imports also succeed with site packages disabled. Project metadata declares zero runtime dependencies; building a distribution uses the declared setuptools backend, which was not installed or exercised in this task.
- Tests block real socket construction and require fake connections. Synthetic transcripts cover default/custom connection arguments, the 0.7/0.25-second read windows and 0.5-second socket timeout, Telnet refusals/escaped IAC, exact UBus quoting/CRLF, command echo and second-marker completion, fragmented payload/markers, JSON amid shell noise, nested/stringified JSON, retries/timeouts, login prompts, disconnects, malformed/error envelopes, and socket cleanup.
- The port and legacy `router.py` have identical SHA-256 hashes (`4050F88425B155E25C8D233CF3C1AD5A019A06F4BC0EF6DF1CCDCDB16BA1A56E`); no protocol, public interface, or exception changes were introduced.
- All 40 legacy files retain their original paths and SHA-256 hashes. Git is initialized only inside `sim-manager/`; no Git directory was created at the workspace root and the legacy tree is outside the repository.
- Git diff review includes new files through a temporary index; the normal index remains unstaged. No commits were created. The initial repository status lists the project files as untracked.

Observed legacy behavior differs from likely future expectations in the following ways, preserved intentionally for this baseline:

- Telnet negotiation split across receives loses state and can leak option bytes into decoded output; failed negotiation replies are swallowed.
- Completion requires two occurrences of the fixed marker. A successful echo-disabled response with one marker is reported as a timeout.
- EOF before completion is reported as a response timeout; receive-side `OSError` is reported as a connection error with its cause retained.
- Success envelopes validate only code/message/data presence. `data` need not be a valid SMS payload, and extraction enumerates nested objects; a nested success envelope can override its outer response. The last successful candidate can also be selected ahead of a later error envelope.
- Raw `OSError` text and exception chaining are unchanged. Future diagnostic callers must mask or omit sensitive content rather than blindly print exceptions or their causes.

These are characterization observations, not fixes or approved permanent contracts. No live-router, hardware, modem, browser, or account verification was performed. The four future requirements above remain documentation only; Task 002 and later have not begun. This foundation plan remains active for its outstanding tasks.

## 9. Requested outcome summary

- **Keep:** D2 Telnet/UBus inbox protocol and error vocabulary, tested OTP/parser behavior, atomic JSON persistence, pure formatting/masking utilities, selected Windows helpers and UI presentation ideas.
- **Refactor:** device SMS normalization, DITO OTP/content rules, MyDITO browser/account code, saved-account schema and cache identity, time/unit handling, controller orchestration, and carrier-specific UI coupling.
- **Remove from the new runtime:** duplicate helper/Tkinter application flows, raw sensitive debugging, remote-page application overlay/mailboxes, hardcoded router availability, global unbound account cache assumptions, and old branding/launch/build entry points. Preserve `old/` intact.
- **Build new:** minimal package/test/dependency setup, verified SIM/network/signal/device-capability queries, carrier/service contracts, missing polling/cache implementations if unrecoverable, neutral local UI, account-bound session/cache lifecycle, and later Smart support/outbound SMS.
- **Completed first step:** Task 001, minimal package scaffold plus a behavior-preserving D2 SMS transport extraction with offline characterization tests. Task 002 requires a separate implementation request.

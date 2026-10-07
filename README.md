# SIM Manager

A lightweight Windows SIM management application in development. Tasks 001 and 002 are complete: the Python package and D2 SMS transport have offline characterization and reliability coverage. Python 3.11 or newer is required. Task 003 has not begun.

## Current scope

The only device implementation is `sim_manager.devices.d2.router`, originally copied from the read-only legacy reference at `../old/D2-desktop/router.py`. It uses the existing Telnet/UBus inbox path. The default `192.168.1.1:2323` endpoint, three-record read, exact UBus command, and fixed historical marker remain unchanged.

The transport now preserves Telnet state across reads, recognizes a terminated standalone completion-marker line with command echo enabled or disabled, bounds raw received bytes, uses monotonic deadlines, supports cooperative cancellation, and emits generic errors without raw exception chains. Marker text inside command echoes or JSON strings cannot complete a read. Response processing stops at the marker line; trailing JSON or Telnet bytes in the same receive are ignored.

`fetch_sms_response` keeps its five existing positional parameters and adds keyword-only `stop_event` and `max_response_bytes`. An optional event with `is_set()` requests cancellation, reported as `RouterCancelledError`. The default byte limit is 1 MiB per read phase (banner, wake-up, command response), including Telnet control bytes. EOF or a reset raises `RouterDisconnectedError`, a subclass of `RouterConnectionError`.

SMS envelopes remain raw. Stringified or otherwise loosely shaped `data` is preserved, and the last successful outer envelope can still win over a later error envelope. Response selection prevents nested SMS objects from overriding valid or malformed outer envelopes. Transparent-wrapper fallback remains when no top-level envelope exists; traversal stops at any dictionary containing both `code` and `msg`, including error envelopes. The public JSON extraction helper still enumerates nested objects. Message normalization and stronger payload-schema validation are deferred.

No GUI, carrier account integration, SIM/signal detection, or hardware probing is included. Importing the package does not connect to a router. No runtime dependencies or browser packages are required.

```text
src/sim_manager/
├── __init__.py
└── devices/
    ├── __init__.py
    └── d2/
        ├── __init__.py
        └── router.py
tests/
├── test_d2_router.py
└── test_d2_router_reliability.py
```

## Offline verification

From this repository root in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -B -m unittest discover -s tests -v
```

The suite uses only the Python standard library, synthetic socket transcripts, and controlled clocks. Tests block real socket construction and replace the connection factory; they require no router, browser, package installation, or personal data. Characterization tests retain selected legacy behavior, and regression tests cover the deliberate Task 002 changes. Passing offline tests does not establish compatibility with any router firmware.

## Transport assumptions

The supported path requires an already available direct Telnet shell and the existing `cped` UBus SMS command. Login prompts are rejected; the transport does not enable a shell, authenticate, or discover router/modem capabilities. The fixed marker and exact standalone-line output are hardware assumptions that remain unverified in this task.

Balanced malformed JSON or shell noise can be skipped. An unclosed leading brace is treated as an incomplete outer object; the parser rejects that response rather than searching inside it for a nested success. Router output must therefore avoid unclosed brace-like shell noise before its response. Telnet option-refusal replies remain best effort: their socket errors are swallowed as in the legacy transport, while cancellation/deadline checks still bound processing.

Cancellation and deadlines use short socket polls (up to 0.5 seconds normally, 0.1 seconds with `stop_event`). Short cancellation polls preserve the legacy 0.5-second idle wait for banner/wake-up reads, capped by their respective 0.7/0.25-second phase deadlines. Connection setup uses a daemon worker and caller polls of at most 0.05 seconds. The caller can abandon a blocked connection attempt, and a late socket is closed. The OS DNS call itself cannot be interrupted; repeated abandoned DNS calls can temporarily accumulate daemon workers. No blocking worker join is required for shutdown.

Diagnostic logs and exception output must mask or omit full phone numbers/MSISDNs, IMSIs, ICCIDs, OTPs, sensitive SMS bodies, authentication cookies, tokens, and passwords. Returned SMS data is sensitive and must not be logged wholesale.

The `pyproject.toml` declares a setuptools build backend for future packaging. Building/installing the distribution requires that build tool; source imports and the offline test command above do not.

See [WORKFLOW.md](docs/WORKFLOW.md) for repository boundaries and verification, [AGENTS.md](AGENTS.md) for security/development rules, and the [active foundation plan](plans/active/000-foundation-reboot.md) for findings and deferred tasks.

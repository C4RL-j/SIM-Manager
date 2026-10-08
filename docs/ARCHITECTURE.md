# SIM Manager architecture

Intended application layers:

```text
UI
 │
Services
 │
Carrier abstraction
 ├── DITO
 └── Smart
 │
Device abstraction
 └── D2
     └── Quectel modem
```

Task 001 established the Python package and D2 device namespace; Task 002 completed scoped hardening of the existing transport in place:

```text
src/sim_manager/
├── __init__.py
└── devices/
    ├── __init__.py
    └── d2/
        ├── __init__.py
        └── router.py
```

`devices/d2/router.py` started as a byte-for-byte copy of the legacy Telnet/UBus SMS transport. Task 002 retains the exact UBus command, default endpoint/read count, and historical marker while adding stateful Telnet decoding, standalone-line completion, bounded reads, monotonic deadlines, cooperative cancellation, and sanitized transport errors. It uses the Python standard library and does not depend on browser, UI, or carrier packages. The new package never imports code from `old/`.

The transport still returns the raw selected SMS envelope; message normalization and payload-schema decisions are deferred. It reads SMS through the router shell and does not establish direct Quectel communication, SIM/network/signal detection, or carrier support. Services, carriers, shared models, storage, and UI remain future work described in `plans/active/000-foundation-reboot.md`.

Response processing stops at the completed marker line even if trailing JSON or Telnet bytes share the same receive. Envelope selection does not descend into valid or malformed response payloads. Transparent structural wrappers are supported, with traversal stopping at any `code`/`msg` envelope. An unclosed leading brace is rejected rather than used for unsafe nested resynchronization. The public extraction helper's nested enumeration, loosely shaped `data`, last-success selection, and best-effort Telnet refusal errors remain compatibility behavior.

Connection setup runs in a daemon worker so the caller can honor cancellation and its monotonic deadline even while an OS resolver/connect call is blocked. An abandoned worker closes a socket if it eventually arrives. The underlying DNS call cannot be interrupted; repeated abandoned DNS calls may temporarily accumulate daemon workers. No hardware or live-network validation is included in Task 002.

Socket polling remains at most 0.5 seconds normally or 0.1 seconds with cancellation enabled. Banner/wake-up reads retain the legacy 0.5-second idle wait within their respective 0.7/0.25-second phase deadlines; short cancellation polls do not shorten that idle window. Task 002 is verified offline.

Task 003 completed discovery with `tools/d2_discovery.py`, offline probe/parser tests, and hardware evidence. The manually invoked tool reuses transport helpers with a fixed read-only query allowlist, bounded deadlines/output, cooperative cancellation, and privacy-filtered summaries. It is not imported at startup and does not extend the production device API. Raw capture is explicit and limited to an ignored private directory. Findings and uncertainties are recorded in `docs/devices/D2-HARDWARE-CAPABILITIES.md`: Task 003 verified the USB module identity and kernel default-route binding, while SIM/operator/registration/radio runtime fields remained untested. Production transport code and its existing tests were unchanged in Task 003; no carrier interpretation or production models were added.

Task 004 completed read-only cellular telemetry discovery through the active `/opt/web` firmware/admin UI. Development tools now include a strict source-evidence helper and a seven-GET same-origin browser probe with sanitized offline fixtures. The user supplied authenticated observations from the legitimate Brave session; authorization remained inside the router origin. Raw Ready/Connected/LTE labels, band/signal strings, and identifier field types are verified, while identifier validity, units, registration, roaming, carrier identity, and modem firmware revision remain unverified. No production device API, carrier detection, or product UI was added. Getter execution continues to require firmware/UI evidence of read semantics. The capability report separates source bindings, authenticated values, and interpretation limits. Task 005 has not begun; the foundation plan remains active for deferred work.

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

Task 001 establishes only the Python package and D2 device namespace:

```text
src/sim_manager/
├── __init__.py
└── devices/
    ├── __init__.py
    └── d2/
        ├── __init__.py
        └── router.py
```

`devices/d2/router.py` is a behavior-preserving copy of the legacy Telnet/UBus SMS transport. It uses the Python standard library and does not depend on browser, UI, or carrier packages. It reads SMS through the router shell; it does not establish direct Quectel communication, SIM/network/signal detection, or carrier support. The new package never imports code from `old/`.

Services, carriers, shared models, storage, and UI remain future work described in `plans/active/000-foundation-reboot.md`. No new interfaces or protocol hardening are introduced in Task 001.

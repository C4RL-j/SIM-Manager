# SIM Manager

A lightweight Windows SIM management application in development. Task 001 establishes a Python package and an offline-tested D2 SMS transport baseline. Python 3.11 or newer is required.

## Current scope

The only device implementation is `sim_manager.devices.d2.router`, copied unchanged from the read-only legacy reference at `../old/D2-desktop/router.py`. It uses the existing Telnet/UBus inbox path. Historical DITO labels, defaults, errors, and protocol limitations remain intact to preserve behavior during extraction.

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
└── test_d2_router.py
```

## Offline verification

From this repository root in PowerShell:

```powershell
$env:PYTHONPATH = (Resolve-Path ./src).Path
python -B -m unittest discover -s tests -v
```

The suite uses only the Python standard library, synthetic socket transcripts, and a deterministic clock. Tests block real socket construction and replace the connection factory; they require no router, browser, package installation, or personal data. Characterization tests preserve observed legacy limitations; passing them does not certify protocol hardening or hardware compatibility.

The `pyproject.toml` declares a setuptools build backend for future packaging. Building/installing the distribution requires that build tool; source imports and the offline test command above do not.

See [WORKFLOW.md](docs/WORKFLOW.md) for repository boundaries and verification, [AGENTS.md](AGENTS.md) for security/development rules, and the [active foundation plan](plans/active/000-foundation-reboot.md) for findings and deferred tasks.

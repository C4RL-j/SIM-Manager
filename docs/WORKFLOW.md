# Development workflow

The repository root is `C:\PROJECTs\SIM-manager_workspace\sim-manager`. Run project commands there. Initialize Git only in this directory; never initialize Git at the workspace root or include `../old/D2-desktop/` in this repository.

The legacy tree is read-only reference material. Copy approved reusable code into `src/sim_manager/`; never import from the legacy tree at runtime. Compare before/after file lists and SHA-256 hashes when verifying that legacy files remain unchanged.

Read `AGENTS.md`, the relevant docs, and the active plan before changing code. Implement only the approved task. Task 001 preserved and characterized the legacy router behavior. Task 002 completed transport hardening with focused regressions; message normalization, Task 003 hardware investigation, carrier/account features, and GUI work remain deferred. Task 003 has not begun.

## Offline transport tests

Use Python 3.11 or later. The transport has no runtime dependencies, and its tests use only the standard library. No package installation, GUI/browser package, or router connection is needed:

```powershell
# Working directory: sim-manager
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -B -m unittest discover -s tests -v
```

The characterization/regression suite uses synthetic socket responses and controlled clocks. It must never open a live connection. `-B` prevents bytecode files during verification. Hardware probing and browser/account work are outside Task 002. Regression cases must distinguish intentional changes from preserved legacy behavior, including echo-disabled completion, Telnet fragmentation, bounded output, cancellation, disconnects, and sanitized errors. Keep coverage for trailing bytes after the completion line, malformed outer envelopes, and wrapper traversal that stops at response envelopes.

Task 002 verification passed 78 tests on Python 3.13.15 with site packages disabled using `python -S -B -m unittest discover -s tests -v`. Keep the 0.5-second idle wait for banner/wake-up reads within their 0.7/0.25-second phase deadlines; receive polls of up to 0.1 seconds when cancellation is enabled must not shorten that idle wait.

## Review and privacy

Run the relevant offline suite, review `git diff` and `git status`, and verify the legacy hashes before reporting completion. Include newly created files in the review; ordinary `git diff` does not show untracked file contents. Do not commit unless explicitly requested.

Diagnostic logs and exception output must mask or omit full phone numbers/MSISDNs, IMSIs, ICCIDs, OTPs, sensitive SMS bodies, authentication cookies, tokens, and passwords. Do not retain real messages, account data, or credentials in tests or fixtures.

Update the active plan with results and limitations. Keep the foundation plan under `plans/active/` while later foundation tasks remain outstanding; finishing Task 002 does not finish the whole plan.

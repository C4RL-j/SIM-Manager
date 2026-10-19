# SIM Manager — Codex Instructions

## Project mission

SIM Manager is a lightweight Windows desktop application for managing Philippine SIM cards installed in supported LTE/5G routers.

Initial supported carriers:

1. DITO
2. Smart / TNT / Smart Bro

Initial supported hardware:

- Smart Bro Home WiFi D2
- Quectel EG060V-EAAA modem

The application should be simple, fast, local-first, and easy for non-technical users.

## Source of truth

Before making architectural or feature changes, read the relevant documentation:

- `docs/PROJECT.md` — product goals and scope
- `docs/ARCHITECTURE.md` — application architecture
- `docs/ROADMAP.md` — implementation phases
- `docs/WORKFLOW.md` — development workflow
- `docs/carriers/DITO.md` — DITO integration
- `docs/carriers/SMART.md` — Smart integration

Do not invent a different architecture without documenting the reason.

## Core architecture rule

Keep these layers independent:

Device → Carrier → Services → UI

Device-specific behavior must not leak into carrier adapters.

Carrier-specific behavior must not leak into the UI.

The UI should consume normalized interfaces such as:

- get_carrier()
- get_signal()
- get_messages()
- get_data_balance()
- get_load_balance()
- get_active_promos()

Do not create DITO-specific UI logic.

## Current development priority

Current phase:

Foundation reboot: Tasks 001–003 are complete within their approved scopes. Task 004 is in progress to discover and verify the read-only cellular telemetry interface already used by the D2 firmware/admin UI. Inspect firmware/web assets before invoking candidate getters, and use only established read-only requests. Do not guess AT/UBus/CGI/RPC commands or interact with configuration controls. Production detection/carrier logic, account integration, GUI work, and Task 005 remain deferred. Use `docs/devices/D2-HARDWARE-CAPABILITIES.md` for evidence and follow `plans/active/000-foundation-reboot.md`.

The application repository is `sim-manager/`. Initialize Git only inside this directory. `../old/D2-desktop/` is read-only reference material, must not be added to the new repository, and must not be changed without explicit authorization.

Do not implement Smart features unless the active task explicitly requests them.

However, new DITO code must be structured so Smart can later implement the same carrier interface.

## Authentication and account integration

The current user request separately authorizes read-only DITO account data on
Home after successful official MyDITO sign-in, automatic/manual account refresh,
stale-data handling and one safe live account validation. It supersedes older
account-data deferrals for this request only. Reuse the isolated site's own
authenticated client; never export session material or private raw responses.
Bind results to the active DITO SIM, show only verified reported values, and
clear them on SIM/account changes. Preserve login/D2/SMS functionality. No Smart,
TNT, purchases, subscriptions, History implementation or other task is authorized.

Use legitimate user-authenticated carrier sessions.

Never:

- hardcode passwords
- store plaintext passwords
- commit authentication cookies or tokens
- embed private credentials in source code
- bypass carrier security mechanisms

Prefer official web login/browser-session integration when appropriate.

Web scraping or network-response parsing may be used only behind the carrier adapter and must not become part of the UI architecture.

## Diagnostic privacy

Diagnostic logs and exception output must mask or omit sensitive values. Never expose full phone numbers/MSISDNs, IMSIs, ICCIDs, OTPs, SMS bodies containing sensitive information, authentication cookies, tokens, or passwords. Do not include raw router responses or authentication payloads in diagnostic output when they could contain these values. Use synthetic values in tests and fixtures.

## Data integrity

Always distinguish between:

- carrier-reported account data
- router/modem information
- locally measured usage

Never display locally estimated usage as an official carrier balance.

## Coding rules

- Prefer simple implementations over unnecessary abstractions.
- Keep modules small and focused.
- Avoid duplicated carrier logic.
- Preserve existing working D2 router functionality unless replacement is intentional.
- Add comments for non-obvious modem/router behavior.
- Do not silently change public interfaces.
- Never commit credentials, SIM identifiers, OTPs, cookies, tokens, or personal account data.

## Workflow

Before implementing a substantial feature:

1. Inspect the existing code.
2. Read relevant docs.
3. State which layers are affected.
4. Create/update an implementation plan under `plans/active/` when the change spans multiple modules.
5. Implement the smallest complete version.
6. Run available tests/checks.
7. Review `git diff`.
8. Update documentation if behavior or architecture changed.

When the feature is complete, move its plan from:

`plans/active/`

to:

`plans/completed/`

## Definition of done

A feature is not complete until:

- the application still starts successfully
- existing working behavior is preserved
- errors fail gracefully
- secrets are not stored in the repository
- architecture boundaries are preserved
- relevant documentation is updated
- changed functionality has been manually or automatically verified

## Local Development Permissions

Codex may:

- read all files under `C:\PROJECTs\SIM-manager_workspace`
- modify files only under `sim-manager`
- run Python, PowerShell, Git, and test commands
- access the local D2 router at `192.168.1.1`
- inspect read-only local router/admin interfaces
- inspect browser/network behavior when necessary for router research

Codex must not:

- modify files under `old/D2-desktop`
- access unrelated personal directories
- read browser passwords or credential stores
- expose cookies, passwords, OTPs, tokens, IMSIs, ICCIDs, or MSISDNs
- run destructive system commands
- change router configuration unless explicitly authorized

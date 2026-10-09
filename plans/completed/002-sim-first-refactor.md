# SIM-first architecture and navigation

User-authorized scope: multiple saved SIM profiles, Home, SIMs, Messages,
History placeholder and router/application Settings. Preserve D2 status/SMS,
remembered router login and the existing isolated MyDITO authentication flow.
Smart support, account-data retrieval, History implementation and Task 12 are
outside this work.

## Implementation

- [x] Add neutral profiles with UUID identities, display metadata, validated
  router identity fingerprints and runtime active/account state.
- [x] Save profile metadata in an atomic per-user DPAPI-protected store;
  keep demo/injected providers isolated and sessions/SMS unpersisted.
- [x] Observe the existing normalized status snapshot, select known identities,
  offer profile creation for unknown SIMs and allow profile renaming.
- [x] Add the five-page navigation and Home summary, move account controls
  into the active DITO profile and label the Messages SIM context.
- [x] Revoke account context and cancel/clear inbox delivery on SIM change;
  preserve read-only endpoints, cancellation and bounded shutdown.
- [x] Add necessary tests, run full suites and verify packaging, native launch,
  privacy, unchanged legacy, scope and Git status.
- [x] Update current documentation and record final verification here.

## Verification

Completed 2026-10-09 (Asia/Irkutsk).

## Behavior and boundaries

- Navigation: Home, SIMs, Messages, History placeholder, Settings.
- Profile metadata: UUID, name, optional full phone number, Unknown/DITO label
  and optional domain-separated ICCID fingerprint. Active/account state is
  runtime only. No phone matching, raw ICCID/IMSI retention or carrier inference.
- Matching requires a successful Ready SIM observation and validated identity
  from the existing device getter. Failed status/identity reads retain the last
  known context. Fresh successful identity loss/change revokes the old binding.
- Unknown SIMs offer optional creation. Unverified profiles remain current only
  within a continuous observation and cannot automatically match after restart.
- Renaming preserves UUID, identity, number, active state and carrier account.
  Browsing an inactive profile does not activate it or discard the active session.
- DPAPI-protected metadata is stored atomically under the current user's app-data
  directory. Corrupt/unavailable storage fails closed; restart is required before
  mutation after a storage error. Default demo/injected composition is memory-only;
  demo rejects explicit Windows storage and incompatible profile modes.
- MyDITO remains explicit and memory-only. Its controls belong to the active DITO
  profile. This association records the profile that initiated sign-in, without
  claiming the official account's subscriber number was verified against the SIM.
- SIM switches dispose the old browser/OTP/owned clipboard, reset the inbox and
  reject stale deliveries. Router Forget/authentication failure preserves the
  same SIM/MyDITO context. No new status endpoint, SMS operation or carrier request.
- Home keeps all D2 fields, distinguishes the profile's carrier label from router
  carrier evidence, and displays unavailable account metrics honestly.

## Final verification

- **602 backend/service tests** passed in 1.222 s, including 37 new profile/store
  cases and five new parser cases, with standard-library-only discovery.
- **177 GUI tests** passed in 44.737 s: all 153 prior cases migrated as necessary,
  plus 16 presentation and eight ownership/integration cases.
- **57 JavaScript tests** passed in 546.2557 ms; observer/probe implementations
  and their existing tests are unchanged. **836 tests total, zero failures.**
- Native Windows launch: compact 840×600, all five pages, visible form labels and
  active DITO actions, no horizontal scrolling and clean close. Guarded default
  normal/demo composition passed without live router/carrier/vault/profile reads.
  Synthetic Home/SIMs screenshots were inspected; no live/private capture was made.
- Isolated native DPAPI encrypted-file roundtrip passed: exact synthetic metadata
  reload, number/name absent from file plaintext, runtime active state reset.
  Temporary storage was removed; existing per-user application data was untouched.
- Editable installation and wheel build passed with zero stderr, using normal
  build isolation (the local environment lacks standalone setuptools). The final
  wheel has 54 entries/50 exact runtime files and excludes tests, tools and legacy.
- 78 Python AST parses, TOML, CLI help, privacy review, tracked/untracked whitespace
  and incremental file review passed.
- All 40 legacy files and 74 pre-existing project files outside this refactor
  match the task-start SHA-256 baseline. D2 transports, MyDITO browser/policy/
  observer/service, fixtures and prior unrelated work remain unchanged.
- Git: main; 27 modified tracked and 33 new files total, including prior work.
  Nothing staged; no commit created.

## File inventory relative to task start

20 existing files updated:

```text
AGENTS.md
README.md
docs/ARCHITECTURE.md
docs/WORKFLOW.md
docs/carriers/DITO.md
src/sim_manager/app.py
src/sim_manager/models.py
src/sim_manager/devices/d2/status_parser.py
src/sim_manager/ui/accounts.py
src/sim_manager/ui/icons.py
src/sim_manager/ui/main_window.py
src/sim_manager/ui/pages/messages.py
src/sim_manager/ui/pages/settings.py
tests/test_d2_status_parser.py
tests/gui/test_accounts.py
tests/gui/test_app_messages.py
tests/gui/test_authentication.py
tests/gui/test_desktop.py
tests/gui/test_messages.py
tests/gui/test_remembered_d2_login.py
```

10 files added:

```text
plans/completed/002-sim-first-refactor.md
src/sim_manager/sim_models.py
src/sim_manager/services/sim_profiles.py
src/sim_manager/storage/sim_profiles.py
src/sim_manager/ui/pages/home.py
src/sim_manager/ui/pages/sims.py
src/sim_manager/ui/pages/history.py
tests/test_sim_profiles.py
tests/gui/test_sim_first.py
tests/gui/test_sim_pages.py
```

## Source references and limits

The identity policy is intentionally conservative; 19-digit ICCID prefix/check
digit semantics are supported by [ITU-T E.118](https://www.itu.int/rec/T-REC-E.118-202509-I/en).
20-digit acceptance is a compatibility allowance, not a standards claim. Router
field presence was previously evidenced; this refactor performs no live identity
or SIM-swap experiment. Recognition requires a fresh successful status Refresh.
Carrier is a user label, and unsupported identity formats remain unverified.

DPAPI follows Microsoft's [CryptProtectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata)
and [CryptUnprotectData](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptunprotectdata)
contracts: current-user scope, UI forbidden, matching purpose entropy, bounded
native output and LocalFree cleanup. Dropping references/wiping mutable buffers
does not promise forensic erasure of immutable Python strings or OS paging.

Smart support, History implementation, account-data retrieval and Task 12 remain
unstarted. The foundation plan stays active for its separate deferred work.

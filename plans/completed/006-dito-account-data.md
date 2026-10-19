# Live DITO account data on Home

Scope: authenticated read-only MyDITO load, remaining data, promos/expiry and
available allowances/buckets on the current DITO SIM. Preserve official login,
isolated memory-only session, D2/SMS and SIM-profile behavior. No Smart/TNT,
History, purchases, top-up, subscriptions or any other task.

- [x] Read existing architecture/session/Home boundaries and snapshot prior work.
- [x] Verify official public account getters, field semantics and session reuse.
- [x] Add bounded neutral account data and service refresh/stale/expiry handling.
- [x] Retrieve through the official page's existing authenticated client.
- [x] Add Home presentation/manual refresh/context clearing.
- [x] Run offline backend, GUI and Node suites plus privacy/lifecycle checks.
- [x] Perform one controlled live validation with user-entered official sign-in.
- [x] Record verified fields/limits, packaging/diff results and complete the plan.

Real private responses, numbers, credentials, OTPs, cookies/tokens and site IDs
must remain out of diagnostics, tool outputs, fixtures and application files.
Live validation reports only verified field presence, closed outcomes and counts.

Completed on 2026-10-09 (Asia/Irkutsk) within this user request only.

## Verified source and behavior

The official main/Home bundles establish the direct subscriber/configuration
objects and balance arrays. The new MainWorld bridge obtains the site's existing
webpack client and original subscriber getters; it does not reproduce signing,
read credentials/OTP fields, export cookies/tokens or directly call fetch.
The source-backed `qrySubsDetail`, usageGL `configParam`, `balInfo` and
`balInfo/glSumInfo` reads remain in the isolated authenticated session. Product
IDs and subscriber-number comparison stay in the page. The protected Home and
BaseLayout chunks remain blocked along with all unrelated account actions.
The public URLs, hashes, offsets and field mappings are recorded in
`tests/fixtures/dito/account-source-evidence.json`.

Load is the returned principal book (`acctResId === 1`); category balances match
the official configured glIds. Remaining values, units and per-resource expiry
are displayed unchanged. Verified unlimited flags are retained, and missing
values never become zero. No detail buckets are added into an invented total.
Current Home's "My Promo Details" names are balance-resource names, not proved
commercial offers. The unused package-history effect cannot establish active-now
semantics and was not enabled. Commercial active promo stays unavailable.

The neutral service refreshes once after strict login proof, or on explicit Home
Refresh account. Requests block overlaps, bound timeouts/cancellation and reject
old session/request/SIM/account callbacks. Temporary failure preserves old data
marked stale. Expiry/mismatch/disconnect clears snapshots and disposes the local
session. No automatic retry loop or server lifetime is introduced.

Home places active identity/account data above D2 network/signal cards, includes
reported SMS/call categories when available, displays individual balance/promo
details with their expiry, and records local successful-refresh time. The top
expiry is explicitly Load expiry. Missing values remain unavailable, and expiry
offers Sign in again through the original sign-in action. Dynamic content is
plain text; multiple/long buckets use the existing page scrolling.

## Verification

- **624 backend/service**, **203 GUI**, **77 Node** tests passed: **904 total**.
  This adds 34 cases (10 models/service, 4 parser/policy, 6 Home, 6 browser and
  8 JavaScript groups) to the prior 870. Tests cover verified separate values,
  multiple buckets, no invented totals/promos, auto/manual refresh, stale recovery,
  expiry/mismatch, changes/disposal/late callbacks, exact read policy, bounded
  schema, malformed data and private-error traps.
- One initial GUI run exposed an existing demo inbox test's idle gap between
  SIM-triggered cancellation and its scheduled replacement. Its four isolated
  tests passed; the complete 203-test rerun passed without production/test edits.
- Native synthetic Home rendering passed at 1120×760 and 840×600 with no
  horizontal scrolling. All 12 test buckets appear before the router cards;
  vertical scrolling reaches the bottom and closure clears values. Synthetic
  screenshots only were viewed, under ignored `.venv`; no live capture exists.
- One controlled live sign-in/read cycle succeeded through the production app.
  Strict sign-in and in-page active-SIM binding passed. Retrieved fields were
  load balance, remaining data, load expiry, one returned balance/promo-detail
  bucket with expiry and Last updated. SMS/call fields and commercial promo
  names were unavailable; none were invented. Home values/count/order matched
  the normalized result, data was fresh and manual refresh was enabled.
  The validation app then closed with data cleared, **zero application log
  records** and process exit **0**. No live values, credentials, codes,
  identifiers, raw responses or screenshots were exported/retained.
- The validation monitor emitted an extra generic connected/no-issue line after
  recording success. This was a monitor fall-through, not an account failure:
  the recorded success data, fresh flags, matched Home and clean exit are the
  authoritative checks. It caused no additional refresh or production change.
- Manual refresh failure/recovery and forced expiry/switch paths are verified
  offline, avoiding deliberate invalidation or another live read. The single
  live account returned one bucket; multiple buckets were verified synthetically.
- Wheel packaging passes with all **56 runtime entries** matching source and
  excluding tests/tools/legacy. All **87 Python files** parse; TOML, evidence JSON
  and JavaScript syntax pass. Privacy and tracked/new-file whitespace/diff checks
  pass. All **40 legacy hashes** and **103 prior project files** outside the
  twelve existing-file changes match baseline; ignored generated egg metadata is
  excluded. Original authentication observer, compact focus/SMS helpers, D2
  transport/status/SMS and SIM identity/storage are unchanged.

Remaining limits: commercial offer names/active-now status, missing SMS/call
categories, bucket additivity and carrier text-date timezone are unverified.
Last updated is local retrieval time, not a carrier-side timestamp. Other account
and future site schemas may differ; incompatible shapes fail closed. Actual
server expiry/lifetime/remote logout are not forced or inferred. No persistent
account data, Smart/TNT, History or other task was implemented.

## Changed files (21)

- `AGENTS.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/WORKFLOW.md`
- `docs/carriers/DITO.md`
- `src/sim_manager/account_models.py`
- `src/sim_manager/app.py`
- `src/sim_manager/carriers/dito/auth_policy.py`
- `src/sim_manager/carriers/dito/browser.py`
- `src/sim_manager/carriers/dito/account_data.py` (new)
- `src/sim_manager/carriers/dito/account_data.js` (new)
- `src/sim_manager/services/accounts.py`
- `src/sim_manager/ui/main_window.py`
- `src/sim_manager/ui/pages/home.py`
- `tests/test_account_data_service.py` (new)
- `tests/test_dito_account_data.py` (new)
- `tests/test_dito_account_data.js` (new)
- `tests/gui/test_account_home.py` (new)
- `tests/gui/test_dito_account_browser.py` (new)
- `tests/fixtures/dito/account-source-evidence.json` (new)
- `plans/completed/006-dito-account-data.md` (new)

Git remains on `main`: thirteen modified tracked files and twenty untracked
files, including prior work. Nothing staged and no commit created. Existing
user changes were preserved; no other task started.

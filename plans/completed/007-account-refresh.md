# Refresh account freshness and feedback

Scope: make the existing Home Refresh account action explicitly fetch fresh
official MyDITO data, show pending/failure accurately, retain the last successful
snapshot on failure, and verify updated values/time on success. Keep the existing
layout, official authentication and read getters unchanged. No new features,
inferred promo names/default live values, new endpoints or other task.

- [x] Inspect current button → service → browser → original page client path.
- [x] Verify original client's supported cache bypass and apply the minimum fix.
- [x] Improve pending/error feedback without changing layout or old-value handling.
- [x] Add necessary repeated-refresh/failure regression checks.
- [x] Run regression suites, privacy/diff/packaging checks and record results.

Phone numbers, credentials, OTPs, session material, raw responses and clipboard
contents remain private. Tests use synthetic providers only; no new live login
or account capture is needed for this focused change.

Completed on 2026-10-18 (Asia/Irkutsk).

The original button was already connected to real account requests. Every
accepted click advances service/browser/page request IDs and invokes the existing
official configuration and balance getters again. No service, browser, model,
authentication or endpoint rewrite was needed. `Last updated` is generated only
after a successful normalized response, rather than on click or timer expiry.

The original `useCache: false` bypasses the request library's internal cache.
Adding the supported Fetch `cache: 'no-store'` option also bypasses browser HTTP
cache without adding parameters, changing signatures or copying session material.
The current [official bundle](https://my.dito.ph/umi.27f7c829.js) forwards Fetch
options without filtering at offset 759909 (1,427,044 bytes; SHA-256
`936b01615f5d72a73b16f7d48f2fd733b3c6d561ca8423ffdab6f449bc217e67`).
The [Fetch Standard](https://fetch.spec.whatwg.org/#concept-request-cache-mode)
defines no-store HTTP cache handling; extra manual cache headers are unnecessary.

The existing button now displays `Refreshing...` and stays disabled during its
actual pending request. Existing values and their successful timestamp remain
visible while waiting. A failed refresh explicitly reports retained stale values,
or an initial failure with no defaults/time. Success replaces the snapshot with
all latest supported fields, including verified promo names/expiry when supplied,
individual bucket expiry and current success time. Missing commercial promo
fields remain unavailable in the existing integration; they are not inferred
from resource names or load expiry. No widget/card/field layout changed.

Verification:

- **625 backend/service**, **204 GUI**, **77 Node** tests passed: **906 total**.
  Two new cases plus stronger existing refresh coverage verify new request IDs,
  changed/removed fields, exact current balances/buckets/expiry, fresh UTC times,
  unchanged pending/failure values and time, clear errors, re-enabling after
  success/failure, overlap prevention and recovery. The GUI uses the actual
  service with an injected synthetic browser; production never simulates data.
- Every synthetic getter checks both cache controls. Repeated JavaScript starts
  invoke three fresh reads each and use the second response's changed values,
  retaining neither prior bucket rows nor an obsolete snapshot.
- All **87 Python files**, TOML and JavaScript syntax pass. The wheel contains
  **56 runtime entries** matching source bytes and excludes tools/tests/legacy.
  Privacy and tracked/changed-untracked whitespace checks pass. **117 prior
  project files** outside the seven changed files match the task baseline,
  including authentication, session, router/SMS, models/service and layout code.
- No authenticated account/router request, private response capture, stored profile access
  or credential access was performed for this change. Prior live source evidence
  remains historical; current cache semantics were checked against public source.

Changed files (8):

- `src/sim_manager/carriers/dito/account_data.js`
- `src/sim_manager/ui/pages/home.py`
- `tests/test_dito_account_data.js`
- `tests/test_dito_account_data.py`
- `tests/gui/test_account_home.py`
- `README.md`
- `docs/carriers/DITO.md`
- `plans/completed/007-account-refresh.md` (new)

Git remains on `main`, with prior work preserved, nothing staged and no commit
created. Restart the running application to load the changed Python/UI and page
script; the existing memory-only MyDITO login behavior is unchanged.

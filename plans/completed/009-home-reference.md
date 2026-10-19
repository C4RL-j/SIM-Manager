# Compact reference-style Home presentation

Scope: visual-only Home redesign from the user's specified card layout, palette
and typography. Preserve existing backend/data models, MyDITO/router services,
authentication, refresh, sidebar/navigation, diagnostics and unrelated pages.

- [x] Inspect current Home, normalized data limits and visual bindings.
- [x] Restyle compact active SIM, primary data card and network summary card.
- [x] Add UI-only human-readable dates and static line-art connection icon.
- [x] Preserve states/actions/privacy; hide progress without a verified total.
- [x] Run suites, native visual/resizing checks, package and scope review.
- [x] Record file inventory/results and complete the plan.

No image attachment accompanies this turn; the detailed written reference is the
design target. AccountData/AccountBucket currently expose no total allowance.
The progress bar must be hidden, never estimated from promo names or summed
buckets. No backend/schema/API extension is authorized by this visual-only task.
Only synthetic validation screenshots/content may be retained.

## Result

Home has compact SIM identity with an explicit keyboard-accessible Show number
disclosure and the existing Messages action. The main data card uses the requested
Home-only palette, a large teal reported balance, reported promo/bucket names,
human-readable expiry, a divider and load/last-successful-update footer. Additional
bucket, SMS/call and load-expiry values remain accessible through Account details.
No verified allowance total exists in the unchanged model; the thin progress
component stays reset and hidden, without parsing totals from names or summing
buckets. Single-bucket expiry omits its duplicate name; multiple named dates stay
associated and load expiry never becomes promo expiry.

The connection card combines the existing network/SIM evidence with a static
antenna icon and honest network badge. Connected requires the existing reported
network connection plus a Ready SIM for the teal presentation. Contradictory or
missing readiness gets a warning/unknown presentation. Router reachability does
not establish a mobile connection. Icon geometry is decorative and never claims
measured signal strength.

The original shared stylesheet, sidebar/navigation, MainWindow, services, models,
MyDITO/D2 authentication, account reads/refresh and Settings diagnostics remain
unchanged by this task. Refresh loading/disable, stale retention, expiry/re-sign-in,
SIM/account clearing and safe errors retain their existing behavior. No new I/O,
timer, dependency or live account operation was added.

## Incremental changed files

- `src/sim_manager/ui/pages/home.py`
- `src/sim_manager/ui/theme.py`
- `src/sim_manager/ui/home_display.py` (new)
- `tests/gui/test_account_home.py`
- `tests/gui/test_sim_pages.py` (Home assertions only)
- `tests/gui/test_home_display.py` (new)
- `README.md`
- `docs/ARCHITECTURE.md`
- `plans/completed/009-home-reference.md` (this plan)

## Validation

- 631 backend/service tests passed.
- 217 offscreen GUI tests passed in 57.148 seconds.
- 77 Node tests passed; total 925, zero failures.
- Native Windows source and packaged-wheel presentation checks passed at
  1120x760 and 840x600. A representative one-bucket snapshot fits without either
  scrollbar. Cards measure 98/249/70 pixels high. Inspected synthetic screenshots
  confirm palette, hierarchy, icon/title separation and compact layout.
- Native keyboard number reveal, mouse disclosure/refresh, loading disable,
  stale-value retention and disconnected/unknown presentation passed. Long names
  and multiple buckets wrap without horizontal scrolling; expanded/excess details
  can use the existing vertical scroller.
- Wheel build passed; all 57 runtime entries match source, including the new
  helper, with tests/tools/legacy excluded. Native wheel validation exited 0.
- All 90 source/test/tool Python files parsed; TOML and whitespace checks passed.
- All 121 other preexisting project-file hashes match the task baseline. The
  original shared stylesheet value is unchanged. Privacy review used synthetic
  content only; no account/router credentials, live snapshots or responses read.
- Final Git state includes earlier authorized work: 19 modified tracked files,
  26 untracked files, none staged. No commit or push performed.

No current reference image was attached, so the written layout/colors are the
reference. Actual signal-strength levels, additional network detection and a
verified original allowance denominator remain outside this visual-only scope.

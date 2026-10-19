# Simplify the SIM Manager Home dashboard

Scope: Home focuses on verified mobile data, promo expiry and active SIM identity
with a compact connection/network/SIM strip. Move the existing diagnostics into
collapsed Settings Connection details, using the same normalized snapshot.
Preserve theme/sidebar, MyDITO and router authentication, SMS/account refresh,
SIMs/Messages/History pages and all fetch/controller behavior. No extra polling.

- [x] Inspect current Home/Overview/Settings, view models and tests; snapshot work.
- [x] Replace Home diagnostics with focused account presentation/status strip.
- [x] Present actual promo/bucket expiry separately from load expiry.
- [x] Reuse all diagnostic fields in collapsed Settings, update from same view.
- [x] Verify readiness/connection evidence and update necessary regression tests.
- [x] Build, run suites and native synthetic layout/resizing checks.
- [x] Audit privacy/unchanged functionality, record results and complete plan.

Only synthetic native/test content may be captured. No real user account, SIM
number, credentials, OTP, cookies/tokens or raw response is logged or persisted.

Completed on 2026-10-18 (Asia/Irkutsk).

Home is now a standalone QWidget, constructing only active identity, account and
compact connection-strip cards. It no longer constructs hidden router/signal/WAN
diagnostic widgets. Data remaining has the largest value text, Promo expiry has
secondary emphasis, and load/promo details retain the existing account refresh,
pending, stale/failure and session-expiry behavior. Unavailable optional promo,
load-expiry and SMS/call rows collapse instead of leaving gaps. All dynamic
values remain plain text.

Promo expiry comes from reported AccountPromo dates or explicitly byte-unit
data-bucket dates. Multiple/unknown dates retain their individual names and
status; no earliest/latest global date is calculated. Load expiry stays separate.
Commercial promo names and unlimited/unclassified resource types are not guessed.

The three status cells consume DeviceView.network_status, network_mode and
sim_state only, with accessible text and subtle theme indicators. Neither router
availability nor WAN connectivity can manufacture mobile Connected. Explicit SIM
absence/PIN/PUK evidence shows Not Ready; missing evidence stays Unknown. Network
type shows the existing reported view value; current provider enums verify LTE
only, with unsupported modes remaining Unknown rather than guessed 5G.

Settings Connection details is checkable/keyboard-accessible and collapsed on
startup. It reuses OverviewPage's existing factories/rendering for all fourteen
diagnostic fields at compact font sizes: router carrier, network type/state,
SIM/PIN, six radio metrics/bands, WAN/address availability and router status.
MainWindow delivers the same existing DeviceView to both pages. Hidden details
stay current; expanding/collapsing does no I/O or polling. Wrapped Settings notes
and form rows fix narrow-width overflow without hiding horizontal scrollbars.

Verification:

- **631 backend/service**, **209 GUI**, **77 Node** tests passed: **917 total**.
  Eleven new cases cover six expiry/readiness rules, three disclosure/update/
  layout cases and two Home presentation/connection rules. Existing account,
  SIM, desktop and refresh checks were updated only for the intended field
  placement and distinct promo/load expiry. Final Home/status-dot spacing polish
  passed all 25 affected Home/SIM-page cases after the full suite.
- Native Windows/Fusion checks used only synthetic profiles/account/device data
  at **1120×760** and **840×600**. Home has no horizontal overflow, has no vertical
  scroll for the representative one-bucket normal-size state, and all primary
  labels meet their required wrapped height at minimum size. Native screenshots
  were visually reviewed under ignored `.venv`. A stress case retained all 64
  long-named buckets with vertical scrolling and a reachable status strip. Status
  dots and values have six pixels separation. Minimum-size collapsed/expanded
  Settings has no horizontal overflow; standalone details also pass at 560px.
- Every original diagnostic remains available and updated while collapsed.
  Toggling the disclosure leaves the provider-call count unchanged. Account
  refresh still uses the original MyDITO session/client/cache bypass, retains old
  values on failure and clears on SIM/account changes.
- Wheel build passes with all **56 runtime entries** matching source bytes and
  excluding tests/tools/legacy. All **88 Python files** parse; TOML/Node and
  tracked/changed-new-file whitespace checks pass. **29 protected prior files**
  match the task snapshot, including all device/carrier/storage code, theme,
  accounts and refresh controllers and the unchanged SIMs/Messages/History pages.
- No live account/router request, credential/profile-store access, private
  capture, telemetry API change, timer, polling setting or navigation page was
  added. The UI change requires an application restart to load.

Changed files (13):

- `src/sim_manager/ui/pages/home.py`
- `src/sim_manager/ui/pages/settings.py`
- `src/sim_manager/ui/main_window.py`
- `src/sim_manager/services/presentation.py`
- `tests/gui/test_account_home.py`
- `tests/gui/test_sim_pages.py`
- `tests/gui/test_desktop.py`
- `tests/gui/test_connection_details.py` (new)
- `tests/test_device_services.py`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/WORKFLOW.md`
- `plans/completed/008-home-dashboard.md` (new)

Prior work is preserved on main, with nothing staged and no commit created.

# D2 hardware capabilities — discovery record

Date: 2026-10-07 (Asia/Irkutsk)

Updated: 2026-10-08 (Asia/Irkutsk)

Status: Tasks 003–007 and 006.1 complete within their approved scopes; Task 008 not started

This report records read-only observations from the router identified by the user as a Smart Bro Home WiFi D2. It is discovery evidence, not a production device API or a carrier-detection implementation. Model, module, SIM, and cellular identity must be established from actual responses rather than the router's branding.

## Setup and evidence classifications

Task 007 initially found no responding Telnet banner or HTTPS handshake within bounded deadlines. After the user connected to the D2, public firmware inspection and direct application login succeeded. The Task 007 section below supersedes those initial connectivity limitations and establishes the production session path; historical observations retain their original scope.

## Task 007 — direct authentication and LIVE validation

Validated on 2026-10-08 (Asia/Irkutsk), against the local D2 only. Windows hosts maps `smartbrosettings.net` to `192.168.1.1`; production connects directly to the literal IP without DNS and rejects redirects. Source discovery read the public Vue assets and the existing fixed read-only public certificate source. No credentials were read from browser storage, copied into chat or written to files.

### Login and session evidence

The sanitized public-source ledger is `tests/fixtures/d2/auth-source-evidence.json`; it contains asset hashes, module names, decoded-character offsets and minimal safe excerpts, rather than full bundles or authenticated captures.

| Finding | Classification | Evidence / limit |
| --- | --- | --- |
| Login request | VERIFIED SOURCE and LIVE | `POST /web/v1/user/login`, `Content-Type: application/json;charset=utf-8`, JSON object with `username` and `password`. App module `c24f`, offset 45584; login module `c6f7`, offset 4240; Axios module `2444`, offset 15447. One legitimate application login succeeded. |
| Credential input / transformation | VERIFIED SOURCE | Both router-admin inputs start empty and are editable/required (`c6f7`, offset 2683). No hash, encryption or base64 transformation occurs in the inspected request chain. Production preserves entered strings and assumes no username. |
| Success response | VERIFIED SOURCE and LIVE | HTTP 200/body `code=200`, object `data`, nonempty `data.Authorization`; auxiliary `userrole`/`FirstLogin` are ignored. Module `4360`, offset 1302. No raw response or session value was exported. |
| Protected request header | VERIFIED SOURCE and LIVE | The returned opaque value is forwarded unchanged in the case-insensitive `Authorization` header (`b775`, offset 40136). Production validates bounded header-safe ASCII and keeps it private to D2 infrastructure. No prefix is invented. |
| Browser/cookie binding | VERIFIED LIVE for this firmware/session | Direct-IP login followed by all seven GETs succeeded without cookies, browser state, XSRF, Origin or Referer headers. Source `withCredentials=true` and stock optional Axios XSRF handling do not impose a demonstrated requirement. Other firmware remains untested. |
| Authentication expiry response | VERIFIED SOURCE; offline enforcement | The admin interceptor clears authentication on HTTP/body 401 (`b775`, offset 40329). An unauthenticated production-transport GET returned HTTP 401. Production stops the cycle and invalidates on 401, with defensive 403 support tested offline. A real authenticated token was not deliberately expired or revoked. |
| Session lifetime | UNKNOWN server lifetime | Admin module `56d7`, offset 3857, checks 900000 ms inactivity when clicked and calls logout. This is a frontend inactivity rule, not verified server TTL. Production does not invent a timer or retain credentials for automatic login. |
| Rejected-password code | UNKNOWN hardware-specific code | Source rejects non-200 body codes; incorrect credentials were not intentionally submitted. Synthetic tests cover rejection without asserting an observed wrong-password code. |
| Logout | VERIFIED SOURCE; runtime UNKNOWN | `POST /web/v1/user/logout` without explicit body (`c24f`, offset 56331). Production deliberately omits this optional request. Closing/invalidation discards local authorization and cancels work; server logout behavior was not exercised. |

### Verified TLS policy

The public certificate was read from the already reviewed `/opt/web/conf/server.crt` source and matches the local HTTPS peer. It is packaged as `src/sim_manager/resources/d2-server.pem`; no private key is included. DER SHA-256 is `b80c4d8777a8894acfbcda6be4389bc8329eae1d25fbc3981ae7a6e0439d4e1b`. The observed certificate is valid from 2020-10-28 to 2030-10-26 and includes IP SAN `192.168.1.1`.

For the exact default IP origin, production uses an isolated trust store containing only that public certificate, with both `CERT_REQUIRED` and hostname verification enabled. Other configured private IP origins use ordinary system trust unless an explicit certificate is supplied; hostname verification remains enabled. There is no verification-disable fallback, hostname relaxation, global warning suppression, DNS lookup or redirect following. Certificate rotation/other firmware requires a reviewed trust-resource update. A live unauthenticated approved GET returned HTTP 401 through this production TLS transport, followed by successful authenticated reads.

### Live application results

The user entered credentials only into the native SIM Manager dialog. One legitimate login and two complete status cycles succeeded: seven approved GETs immediately after login, then the same seven through Overview Refresh. Both normalized snapshots had seven successful sources, `partial=False`, no issues, and live source `device:d2`. Native GUI rendering showed LIVE and was visually checked; no raw authenticated capture was retained. The temporary screenshot contains safe presentation values only and remains outside the repository.

| Displayed field | Verified live value | Limit |
| --- | --- | --- |
| SIM / PIN check | Ready / Off | Reported labels; independent presence and absent/locked states remain untested. |
| Network mode / status | LTE / Connected | No EPS-registration, roaming or Internet-health claim. |
| Reported bands | 1 / 28 | No aggregation or primary/secondary-band interpretation. |
| RSRP / secondary RSRP | -87 / -95 | Numeric readings only; units and path meaning remain unverified. |
| RSRQ / RSSI / SINR | -9 / -76 / 23 | Units/measurement semantics remain unverified. |
| WAN state / address availability | Connected / Reported | Normalized connection label and nonempty address availability only; no address/DNS value retained. |
| Router status | Status available | All seven getters succeeded in both cycles. |
| Carrier | Unknown | No neutral operator/PLMN value was exported or mapped. |

Only legitimate login/session creation was requested as a write. No APN, RAT/network-mode, LTE-band, reboot/reset, SMS, Wi-Fi, SIM-PIN, password or firmware/configuration action was requested. The read allowlist contains exactly the seven earlier verified status GETs. This records requested operations, not an audit of firmware-internal counters/logs. Session expiry/relogin, partial failures, malformed/rejected authentication, cancellation, redaction and closure are covered offline; server TTL and runtime logout remain unknown.

The existing direct shell at the default `192.168.1.1:2323` endpoint responded to the development probe. The hardened transport's Telnet decoding and terminated-marker framing worked for the recorded queries. An initial sandbox connection attempt failed; subsequent authorized network access outside that sandbox succeeded. The failed attempt does not establish an unavailable router or capability.

`DISTRIB_ID=OpenWrt` is verified router OS identity. USB device `1-2` directly reports vendor ID `2c7c`, product ID `6004`, manufacturer `Quectel`, and product `EG060V-EAAA`. A kernel network interface bound to that USB device carries both observed default routes. Task 004's user-supplied authenticated report now verifies raw Ready/Connected/LTE labels, band/signal strings, and masked identifier field types. Exact identifier values, operator identity, router/modem firmware versions, radio units, and broader state semantics remain unverified. Omitted values do not establish absent fields.

Use the latest four classifications requested for Task 003:

| Status | Meaning |
| --- | --- |
| VERIFIED | Observed directly on the actual router. The source and value shape are recorded. Units or status-code interpretation require their own evidence. |
| INFERRED | Strongly suggested by source/response structure, but not directly confirmed. It must not become production behavior. |
| NOT FOUND | Relevant safe sources were investigated, but no reliable source for this capability was found. This is scoped to the investigated firmware/interfaces. |
| UNTESTED | The capability has not yet been tested through a verified safe source. A failed connection or an omitted value does not prove absence. |

“Unverified” is an umbrella description for uncertain evidence, not an additional field status. Verification is scoped: a USB descriptor proves the reported module identity; a kernel route proves route configuration, not cellular registration or working Internet access.

## Queries actually executed

All 18 fixed query types below ran manually and sequentially through `tools/d2_discovery.py`; some metadata queries were repeated while summaries were refined. Evidence IDs identify unique queries, not a total invocation count. Its framing uses `printf` only to emit start/end and exit-status lines to the Telnet stream. It does not write router files or configuration.

| Evidence | Command | Read-only basis | Exit | Direct observation |
| --- | --- | --- | --- | --- |
| E01 | `command -v ubus` | Shell executable lookup; no execution of vendor operations. | 0 | A recognized UBus executable path exists; the exact path is omitted here. |
| E02 | `ubus -h` | CLI help/metadata only. | 1 | Help advertises `-t`, `-v`, `list`, and `call`. The nonzero help exit is recorded, not treated as lack of UBus support. |
| E03 | `ubus -t 5 list` | Advertised UBus object listing. | 0 | Object `cped` is present. Five other names were omitted by the privacy allowlist. |
| E04 | `ubus -t 5 -v list cped` | Advertised verbose object/method schema listing; no method invoked. | 0 | `cped` exposes method `cmd` with string arguments `cmd` and `arg`. |
| E05 | `cat /etc/openwrt_release` | Reading a fixed firmware release file. | 0 | `DISTRIB_ID=OpenWrt`; other release values omitted. |
| E06 | `find /www -maxdepth 4 -type f` | Static file-name enumeration. | 0 | 252 output lines; five reviewed paths reported and 247 other names omitted. |
| E07 | `cat /www/js/config.js` | Static source at a path observed in E06; source is not executed. | 0 | 289 lines; no allowlisted operation-name candidates or recognized terms. |
| E08 | `cat /www/js/page.js` | Static source at a path observed in E06; source is not executed. | 0 | 304 lines; no allowlisted operation-name candidates or recognized terms. |
| E09 | `web-sms-source-index` fixed command below | Static search for the legacy inbox command string. | 0 | No matching files reported. |
| E10 | `web-status-name-index` fixed command below | Static search for getter-like names; no candidate is invoked. | 0 | No candidates reported. |
| E11 | `ip address show` | Documented network display operation. | 0 | IPv4 and IPv6 host addresses observed, including global-scope addresses on `br0`; exact addresses masked. Final parser recheck confirmed interface-header isolation. |
| E12 | `usb-descriptors` fixed command below | Reads only USB identification descriptor files, excluding serial numbers and device nodes. | 0 | USB `1-2`: `2c7c:6004`, `Quectel`, `EG060V-EAAA`. Root hubs also observed. |
| E13 | `ip route show` | Documented routing-table display operation. | 0 | One IPv4 default route; interface name/gateway omitted or masked. |
| E14 | `web-capability-references` fixed command below | Static term occurrence search; source text is not executed. | 0 | Seven searched terms occur across 18 source files; no runtime values or safe getter established. |
| E15 | `cat /etc/resolv.conf` | Reading the current resolver file. | 0 | Three IPv4 nameserver entries; addresses masked. Cellular origin unverified. |
| E16 | `grep -E '^[[:space:]]*option[[:space:]]+apn[[:space:]]' /etc/config/network` | Filtered read of APN declarations only; no configuration dump/write. | 2 | Source query failed; no APN value or source-absence conclusion is justified. |
| E17 | `ip -f inet6 route show` | Documented IPv6 routing-table display operation. | 0 | One IPv6 default route; interface name/gateway omitted or masked. |
| E18 | `usb-network-binding` fixed command below | Read-only route displays and kernel device symlink correlation. Session-local variables only. | 0 | One network interface maps to USB `1-2` and matches both IPv4 and IPv6 default-route interfaces. |

The BusyBox manual documents IP address/route display and address-family forms; the Linux USB ABI documents identification descriptor fields. These sources justify observational command semantics, not hardware availability or the observations above. Hardware evidence comes only from the actual query results. [BusyBox command reference](https://busybox.net/downloads/BusyBox.html), [Linux USB sysfs ABI](https://github.com/torvalds/linux/blob/master/Documentation/ABI/testing/sysfs-bus-usb).

Exact longer commands (query names match the fixed registry):

```sh
# E09: web-sms-source-index
find /www -maxdepth 4 -type f \( -name '*.js' -o -name '*.html' \) -exec grep -l 'sms.get.inboxdata' {} \;

# E10: web-status-name-index
find /www -maxdepth 4 -type f \( -name '*.js' -o -name '*.html' \) -exec grep -H -oE '(sim|network|lte|wan|modem|device|system|internet)\.(get|status|info)[a-z0-9_.]*' {} \;

# E12: usb-descriptors
for d in /sys/bus/usb/devices/*; do for f in idVendor idProduct manufacturer product; do if [ -f "$d/$f" ]; then printf "%s %s=" "${d##*/}" "$f"; cat "$d/$f"; fi; done; done

# E14: web-capability-references
find /www -maxdepth 4 -type f \( -name '*.js' -o -name '*.html' \) -exec grep -H -i -oE 'iccid|imsi|msisdn|plmn|mcc|mnc|rsrp|rsrq|sinr|rssi|earfcn|roaming|registration|quectel|apn|ipv4|ipv6|operator' {} \;

# E18: usb-network-binding
v4dev="$(ip route show | sed -n 's/^default .*dev \([^ ]*\).*/\1/p')"; v6dev="$(ip -f inet6 route show | sed -n 's/^default .*dev \([^ ]*\).*/\1/p')"; for n in /sys/class/net/*; do if [ -e "$n/device" ]; then printf "%s|%s|" "${n##*/}" "$(readlink -f "$n/device")"; if [ "${n##*/}" = "$v4dev" ]; then printf v4; fi; if [ "${n##*/}" = "$v6dev" ]; then printf v6; fi; printf "\n"; fi; done
```

`cped.cmd` existing does not prove that any particular command string is read-only. No vendor getter was invoked. No SMS query/read, SMS send/delete, AT command, configuration write, service restart, mobile-data reconnect, or reboot was performed in this evidence set.

## Observed response shapes

These are privacy-filtered representations of observed shapes, not raw captures:

```text
E01: recognized executable path found
E02: advertised CLI items: -t, -v, list, call
E03: object names: cped; 5 other names omitted
E04: "cmd": {"cmd": "String", "arg": "String"}
E05: DISTRIB_ID='OpenWrt'; other values omitted
E06: source paths: /www/index.html, /www/js/config.js, /www/js/jquery.js,
     /www/js/page.js, /www/page/login/login.html; 247 other names omitted
E07: source_line_count=289; operation_name_candidates=[]; recognized_terms=[]
E08: source_line_count=304; operation_name_candidates=[]; recognized_terms=[]
E09: no matching files reported
E10: no getter-name candidates reported
E11: lo: IPv4 host /8, IPv6 host /128
     eth0/wlan0/wlan1: IPv6 link /64; UP, LOWER_UP
     br0: IPv4 global /24, IPv6 global /64 and link /64; UP, LOWER_UP
     br1: IPv4 global /24, IPv6 link /64; UP, LOWER_UP
     one interface name omitted: IPv4 global /24, IPv6 link /64; UP, LOWER_UP
     37 interface names unreported; exact addresses masked throughout
E12: USB 1-2: {idVendor: 2c7c, idProduct: 6004,
               manufacturer: Quectel, product: EG060V-EAAA}
     usb1/usb2 root hubs: idVendor=1d6b, idProduct=0002/0003
E13: IPv4 default route count=1; interface omitted; gateway masked
E14: source_count=18; ipv4=148, ipv6=288, apn=16, rssi=2,
     operator=12, mnc=1, earfcn=73
E15: nameserver_families=[4, 4, 4]; nameserver addresses masked
E16: exit_code=2; active APN not established
E17: IPv6 default route count=1; interface omitted; gateway masked
E18: {interface: omitted, usb_device: 1-2,
      ipv4_default: true, ipv6_default: true}
```

No `--capture-raw` flag has been used. Unknown values, identifiers, and arbitrary shell text are omitted from normal probe output.

## Task 003 field inventory (historical)

No query above reads SIM, registration, or radio runtime state. “No observation” means UNTESTED, not an empty value, unsupported capability, or missing SIM. Host/network configuration observations below are kept separate from active modem/PDP state.

| Domain | Field | Status | Source/path and observed shape | Meaning/limitations |
| --- | --- | --- | --- | --- |
| SIM | Inserted/present | UNTESTED | No observation. | Do not infer from shell reachability. |
| SIM | Ready/PIN state | UNTESTED | No observation. | Present and ready must remain distinct. |
| SIM | ICCID | UNTESTED | No observation. | Mask or omit full identifiers. |
| SIM | IMSI | UNTESTED | No observation. | Mask or omit full identifiers. |
| SIM | MSISDN | UNTESTED | No observation. | Absence from a source would not establish that the SIM has no phone number. |
| Network | Registered operator identity | UNTESTED | No observation. | Registered operator and SIM home operator are separate facts. |
| Network | PLMN | UNTESTED | No observation. | Preserve digit strings and leading zeros. |
| Network | MCC | UNTESTED | No observation. | No derived value or carrier mapping yet. |
| Network | MNC | UNTESTED | No observation. | Preserve length/leading zeros; do not guess a split. |
| Network | Registration state | UNTESTED | No observation. | Raw codes require evidenced interpretation. |
| Network | Roaming state | UNTESTED | No observation. | Do not infer from operator naming. |
| Network | RAT / LTE/5G mode | UNTESTED | No observation. | Raw codes require evidenced interpretation. |
| Radio | LTE band | UNTESTED | No observation. | No band-lock/configuration operations permitted. |
| Radio | EARFCN | UNTESTED | No observation. | No derived frequency/band mapping yet. |
| Radio | RSSI | UNTESTED | No observation. | Value and unit/scale each require evidence. |
| Radio | RSRP | UNTESTED | No observation. | Value and unit/scale each require evidence. |
| Radio | RSRQ | UNTESTED | No observation. | Value and unit/scale each require evidence. |
| Radio | SINR | UNTESTED | No observation. | Value and unit/scale each require evidence. |
| Radio | Cell ID | UNTESTED | No observation. | Treat location-related identifiers conservatively in shared reports. |
| Radio | PCI | UNTESTED | No observation. | No normalization implemented. |
| WAN | Active APN | UNTESTED | E16 source query exited 2; no value observed. | A failed config read does not establish missing APN configuration or active PDP/APN state. |
| WAN | PDP / IP family | UNTESTED | No observation. | No PDP-context modification permitted. |
| Host network | IPv4/IPv6 address presence | VERIFIED | E11: `br0` has global-scope IPv4 `/24` and IPv6 `/64`, plus link-scope IPv6 `/64`; `br1` has global-scope IPv4 `/24` and link-scope IPv6 `/64`. Addresses masked. | Other observed shapes are listed above. Host address scope does not prove cellular assignment. Unknown interface names are omitted rather than guessed. |
| WAN | IPv4 default route / USB binding | VERIFIED | E13/E18: one default route through a network interface bound to USB `1-2`. | Route configuration only; address/session health untested. |
| WAN | IPv6 default route / USB binding | VERIFIED | E17/E18: one default route through the same USB device's network interface. | Route configuration only; active PDP/IP family and reachability untested. |
| WAN | Cellular IPv4 address/session state | UNTESTED | No directly verified modem/PDP value. | Do not equate unrelated bridge/host addresses with cellular assignment. |
| WAN | Cellular IPv6 address/session state | UNTESTED | No directly verified modem/PDP value. | Address availability, route presence, and connection health are distinct. |
| Host resolver | DNS server configuration | VERIFIED | E15: three IPv4 nameserver entries, addresses masked. | Cellular provenance and DNS resolution health remain untested. |
| WAN | Mobile-data connection health | UNTESTED | No modem session or end-to-end test. | USB default routes do not prove registration or working Internet access. |
| Modem | Vendor | VERIFIED | E12: `/sys/bus/usb/devices/1-2/manufacturer` reports `Quectel`; vendor ID `2c7c`. | Direct USB descriptor observation. |
| Modem | Model/module | VERIFIED | E12: `/sys/bus/usb/devices/1-2/product` reports `EG060V-EAAA`; product ID `6004`. | Direct USB descriptor observation, not a router-brand inference. |
| Modem | Firmware revision | UNTESTED | No observation. | Router OS release is not modem firmware. |

At Task 003 completion, no safe read-only cellular getter was found in the inspected UBus schema and selected static-source/name searches. This is NOT FOUND for that discovery path, not proof that the hardware lacks SIM/operator/radio capabilities. Task 004 below establishes the different Vue application's getters and authenticated runtime observations; this historical matrix is retained unchanged. The E16 error likewise cannot establish APN absence.

Static references in E14 are VERIFIED as text occurrences only. They are too weak to assign INFERRED status to any runtime field: `earfcn` may relate to band configuration and `rssi` may describe Wi-Fi. Operator/MNC strings do not establish an observed operator or MNC. No inferred value is used by production code.

## Carrier-detection evidence

No PLMN/MCC/MNC or actual operator-name value was exported. Task 004 verifies that `Operator` is a string and identifier fields exist, while their values are omitted/masked; this cannot identify the inserted SIM as DITO or Smart. Quectel identity, USB routes, router branding/model, MAC address, SSID, firmware branding, and static operator references do not resolve that question. No carrier mapping is implemented.

Future discovery should seek directly reported PLMN/MCC-MNC and registered operator identity through firmware-evidenced read-only sources. Record registered-network identity separately from SIM home identity and roaming state. The device layer may eventually expose neutral values such as `plmn`; carrier interpretation belongs in the carrier layer. No carrier implementation is part of Task 003.

## Task 004 — verified cellular telemetry source

The D2 firmware contains two distinct web trees. Expanded inspection of `/www` found 139 `.shtml` templates associated with the older TR-069-style UI. Those templates do not establish the active Vue admin interface. Process metadata showed `/opt/web/start.sh` alongside `uhttpd`/`/www`, leading to the separate `/opt/web` application. Listener metadata showed ports 443 and 8080, with no port-80 listener observed; a port-80 root request timed out.

The following source evidence was observed directly through fixed read-only file/metadata queries:

| Evidence | Source | Observation | Classification/limit |
| --- | --- | --- | --- |
| T4-S01 | `/www` templates and process/listener metadata | Older template tree differs from the `/opt/web` application; observed listeners include 443/8080. | VERIFIED source/topology observations; not cellular values. |
| T4-S02 | `/opt/web/views/index.html` | References `/opt/web/static/js/app.5af0ce0f.js`. | VERIFIED asset reference for this firmware build. |
| T4-S03 | `/opt/web/static/js/app.5af0ce0f.js` | Defines the exact GET requests listed below. | VERIFIED request construction; source alone does not verify response values or field semantics. |
| T4-S04 | `/opt/web/static/js/chunk-a65ab4a6.3cfa7746.js` | Views consume responses into `e.nodeData.Internet=t.data` and `simInfo=t.data`; keys include `USIMStatus`, `UICCID`, and `IMSI`. Wireless status reads poll with `setTimeout`; signal-related references include `rsrp`, `rsrq`, and `sinr`. | VERIFIED view bindings/polling source. Runtime follow-up is recorded separately in T4-A01–A07; units remain unverified. |
| T4-S05 | Request/authentication interceptor in `/opt/web/static/js/app.5af0ce0f.js` | Reads `localStorage.Authorization`, sends an Authorization header, and includes `withCredentials` behavior. | VERIFIED authentication mechanism in source; no stored credential value was exported or logged. |

These paths, versioned asset filenames, and view bindings are firmware-specific. Reading a view's field name does not prove the installed SIM's state, identifier, operator, registration, or signal measurement.

### Source field inventory

The following keys were observed in firmware/admin view bindings before authenticated probing. This source matrix is retained as provenance, not as a guarantee that every key exists in a response. The source sometimes assigns `t.data` into a view model. T4-A01–A07 below now establish specific response paths/types; unreported keys, null/missing behavior, units, and broader enum meanings remain unverified.

| View/group | Observed keys | Source status | Runtime status |
| --- | --- | --- | --- |
| Internet/status view | `Status`, `Band`, `CellId`, `ECellId`, `Operator`, `RSRP`, `RSRQ`, `SINR` | VERIFIED bindings. | T4-A02 verifies paths/types and allowed status/band/signal values; operator text and cell IDs remain omitted/masked. |
| `simInfo` view | `USIMStatus`, `UICCID`, `IMSI`, `DeviceModel`, `IMEI`, `RouterVersion` | VERIFIED bindings. | T4-A04 verifies Ready and selected identifier field types; `DeviceModel`/`RouterVersion` are not exported in this report. |
| WAN `ConnectionStatus` view | `ConnectMode`, `ConnectStatus`, `IMEI`, `IMSI`, `RSRP0`, `RSRP1`, `RSRQ`, `RSSI`, `SINR`, `USIMStatus` | VERIFIED bindings. | T4-A05 verifies allowed labels/signals and identifier types; registration and signal units remain unverified. |
| SIM-card information view | `SIMCardState`, `RetriesPIN`, `PINCheckEnabled` | VERIFIED bindings. | T4-A06 verifies `READY`, `OFF`, and string `RetriesPIN` whose value is omitted. No PIN action executed. |
| Device information view | `RunningTime`, `ProductModel`, `HardwareVersion`, `SoftwareVersion`, `UBootVersion`, `SerialNumber`, `IMEI`, `IMSI`, `MacAddress`, `IpAddress`, `SubnetMask` | VERIFIED bindings. | T4-A07 verifies selected string field types only; arbitrary model/version text omitted, identifiers masked, `RunningTime` unreported. |

PLMN/EARFCN references remain configuration/search evidence rather than an established telemetry value. No candidate was invoked from those names alone. T4-A05 now establishes a `PCI` string field, but its value was omitted; no numeric decoding is invented. No PLMN/MCC-MNC value or carrier mapping is established. Signal numbers and status codes are not normalized based on names.

### Getter requests and authentication observations

The firmware bundle explicitly constructs the following GET requests. None of the listed paths was guessed from a desired capability or substituted with a configuration operation.

| Request | Source evidence | Initial unauthenticated result | Authenticated follow-up |
| --- | --- | --- | --- |
| `GET /web/v1/dashboard/wirelessinfo` | T4-S03/T4-S04, dashboard getter and status-view use. | HTTP 401; JSON shape `{code: integer, msg: string}`. | T4-A01: HTTP 200/body code 200, object data; no allowlisted fields exported. |
| `GET /web/v1/dashboard/internetinfo` | T4-S03/T4-S04, dashboard getter and response consumption. | HTTP 401; JSON shape `{code: integer, msg: string}`. | T4-A02: HTTP 200/body code 200; status/band/signal fields observed. |
| `GET /web/v1/dashboard/waninfo` | T4-S03, exact GET construction. | Not attempted in initial unauthenticated checks. | T4-A03: HTTP 200/body code 200; connection/address field types observed. |
| `GET /web/v1/dashboard/deviceinfo` | T4-S03, exact GET construction. | Not attempted in initial unauthenticated checks. | T4-A04: HTTP 200/body code 200; Ready and masked SIM identifiers observed. |
| `GET /web/v1/status/wanstatus` | T4-S03, exact GET construction. | Not attempted in initial unauthenticated checks. | T4-A05: HTTP 200/body code 200; nested WAN status/signal fields observed. |
| `GET /web/v1/setting/deviceinfo` | T4-S03, exact GET construction. | Not attempted in initial unauthenticated checks. | T4-A07: HTTP 200/body code 200; device/version/identifier field types observed. |
| `GET /web/v1/setting/network/pinmanagement/simcardinfo` | T4-S03/T4-S04, SIM-information getter/view references. | Not attempted in initial unauthenticated checks. | T4-A06: HTTP 200/body code 200; raw SIM/PIN-information labels observed. No PIN operation performed. |

An unauthenticated `GET /` over HTTPS port 443 returned HTTP 200. The two initial telemetry requests sent no cookies/authentication headers and returned HTTP 401. Authentication requirements for the other five were not tested separately without the session. The user subsequently executed the fixed browser probe inside the legitimate signed-in Brave tab; all seven requests returned HTTP 200/body code 200/object data. T4-S05 establishes the firmware's local-storage/header session mechanism, used privately inside that origin. No credential value, authentication cookie, or token was exported. No authentication bypass or guessed credential flow was used.

The initial development HTTPS requests used the public certificate read from `/opt/web/conf/server.crt` as a trust anchor. Certificate verification remained enabled; hostname checking was disabled for the private-IP connection. This is a development-only TLS assumption, not a production TLS policy. No private key or credential database was read. The browser probe reads the existing Authorization value privately inside the tab; no password, cookie, or token was exported or logged.

Observed unauthorized response shape, with message text omitted:

```text
HTTP 401
{"code": <integer>, "msg": <string omitted>}
```

Only the fields recorded in the authenticated ledger below are runtime observations; other source-only keys remain unverified. At Task 004 completion, no PLMN/carrier mapping, production detection, router-setting write, or Task 005 work had begun.

### Manual signed-in-browser probe (authenticated report received)

The user confirmed Brave. Sixteen Brave processes were observed, but no exposed remote-debugging port/pipe or browser connector was available to access its signed-in router tab. This is an access limitation of the development environment, not evidence of a missing or expired router session.

The user manually executed `tools/d2_browser_probe.js` in the existing signed-in HTTPS admin tab and supplied its sanitized report. `tools/d2_discovery.py --browser-script` prints it offline. It sends only the seven fixed source-evidenced GETs above to the same allowed router origin, using the existing Authorization value without copying credentials outside the tab. Redirects are rejected. No browser-storage or router-setting writes are requested.

The probe has a 20-second total deadline, a 256 KiB per-response limit, and `SIM_MANAGER_D2_PROBE.cancel()` cancellation. Its report masks identifiers including IMEI, IP/cell addresses/IDs, and APN; arbitrary operator/model/version strings are omitted while their types are retained. Only narrowly allowed status enums, bands, signals, and neutral PLMN strings may include values. Unknown values and raw error messages are omitted. Cookies, tokens, passwords, OTPs, and SMS contents must not be shared.

Offline JavaScript tests use `node --test tests/test_d2_browser_probe.js` without npm packages and remain separate from the Python standard-library suite. The supplied report is already sanitized; it is not raw network data or an exported browser session.

### Authenticated query ledger and observed shapes

T4-A01–A07 come from the user-supplied signed-in Brave probe report. Every entry returned HTTP 200, body `code=200`, `payload_type=object`, and `data_state=object`. Values below preserve reported strings without unit conversion or carrier interpretation.

| Evidence | Exact request | Observed data shape/allowed values | Classification and limit |
| --- | --- | --- | --- |
| T4-A01 | `GET /web/v1/dashboard/wirelessinfo` | Sanitized `fields={}`; object data confirmed. | VERIFIED successful response. No allowlisted field was exported; this does not prove empty raw data or missing capabilities. |
| T4-A02 | `GET /web/v1/dashboard/internetinfo` | `data.Status="Connected"`, `Band="1/28"`, `RSRP="-91"`, `RSRQ="-9"`, `SINR="22"`; `Operator` string omitted; `CellId`/`ECellId` strings masked. | VERIFIED paths/types and allowed raw values. Units, exact operator/cell identity, and band aggregation semantics unverified. |
| T4-A03 | `GET /web/v1/dashboard/waninfo` | `data.ConnectMethod="GSM"`; `ConnectMode` string omitted; `IpAddress`/`MacAddress`/`SubnetMask`/`DnsServer` strings masked. | VERIFIED field types/raw method label. Do not equate `GSM` with the observed LTE-mode label or infer PDP/address validity. |
| T4-A04 | `GET /web/v1/dashboard/deviceinfo` | `data.USIMStatus="Ready"`; `UICCID`/`IMSI`/`IMEI`/`SerialNumber`/`MacAddress` strings masked; `ProductModel`/`SoftwareVersion` strings omitted. | VERIFIED reported ready label and identifier field types, not identifier contents/validity. |
| T4-A05 | `GET /web/v1/status/wanstatus` | `data.ConnectionStatus`: `ConnectMode="LTE"`, `ConnectStatus="Connected"`, `USIMStatus="Ready"`, `Band="1/28"`, `RSRP0="-91"`, `RSRP1="-96"`, `RSRQ="-9"`, `RSSI="-82"`, `SINR="22"`; `PCI` string omitted; `CellId`/`IMEI`/`IMSI` strings masked. | VERIFIED nested response paths/types/allowed labels/signals. No registration, units, PCI decoding, or Internet-health inference. |
| T4-A06 | `GET /web/v1/setting/network/pinmanagement/simcardinfo` | `data.SIMCardState="READY"`, `PINCheckEnabled="OFF"`; `RetriesPIN` string omitted. | VERIFIED raw state/PIN-information labels and retry field type. No PIN mutation or numeric retry decoding. |
| T4-A07 | `GET /web/v1/setting/deviceinfo` | `data.MSISDN`/`IMEI`/`IMSI`/`SerialNumber`/`MacAddress`/`IpAddress`/`SubnetMask` strings masked; `ProductModel`/`HardwareVersion`/`SoftwareVersion`/`UBootVersion` strings omitted. | VERIFIED field presence/types only. Model/version values and modem firmware revision are not established. |

The report says `state_changes_requested=false`, matching the fixed GET-only script and source read paths. No setting-changing request was sent; firmware-internal side effects were not audited, so this does not claim that absolutely no internal counter/log changed.

```text
Common response summary: HTTP 200, code=200, data_state="object"
internet data: Status="Connected", Band="1/28", RSRP="-91", RSRQ="-9", SINR="22"
wanStatus data.ConnectionStatus: ConnectMode="LTE", ConnectStatus="Connected",
  USIMStatus="Ready", RSRP0="-91", RSRP1="-96", RSSI="-82"
sim data: SIMCardState="READY", PINCheckEnabled="OFF", RetriesPIN=<string omitted>
identifier shape: {type: "string", value: "masked"}
```

The mask replaces even an empty string. Consequently identifier/address field presence and type are VERIFIED, while non-empty content, validity, exact values, address family, and correspondence to the inserted SIM remain unverified. No raw identifiers, authentication material, or raw network responses are retained in the report.

### Current capability conclusions after Task 004

| Capability | Classification | Evidence and remaining limit |
| --- | --- | --- |
| SIM-ready/state labels | VERIFIED | T4-A04/A05 `Ready`, T4-A06 `READY`. SIM presence is INFERRED from these labels; no independent present/absent boolean or absent/PIN-locked SIM validation. |
| PIN-check label/retry field | VERIFIED | T4-A06 `OFF` and string `RetriesPIN` with omitted value. Meanings across firmware/state variations and retry number remain unverified. |
| ICCID/IMSI/MSISDN fields | VERIFIED field presence/types | T4-A04 `UICCID`/`IMSI`; T4-A07 `MSISDN`. Contents/non-empty state/validity unknown because masked. |
| Cellular connection/mode labels | VERIFIED | T4-A02/A05 `Connected`; T4-A05 `LTE`; T4-A03 separate `GSM` method label. No EPS registration, roaming, or Internet-health conclusion. |
| Operator field | VERIFIED string field | T4-A02; actual text omitted. No operator or carrier identity established. |
| PLMN/MCC/MNC | NOT FOUND in reviewed sanitized output | No neutral value exported; source search/config references are not runtime evidence. No carrier mapping implemented. |
| Band field | VERIFIED raw string | T4-A02/A05 `1/28`; no normalization, carrier aggregation, or primary/secondary-band assignment. |
| RSRP/RSRP0/RSRP1/RSRQ/RSSI/SINR | VERIFIED raw strings | T4-A02/A05 values above; units, scale/calibration, and antenna/path meanings unverified. |
| Cell ID/ECellId/PCI fields | VERIFIED field presence/types | Cell identifiers masked; PCI string omitted. Exact cell/PCI values and decoding unavailable. |
| APN/PDP family/registration/roaming | NOT FOUND in reviewed sanitized output | No validated field/value in this allowlisted report; omitted/unknown raw fields may exist. Hardware support is not ruled out. |
| WAN address/mask/DNS fields | VERIFIED string fields | T4-A03/A07; masks conceal contents including empty strings. Cellular address assignment, IP family, DNS provenance, and health unverified. |
| Modem firmware revision | UNTESTED / not established | Software/router-version references are not proof of modem firmware. Exact version strings omitted. |
| Model/hardware/software/bootloader fields | VERIFIED string fields | T4-A04/A07; actual values omitted. Task 003 USB model evidence remains independently verified. |

Task 004 is complete within its discovery scope: seven source-evidenced getters and sanitized authenticated shapes are established, with limitations explicit. At Task 004 completion, production detection/carrier logic and Task 005 were unstarted. The separately approved normalization work is recorded below.

### Development-summary privacy correction

Task 004 intentionally tightens earlier development summaries. Component-vocabulary matching could emit an arbitrary quoted credential if its value resembled an allowed dotted name, such as `home.wifi` or `network.get.info`. Selected source summaries and the status-name search now emit only the exact reviewed operation name `sms.get.inboxdata`; a separate strict source helper reports reviewed GET endpoints, asset paths, and property metadata without literal values. Two Task 003 development-summary test expectations were updated and a privacy regression added. Production code and all 78 original transport tests remain unchanged.

### Task 004 verification record

- Python 3.13.15 with `PYTHONPATH=src` and `python -S -B -m unittest discover -s tests -v`: **190 tests passed** in 0.974 seconds. Python tests require no browser packages or live hardware; all 78 original transport tests remain unchanged.
- `node --test tests/test_d2_browser_probe.js`: **36 tests passed** in 693.5684 ms. `node --check tools/d2_browser_probe.js` also passed. These are offline fake-browser tests using only Node built-ins, separate from the Python suite.
- `tests/fixtures/d2/authenticated-report.json` preserves the user's sanitized report with notes: seven successful GETs and 49 typed fields, with no seven-or-more-digit strings. Tests reconstructing hidden values use explicitly synthetic data; no raw authenticated payload or credential is stored.
- All 40 legacy file paths/SHA-256 hashes, production package files, both original transport test modules, and `pyproject.toml` match the Task 004 baseline. No hardware raw-capture flag was used or sensitive capture tracked.
- Git is on `main`, with no staged changes or Task 004 commit. Aggregate Task 003/004 status is six modified files and twelve untracked files; Task 004 relative to its starting snapshot changes eight files and adds nine files. Diff review and `git diff --check` pass; all twelve untracked files also pass read-only `git diff --no-index --check` against `NUL`. The normal Git index was not changed.

Source investigation, authenticated discovery, and offline verification are complete with the retained limits above. These Task 004 results are historical; Task 005 has separate implementation/verification records below. The foundation plan remains active for deferred work.

## Task 005 — normalized production device boundary

Task 005 completed immutable carrier-neutral models, D2 response normalization, and an authentication-isolated aggregate status client. No additional hardware query, operator-value disclosure, or firmware observation was needed. The raw evidence in T4-A01–A07 remains unchanged. Normalization is software representation, not new verification of units, identity, registration, or firmware variations.

`sim_manager.models` provides `SimState`, `NetworkState`, `RadioState`, `WanState`, `CarrierEvidence`, `DeviceIssue`, and `DeviceState`. Models are frozen and use closed status/issue enums with optional values. Repr/str omits all fields even if a caller accidentally passes private text into a wrongly typed argument. The D2 parser stores no full SIM/device identifiers, addresses, DNS, credentials, SMS, or OTP values. Availability can describe non-empty reported text without asserting validity; raw payloads must not be logged or retained alongside snapshots.

### Verified raw values, normalized representations, and unknown semantics

The parser accepts actual parsed JSON endpoint envelopes, not the browser probe's sanitized summary format. Offline observed-shape fixtures reconstruct the seven envelopes using the provided report's allowed strings/placeholders; any hidden values used for privacy tests are explicitly synthetic. A provided endpoint must contain integer `code=200` and object `data`; an invalid supplied envelope creates a fixed-source malformed-response issue. An absent endpoint is incomplete retrieval rather than a fabricated malformed response.

| Verified raw evidence | Normalized representation | INFERRED/UNKNOWN semantics retained |
| --- | --- | --- |
| T4-A06 `data.SIMCardState="READY"`; T4-A04/A05 `USIMStatus="Ready"` | `sim.readiness=READY`; canonical SIM-card state takes precedence, then dashboard device/WAN fallback when missing/null/empty. | `sim.present=None`, `pin_state=UNKNOWN`; absent/PIN-locked/PUK states not observed. A populated unfamiliar canonical state blocks fallback to a stale Ready label. |
| T4-A06 `PINCheckEnabled="OFF"` | `sim.pin_check_enabled=False`. | Other labels and retry string semantics unverified; no PIN operation. |
| T4-A04 `UICCID`/`IMSI`, T4-A07 `MSISDN` are masked strings | Identifier availability only; Task 004 masked placeholders normalize to `UNKNOWN`. | Exact value, non-empty state, validity, and SIM correspondence remain unknown. Actual non-empty reported text can become `AVAILABLE`; empty text `UNAVAILABLE`; neither stores the value. |
| T4-A05 `ConnectionStatus.ConnectMode="LTE"` | `network.connection_mode=LTE`. | No registration/roaming/5G/fallback interpretation; the separate T4-A03 `ConnectMethod="GSM"` label is not mapped. |
| T4-A05 `ConnectionStatus.ConnectStatus="Connected"`, T4-A02 `Status="Connected"` | `network.connection` and `wan.connection=CONNECTED`; canonical WAN status precedes Internet fallback when missing/null/empty. | Connected does not prove EPS registration or Internet health. A populated unfamiliar canonical state blocks stale fallback. Defensive `Disconnected` handling is not a newly observed hardware state. |
| T4-A02/A05 `Band="1/28"` | `radio.bands=(1, 28)`, preserving reported order. | No carrier aggregation, primary/secondary assignment, or supported-band claim. |
| T4-A05 `RSRP0="-91"`, `RSRP1="-96"`; T4-A02 `RSRP="-91"` | `radio.rsrp=-91.0`, `secondary_rsrp=-96.0`; valid WAN value before valid Internet fallback. | `units_verified=False`; no dBm claim, antenna assignment, calibration, or measurement validity. |
| T4-A02/A05 `RSRQ="-9"`, `SINR="22"`; T4-A05 `RSSI="-82"` | Optional finite numeric `rsrq=-9.0`, `sinr=22.0`, `rssi=-82.0`; individual invalid/missing values stay unknown. | No dB/dBm/scale assumption. Partial signal availability does not invalidate the radio state. |
| T4-A05 `PCI` is a string with value omitted | Optional `radio.pci`; the observed omitted placeholder stays `None`. | Defensive integer/numeric-string acceptance is parser behavior, not an observed PCI value or range interpretation. `earfcn=None` without a verified telemetry path. |
| T4-A03 `IpAddress` is a masked string | `wan.address_availability=UNKNOWN` for the fixture; actual non-empty/empty text may describe availability without retaining addresses. | IP family, cellular assignment, DNS provenance, APN, and PDP remain unknown/unset. |
| T4-A02 `Operator` string omitted; no PLMN/MCC/MNC exported | `network.operator=None`; empty `CarrierEvidence(operator=None, plmn=None, mcc=None, mnc=None)`. | Carrier identity remains UNKNOWN. No router-brand/model/MAC/SSID inference or DITO/Smart mapping. |

Band and signal values choose the first valid value per field from nested WAN status, then Internet where an evidenced counterpart exists. Numeric syntax/size bounds are defensive parser choices, not proven radio-domain ranges. Invalid/missing optional fields do not invalidate a successful endpoint. Unknown future fields and issue inputs outside the fixed source/closed-code set are ignored. `successful_sources` uses the fixed seven-source order. Snapshot `partial` describes retrieval completeness/errors, not whether every optional field is known; all seven successful envelopes may yield `partial=False` with carrier/units/identifiers still unknown. Default UTC observation time is local snapshot metadata, not a router measurement timestamp or freshness guarantee; fixed source metadata accompanies it.

### Authentication and aggregation limit

The production `D2StatusClient.get_device_state(timeout=20.0, stop_event=None)` exposes one snapshot over the same seven GET paths documented above. It accepts an explicitly injected `AuthenticatedStatusSession.read_json()` implementation returning an opaque `StatusResponse(http_status, payload)` within the device boundary; raw payloads are not returned to services/UI. Authentication remains isolated from parser/models and the future UI. No production Python bridge to the existing Brave tab has been implemented. With no session, the client returns an authentication-required unknown snapshot without opening sockets, browsers, or development probes. It accepts no credentials/Authorization/header parameter and stores no token.

An injected session is responsible for legitimate authentication, TLS verification, rejecting redirects, connection cleanup, and honoring the shared monotonic deadline, cooperative cancellation, and 256 KiB per-response contract. The client receives parsed JSON and forwards `max_bytes`; it cannot independently count raw HTTP bytes or enforce that cap. Tests verify contract forwarding, not a nonexistent HTTP implementation. The client cannot preempt arbitrary injected code that ignores that contract. Authentication failure stops further requests; cancellation/deadline expiry discards late responses while retaining earlier successful data. Other endpoint failures are isolated and reported through fixed source keys and closed issue codes, without raw exception messages, response bodies, or chains. Partial successful data remains usable. No further runtime/hardware compatibility claim follows from fake-session tests.

### Task 005 verification record

- Python 3.13.15, `PYTHONPATH=src`, `python -S -B -m unittest discover -s tests -v`: **260 tests passed**, zero failures/errors, in 1.888 seconds. This retains all 190 prior tests, including 78 SMS transport cases, and adds 31 parser/model plus 39 client cases.
- `node --test tests/test_d2_browser_probe.js`: **36 tests passed** in 688.2856 ms. `node --check tools/d2_browser_probe.js` also passed. No development-browser tool/test/fixture changes were needed.
- Fake sessions and sanitized/synthetic values cover observed mappings, field/envelope failures, canonical-state precedence, optional unknowns, availability, opaque repr/logging, unknown carrier evidence, no-session inertness, shared deadlines/cancellation/late-response handling, authentication stops, and the forwarded byte-limit contract. Tests do not implement/enforce a raw HTTP body limit or establish new hardware behavior.
- Five files were added: `src/sim_manager/models.py`, `src/sim_manager/devices/d2/status_parser.py`, `src/sim_manager/devices/d2/status.py`, `tests/test_d2_status_parser.py`, and `tests/test_d2_status_client.py`. Six documentation files were updated: `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/WORKFLOW.md`, this report, and the active foundation plan.
- All 40 legacy paths/SHA-256 hashes and 19 pre-existing non-document project files match the Task 005 baseline, including the SMS transport/original tests, development tools/tests/fixtures, package initializers/metadata, and ignore rules. No new router/browser access or setting-changing operation occurred. No `artifacts/d2-private/` directory or tracked capture exists, and its ignore rule is effective.
- All five new Python files parse successfully. Code/test privacy review found no real identifier or credential values; long digit test inputs are reviewed synthetic malformed-PCI vectors. Model/response/client repr and logs remain opaque in tests. `git diff --check` passes, and each of the five untracked files passes read-only `git diff --no-index --check` against `NUL`.
- Git is on `main` with six modified documentation files and five untracked source/test files. The normal index remains unstaged; no Task 005 commit was created. Historical Task 004 Git counts above describe its earlier verification point, not the current tree.

Task 005 is complete within its approved device-boundary scope with authentication and semantic limits explicit. No carrier mapping, GUI/storage/account integration, or Task 006 work was implemented. The foundation plan remains active for deferred work.

## Task 006 — presentation of existing normalized evidence

Task 006 implemented the first native Windows PySide6 shell over services derived from the existing `DeviceState`. It adds no router/modem query, raw operator value, browser authentication bridge, or hardware evidence. All Task 003–005 observations and semantic limits above remain unchanged. A presentation model converts only known enums and bounded numeric/availability fields into safe display text; carrier remains Unknown and unverified signal units remain unlabeled.

Default production mode has no authenticated D2 session and must display authentication-required unknown state without router/browser I/O. Explicit `--demo` derives offline state from the sanitized Task 004 report and keeps DEMO visible; fixture fields are not presented as live observations. Messages remains a shell until a neutral SMS model/service exists. Settings is read-only, with no credential/configuration storage or router-state change. Task 006 adds no live telemetry compatibility claim and no Task 007 work.

Task 006's final suites passed 285 standard-library backend/service tests (260 prior plus 25 new), 30 separate GUI tests, and 36 Node tests on Python 3.13.15 and PySide6/Qt 6.11.2. Native Windows production/demo rendering, refresh, and closure passed with no remaining refresh workers. Installed production/demo commands also launched outside the repository with no `PYTHONPATH`, exited cleanly, and produced no stdout/stderr. Editable and wheel builds passed; the packaged demo resource exactly matches the sanitized Task 004 fixture, with tests/legacy code excluded from the wheel. These software checks do not establish new hardware/authentication/firmware facts.

All 40 legacy paths/SHA-256 hashes and 27 pre-existing project files outside approved documentation/metadata edits remain unchanged. The six docs and `pyproject.toml` are modified; eighteen new files comprise 17 Python modules/tests and one sanitized JSON resource. AST/TOML syntax, privacy, and tracked/untracked diff/whitespace checks passed. Git is on `main` with seven modified/eighteen untracked files, an unstaged index, and no Task 006 commit. No private captures, credentials, identifiers, hardware/browser access, or router-setting changes were introduced. Generated environment/build/distribution metadata is ignored. Historical verification totals above remain scoped to their recorded tasks. Task 006 is complete as a visual milestone; Task 007 is unstarted and the foundation plan stays active for deferred work.

## Development probe and privacy boundary

`tools/d2_discovery.py` is manually invoked and excluded from application startup. It reuses the existing transport's private helpers only in this development tool; no production arbitrary-shell-command interface is added. Its fixed query allowlist prevents executing unknown commands. CLI/schema discovery alone never authorizes invoking a vendor method.

The probe uses an 8-second query deadline by default, a 256 KiB raw-wire cap per read phase, and a Ctrl+C cooperative cancellation event. Hosts must be literal IP addresses. Normal output includes only reviewed metadata and summaries; unknown values and raw errors are omitted. Full phone numbers/MSISDNs, IMSIs, ICCIDs, OTPs, sensitive SMS bodies, authentication cookies, tokens, and passwords must never appear in normal logs or exception output.

Optional raw output requires the explicit `--capture-raw` flag and is written only beneath the ignored `artifacts/d2-private/` directory. It must never be committed or reproduced in this report. The flag has not been used in the observations above.

The E18 binding query assumes at most one default route per address family, matching E13/E17 on this router. Multiple defaults produce a multiline comparison value and may leave every binding flag false for that family. Such a negative result would be inconclusive; extend the development query and its tests before applying it to that topology. No production routing model is derived from this probe.

## Recommended future abstractions and validation

Keep device identity, SIM state/identity, cellular registration/operator, radio measurements, WAN connectivity, and modem identity as separate neutral results. Preserve observed labels and explicit unknown units/semantics until their interpretation is verified. Task 005 established the production model/parser boundary described above; expanded hardware validation remains separate future work.

Future work must continue establishing firmware evidence before new queries and preserve paths/types, masked shapes, units, missing fields, and firmware assumptions. Task 004 located the separate Vue application's seven GET requests and received sanitized authenticated shapes. Units, unknown/omitted fields, SIM-state variations, registration/roaming, modem revision, and other firmware versions need separately scoped validation. A term occurrence alone never permits execution. Do not guess AT commands or UBus strings, or switch state/configuration under this observational scope.

## Task 003 verification record

Verified on Python 3.13.15 from `sim-manager/` with `PYTHONPATH=src`:

- `python -S -B -m unittest discover -s tests -v`: **139 tests passed** in 1.014 seconds, with zero failures/errors. The original 78 transport tests remain unchanged; 61 discovery tests cover synthetic framing/socket phases, deadlines/cancellation/cleanup, query restrictions, privacy summaries, USB/network parsing, capture confinement, and manual CLI behavior. No live connection occurs in the offline suite.
- All 18 fixed hardware query types were manually executed. The final address-summary recheck is included in E11 above. No vendor command, SMS query/read/send/delete, AT command, router configuration write, service restart, mobile-data reconnect, or reboot was issued.
- All 40 legacy file paths and SHA-256 hashes match the Task 003 baseline. Production package files, existing transport tests, and package metadata remain unchanged.
- `git diff --check` passes, including the three new files reviewed through a temporary index. The normal index remains unstaged. On `main`, Task 003 has six modified files and three new files; no Task 003 commit was created.
- No hardware raw-capture flag was used, no hardware captures were retained, and no files under `artifacts/d2-private/` are tracked. The explicit ignore rule is effective; capture tests use temporary synthetic data only.

The Task 003 observational task is complete with its original unresolved fields recorded explicitly. Its 139-test result is historical; Task 004's later authenticated observations and final verification record are separate above. Task 005 was unstarted at that historical verification point and now has its own section.

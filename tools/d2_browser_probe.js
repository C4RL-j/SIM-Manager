/* Manual development probe for the already signed-in D2 admin tab.
 * Paste this entire file in that tab's DevTools Console. Only the fixed GETs
 * below are sent. Credentials stay in the browser; output is privacy-filtered.
 * Run SIM_MANAGER_D2_PROBE.cancel() to stop. No localStorage values are changed.
 */
(function () {
  "use strict";
  const READS = Object.freeze({
    wireless: "/web/v1/dashboard/wirelessinfo",
    internet: "/web/v1/dashboard/internetinfo",
    wan: "/web/v1/dashboard/waninfo",
    device: "/web/v1/dashboard/deviceinfo",
    wanStatus: "/web/v1/status/wanstatus",
    sim: "/web/v1/setting/network/pinmanagement/simcardinfo",
    deviceDetails: "/web/v1/setting/deviceinfo"
  });
  const IDENTIFIERS = new Set([
    "UICCID", "ICCID", "IMSI", "MSISDN", "IMEI", "SerialNumber", "MacAddress",
    "IpAddress", "IPv4Address", "IPv6Address", "DnsServer", "DNSServers",
    "SubnetMask", "CellId", "ECellId", "APN", "Apn"
  ]);
  const SIGNALS = new Set(["RSRP", "RSRP0", "RSRP1", "RSRQ", "RSSI", "SINR"]);
  const TEXT_FIELDS = new Set([
    "Operator", "Status", "USIMStatus", "SIMCardState", "PINCheckEnabled",
    "NetworkType", "RAT", "Roaming", "Registration", "ConnectMethod",
    "ConnectMode", "ConnectStatus", "PDPType", "IPType", "Band",
    "DeviceModel", "ProductModel", "HardwareVersion", "SoftwareVersion",
    "RouterVersion", "ModemVersion", "FirmwareVersion", "UBootVersion"
  ]);
  // Arbitrary operator/model/version text can contain identifiers or secrets.
  // Retain its type only. Status values leave the tab only if on this list;
  // their meaning/units are deliberately not normalized by this dev probe.
  const ENUM_FIELDS = new Set([
    "Status", "USIMStatus", "SIMCardState", "PINCheckEnabled", "NetworkType",
    "RAT", "Roaming", "Registration", "ConnectMethod", "ConnectMode",
    "ConnectStatus", "PDPType", "IPType"
  ]);
  const ENUM_VALUES = new Set([
    "ready", "not ready", "present", "absent", "unknown", "invalid", "error",
    "pin", "puk", "pin required", "puk required", "sim pin", "sim puk",
    "connected", "disconnected", "connecting", "registered", "unregistered",
    "searching", "denied", "home", "roaming", "enabled", "disabled",
    "enable", "disable", "on", "off", "yes", "no", "true", "false",
    "auto", "automatic", "manual", "lte", "lte only", "4g", "3g", "2g",
    "wcdma", "gsm", "nr", "5g", "ipv4", "ipv6", "ipv4v6", "ip"
  ]);
  const NUMBERS = new Set(["RetriesPIN", "PCI", "EARFCN"]);
  const PLMNS = new Set(["PLMN", "MCC", "MNC", "HomePlmnId"]);
  const CONTAINERS = new Set(["data", "Internet", "ConnectionStatus", "Items"]);
  const MAX_BYTES = 256 * 1024;
  const MAX_NODES = 256;

  function type(value) {
    return value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
  }

  function fieldValue(key, value) {
    const state = {type: type(value)};
    if (value === null) return state;
    if (IDENTIFIERS.has(key)) {
      state.value = "masked";
      return state;
    }
    if (SIGNALS.has(key)) {
      if (typeof value === "number" && Number.isFinite(value) && Math.abs(value) < 1000) {
        state.value = value;
      } else if (typeof value === "string" && /^[+-]?\d{1,3}(?:\.\d{1,3})?(?:\s*dBm?)?$/.test(value)) {
        state.value = value;
      }
    } else if (PLMNS.has(key)) {
      // Preserve digit strings/leading zeros; never derive a carrier or split.
      if (typeof value === "string" && /^\d{2,6}$/.test(value)) state.value = value;
    } else if (NUMBERS.has(key)) {
      if (typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 262143) state.value = value;
    } else if (ENUM_FIELDS.has(key)) {
      if (typeof value === "boolean") state.value = value;
      else if (typeof value === "number" && Number.isInteger(value) && Math.abs(value) < 100) state.value = value;
      else if (typeof value === "string" && ENUM_VALUES.has(value.toLowerCase())) state.value = value;
    } else if (key === "Band") {
      if (typeof value === "number" && Number.isInteger(value) && value >= 0 && value < 1000) state.value = value;
      else if (typeof value === "string" && /^(?:B?\d{1,3})(?:[+,/]B?\d{1,3}){0,4}$/i.test(value)) state.value = value;
    }
    if (!Object.hasOwn(state, "value")) state.value = "omitted";
    return state;
  }

  function summarize(payload) {
    const result = {payload_type: type(payload), fields: {}, other_values: "omitted"};
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) return result;
    if (typeof payload.code === "number" && Number.isInteger(payload.code) && payload.code >= 100 && payload.code <= 599) result.code = payload.code;
    result.data_state = Object.hasOwn(payload, "data") ? type(payload.data) : "missing";
    // Error messages/payloads can contain credentials. Never inspect their data.
    if (result.code !== 200 || result.data_state !== "object") return result;
    let nodes = 0;
    function visit(value, path, depth) {
      if (++nodes > MAX_NODES || depth > 4 || !value || typeof value !== "object") return;
      if (Array.isArray(value)) {
        value.slice(0, 8).forEach((item, index) => visit(item, path + "[" + index + "]", depth + 1));
        return;
      }
      for (const [key, child] of Object.entries(value)) {
        const name = path ? path + "." + key : key;
        if (IDENTIFIERS.has(key) || SIGNALS.has(key) || TEXT_FIELDS.has(key) || NUMBERS.has(key) || PLMNS.has(key)) result.fields[name] = fieldValue(key, child);
        else if (CONTAINERS.has(key)) visit(child, name, depth + 1);
      }
    }
    visit(payload.data, "data", 0);
    return result;
  }

  async function readText(response, signal) {
    if (!response.body) throw new Error("unavailable_body");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let size = 0;
    let text = "";
    try {
      while (true) {
        if (signal.aborted) throw new Error("cancelled");
        const chunk = await reader.read();
        if (chunk.done) break;
        size += chunk.value.byteLength;
        if (size > MAX_BYTES) throw new Error("response_limit");
        text += decoder.decode(chunk.value, {stream: true});
      }
      return text + decoder.decode();
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  }

  async function run(environment) {
    const {origin, storage, fetch: request, controller} = environment;
    // An explicit local-router origin prevents credentials leaving that tab.
    if (!["https://192.168.1.1", "https://smartbrosettings.net"].includes(origin)) throw new Error("wrong_origin");
    let authorization;
    try {
      authorization = storage.getItem("Authorization");
    } catch (_) {
      throw new Error("sign_in_unavailable");
    }
    if (typeof authorization !== "string" || !authorization) throw new Error("sign_in_required");
    const report = {probe: "SIM Manager D2 Task 004", requests: [], state_changes_requested: false};
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      for (const [query, path] of Object.entries(READS)) {
        if (controller.signal.aborted) break;
        const record = {query, method: "GET", path};
        report.requests.push(record);
        try {
          const response = await request(origin + path, {
            method: "GET", mode: "same-origin", credentials: "same-origin",
            redirect: "error", cache: "no-store", signal: controller.signal,
            headers: {Authorization: authorization, Accept: "application/json"}
          });
          record.http_status = response.status;
          if (response.status !== 200 && response.body) {
            await response.body.cancel().catch(() => {});
          }
          if (response.status === 401 || response.status === 403) {
            record.result = "authentication_required";
            break;
          }
          if (response.status !== 200) {
            record.result = "http_error";
            continue;
          }
          const payload = JSON.parse(await readText(response, controller.signal));
          record.summary = summarize(payload);
          if (record.summary.code === 401 || record.summary.code === 403) {
            record.result = "authentication_required";
            break;
          }
        } catch (_) {
          record.result = controller.signal.aborted ? "cancelled_or_deadline" : "response_unavailable";
          if (controller.signal.aborted) break;
        }
      }
    } finally {
      clearTimeout(timer);
      controller.abort();
    }
    return report;
  }

  if (typeof module === "object" && module.exports) {
    module.exports = {READS, summarize, run, readText};
  } else {
    const controller = new AbortController();
    globalThis.SIM_MANAGER_D2_PROBE = Object.freeze({cancel: () => controller.abort()});
    run({origin: location.origin, storage: localStorage, fetch, controller})
      .then(report => console.log(JSON.stringify(report, null, 2)))
      .catch(() => console.log("D2 probe unavailable: use the signed-in local router HTTPS tab. No credentials printed."));
  }
})();

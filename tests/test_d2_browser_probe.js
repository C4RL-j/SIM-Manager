"use strict";

// Native Node tests use synthetic streams, sessions, fetch and abort signals.
// The authenticated fixture records user-collected sanitized browser summaries.
// Reconstructed concealed raw values are synthetic, never raw hardware captures.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "../tools/d2_browser_probe.js"), "utf8");
const PRIVATE = "SYNTHETIC_PRIVATE_TOKEN";
const ORIGIN = "https://192.168.1.1";
const EXPECTED_PATHS = [
  "/web/v1/dashboard/wirelessinfo", "/web/v1/dashboard/internetinfo",
  "/web/v1/dashboard/waninfo", "/web/v1/dashboard/deviceinfo",
  "/web/v1/status/wanstatus", "/web/v1/setting/network/pinmanagement/simcardinfo",
  "/web/v1/setting/deviceinfo"
];
const plain = value => JSON.parse(JSON.stringify(value));
const authenticatedFixture = JSON.parse(fs.readFileSync(
  path.join(__dirname, "fixtures/d2/authenticated-report.json"), "utf8"
));

class FakeController {
  constructor() {
    this.signal = {aborted: false};
    this.abortCalls = 0;
  }
  abort() {
    this.signal.aborted = true;
    this.abortCalls += 1;
  }
}

function loadProbe() {
  const timers = [];
  const cleared = [];
  const context = {
    module: {exports: {}}, TextDecoder,
    setTimeout(callback, delay) {
      const timer = {callback, delay};
      timers.push(timer);
      return timer;
    },
    clearTimeout(timer) { cleared.push(timer); },
    fetch() { throw new Error("Real fetch forbidden"); },
    console: {log() { throw new Error("Import must not log"); }},
    AbortController: FakeController
  };
  for (const key of ["location", "localStorage"]) {
    Object.defineProperty(context, key, {get() { throw new Error("Import must be inert"); }});
  }
  vm.runInNewContext(source, context, {filename: "d2_browser_probe.js"});
  return {probe: context.module.exports, timers, cleared, context};
}

function streamResponse(payload, status = 200, options = {}) {
  const state = {reads: 0, readerCancels: 0, bodyCancels: 0, releases: 0, readers: 0};
  const chunks = options.chunks || [Buffer.from(JSON.stringify(payload))];
  const reader = {
    async read() {
      state.reads += 1;
      if (options.readError) throw options.readError;
      if (options.onRead) options.onRead(state.reads);
      return chunks.length ? {done: false, value: chunks.shift()} : {done: true};
    },
    async cancel() {
      state.readerCancels += 1;
      if (options.cancelError) throw options.cancelError;
    },
    releaseLock() { state.releases += 1; }
  };
  const response = {status, body: {
    getReader() { state.readers += 1; return reader; },
    async cancel() {
      state.bodyCancels += 1;
      if (options.cancelError) throw options.cancelError;
    }
  }};
  return {response, state};
}

function environment(controller = new FakeController()) {
  const calls = [];
  const storageReads = [];
  const responses = [];
  const env = {
    origin: ORIGIN, controller,
    storage: {getItem(key) { storageReads.push(key); return PRIVATE; }},
    async fetch(url, options) {
      calls.push({url, options});
      const item = streamResponse({code: 200, data: {}});
      responses.push(item);
      return item.response;
    }
  };
  return {env, calls, storageReads, responses};
}

function assertPrivateOmitted(report, ...values) {
  const serialized = JSON.stringify(report);
  for (const value of [PRIVATE, ...values]) assert.ok(!serialized.includes(value), "Private value leaked");
}

test("module import is inert and exposes exactly the fixed reviewed GET paths", () => {
  const {probe, timers, context} = loadProbe();
  assert.deepEqual(Object.values(probe.READS), EXPECTED_PATHS);
  assert.ok(Object.isFrozen(probe.READS));
  assert.equal(timers.length, 0);
  assert.equal(context.SIM_MANAGER_D2_PROBE, undefined);
});

test("all seven requests are same-origin fixed GETs with private session headers", async () => {
  const {probe, timers, cleared} = loadProbe();
  const {env, calls, storageReads, responses} = environment();
  const report = await probe.run(env);
  assert.deepEqual(calls.map(call => call.url), EXPECTED_PATHS.map(item => ORIGIN + item));
  assert.deepEqual(storageReads, ["Authorization"]);
  for (const {options} of calls) {
    assert.equal(options.method, "GET");
    assert.equal(options.mode, "same-origin");
    assert.equal(options.credentials, "same-origin");
    assert.equal(options.redirect, "error");
    assert.equal(options.cache, "no-store");
    assert.equal(options.signal, env.controller.signal);
    assert.equal(options.headers.Authorization, PRIVATE);
    assert.equal(options.headers.Accept, "application/json");
    assert.equal(options.body, undefined);
  }
  assertPrivateOmitted(report);
  assert.equal(report.state_changes_requested, false);
  assert.equal(timers.length, 1);
  assert.equal(timers[0].delay, 20000);
  assert.deepEqual(cleared, timers);
  assert.ok(responses.every(item => item.state.readerCancels === 1 && item.state.releases === 1));
  assert.ok(env.controller.signal.aborted, "Run must close remaining activity");
});

test("wrong origin fails before storage or fetch access", async () => {
  const {probe, timers} = loadProbe();
  for (const origin of ["http://192.168.1.1", "https://evil.example", "https://192.168.1.1.evil.example"]) {
    const env = {
      origin, controller: new FakeController(),
      storage: {getItem() { assert.fail("Storage read forbidden"); }},
      fetch() { assert.fail("Fetch forbidden"); }
    };
    await assert.rejects(probe.run(env), /wrong_origin/);
  }
  assert.equal(timers.length, 0);
});

test("missing authentication fails before requests and timer creation", async () => {
  const {probe, timers} = loadProbe();
  for (const value of [null, undefined, "", 1, {}]) {
    const env = {origin: ORIGIN, controller: new FakeController(),
      storage: {getItem() { return value; }}, fetch() { assert.fail("Fetch forbidden"); }};
    await assert.rejects(probe.run(env), /sign_in_required/);
  }
  assert.equal(timers.length, 0);
});

test("storage exceptions are sanitized before leaving the run API", async () => {
  const {probe} = loadProbe();
  const env = {origin: ORIGIN, controller: new FakeController(),
    storage: {getItem() { throw new Error(PRIVATE); }}, fetch() { assert.fail("Fetch forbidden"); }};
  await assert.rejects(probe.run(env), error => !String(error).includes(PRIVATE));
});

test("HTTP authentication errors stop immediately and cancel unread bodies", async () => {
  for (const status of [401, 403]) {
    const {probe, cleared} = loadProbe();
    const {env} = environment();
    const item = streamResponse({code: 200, data: {ICCID: PRIVATE}}, status);
    let calls = 0;
    env.fetch = async () => { calls += 1; return item.response; };
    const report = await probe.run(env);
    assert.equal(calls, 1);
    assert.equal(report.requests[0].result, "authentication_required");
    assert.equal(item.state.readers, 0);
    assert.equal(item.state.bodyCancels, 1);
    assert.equal(cleared.length, 1);
    assertPrivateOmitted(report);
  }
});

test("non-200 responses cancel unread bodies instead of reading unbounded errors", async () => {
  const {probe} = loadProbe();
  const {env} = environment();
  const items = [];
  env.fetch = async () => {
    const item = streamResponse(null, 500, {chunks: [Buffer.alloc(1024 * 1024)]});
    items.push(item);
    return item.response;
  };
  const report = await probe.run(env);
  assert.equal(items.length, 7);
  assert.ok(items.every(item => item.state.bodyCancels === 1 && item.state.readers === 0));
  assert.ok(report.requests.every(record => record.result === "http_error"));
  assertPrivateOmitted(report);
});

test("authentication codes inside an HTTP 200 envelope stop later queries", async () => {
  for (const code of [401, 403]) {
    const {probe} = loadProbe();
    const {env} = environment();
    const item = streamResponse({code, msg: PRIVATE, data: {IMSI: PRIVATE}});
    let calls = 0;
    env.fetch = async () => { calls += 1; return item.response; };
    const report = await probe.run(env);
    assert.equal(calls, 1);
    assert.equal(report.requests[0].result, "authentication_required");
    assert.equal(item.state.readerCancels, 1);
    assert.equal(item.state.releases, 1);
    assertPrivateOmitted(report);
  }
});

test("malformed and partial JSON produce generic unavailable results", async () => {
  for (const text of ["not json " + PRIVATE, '{"code":200,"data":', ""]) {
    const {probe} = loadProbe();
    const {env} = environment();
    const items = [];
    env.fetch = async () => {
      const item = streamResponse(null, 200, {chunks: [Buffer.from(text)]});
      items.push(item);
      return item.response;
    };
    const report = await probe.run(env);
    assert.ok(report.requests.every(record => record.result === "response_unavailable"));
    assert.ok(items.every(item => item.state.readerCancels === 1 && item.state.releases === 1));
    assertPrivateOmitted(report);
  }
});

test("fetch and stream exceptions do not disclose raw private error text", async () => {
  const {probe} = loadProbe();
  const {env} = environment();
  env.fetch = async () => { throw new Error(PRIVATE); };
  const fetchReport = await probe.run(env);
  assert.ok(fetchReport.requests.every(item => item.result === "response_unavailable"));
  assertPrivateOmitted(fetchReport);
  env.controller = new FakeController();
  env.fetch = async () => streamResponse(null, 200, {readError: new Error(PRIVATE), cancelError: new Error(PRIVATE)}).response;
  assertPrivateOmitted(await probe.run(env));
});

test("deadline abortion stops the sequence and clears its timer", async () => {
  const {probe, timers, cleared} = loadProbe();
  const {env} = environment();
  let calls = 0;
  env.fetch = async () => {
    calls += 1;
    timers[0].callback();
    throw new Error(PRIVATE);
  };
  const report = await probe.run(env);
  assert.equal(calls, 1);
  assert.equal(report.requests[0].result, "cancelled_or_deadline");
  assert.deepEqual(cleared, timers);
  assertPrivateOmitted(report);
});

test("pre-cancelled run sends no requests", async () => {
  const {probe} = loadProbe();
  const controller = new FakeController();
  controller.abort();
  const {env, calls} = environment(controller);
  const report = await probe.run(env);
  assert.equal(calls.length, 0);
  assert.equal(report.requests.length, 0);
});

test("stream byte cap cancels and releases without returning oversized text", async () => {
  const {probe} = loadProbe();
  const controller = new FakeController();
  const item = streamResponse(null, 200, {chunks: [Buffer.alloc(256 * 1024), Buffer.from("x")]});
  await assert.rejects(probe.readText(item.response, controller.signal));
  assert.equal(item.state.readerCancels, 1);
  assert.equal(item.state.releases, 1);
});

test("stream boundary and fragmented UTF-8 preserve complete text", async () => {
  const {probe} = loadProbe();
  const controller = new FakeController();
  const bytes = Buffer.from("synthetic á text");
  const item = streamResponse(null, 200, {chunks: Array.from(bytes, byte => Buffer.from([byte]))});
  assert.equal(await probe.readText(item.response, controller.signal), "synthetic á text");
  const boundary = streamResponse(null, 200, {chunks: [Buffer.alloc(256 * 1024, 32)]});
  assert.equal((await probe.readText(boundary.response, controller.signal)).length, 256 * 1024);
});

test("cooperative cancellation during stream reading closes the reader", async () => {
  const {probe} = loadProbe();
  const controller = new FakeController();
  const item = streamResponse(null, 200, {chunks: [Buffer.from(PRIVATE)], onRead() { controller.abort(); }});
  await assert.rejects(probe.readText(item.response, controller.signal));
  assert.equal(item.state.readerCancels, 1);
  assert.equal(item.state.releases, 1);
});

test("missing body is unavailable and never becomes a fabricated summary", async () => {
  const {probe} = loadProbe();
  const {env} = environment();
  env.fetch = async () => ({status: 200, body: null});
  const report = await probe.run(env);
  assert.ok(report.requests.every(record => record.result === "response_unavailable"));
});

test("missing, null, unexpected and partial envelopes keep explicit shape states", () => {
  const {probe} = loadProbe();
  for (const payload of [null, [], PRIVATE, 7, false]) {
    const result = probe.summarize(payload);
    assert.deepEqual(plain(result.fields), {});
    assertPrivateOmitted(result);
  }
  for (const [payload, state] of [
    [{code: 200}, "missing"], [{code: 200, data: null}, "null"],
    [{code: 200, data: []}, "array"], [{code: 200, data: PRIVATE}, "string"],
    [{code: 200, data: {}}, "object"]
  ]) {
    const result = probe.summarize(payload);
    assert.equal(result.data_state, state);
    assert.deepEqual(plain(result.fields), {});
    assertPrivateOmitted(result);
  }
});

test("error and unexpected envelope codes never inspect nested telemetry or messages", () => {
  const {probe} = loadProbe();
  for (const code of [400, 401, 403, "200", null, {}, 99999]) {
    const result = probe.summarize({code, msg: PRIVATE, data: {RSRP: -105, ICCID: PRIVATE}});
    assert.deepEqual(plain(result.fields), {});
    assertPrivateOmitted(result);
  }
});

test("identifiers, address information, APN and cell identities are masked", () => {
  const {probe} = loadProbe();
  const data = {};
  for (const key of ["UICCID", "ICCID", "IMSI", "MSISDN", "IMEI", "SerialNumber", "MacAddress", "IpAddress", "IPv4Address", "IPv6Address", "DnsServer", "DNSServers", "SubnetMask", "CellId", "ECellId", "APN", "Apn"]) data[key] = PRIVATE;
  const result = probe.summarize({code: 200, data});
  assert.equal(Object.keys(result.fields).length, Object.keys(data).length);
  assert.ok(Object.values(result.fields).every(field => field.value === "masked"));
  assertPrivateOmitted(result);
});

test("only safe signal, PLMN, numeric and status forms are retained", () => {
  const {probe} = loadProbe();
  const result = probe.summarize({code: 200, data: {
    RSRP: -105, RSRQ: "-9.5 dB", SINR: 13.2, RSSI: "-75 dBm",
    PLMN: "51500", MCC: "515", MNC: "00", HomePlmnId: "00101",
    PCI: 123, EARFCN: 1800, RetriesPIN: 3, NetworkType: "LTE",
    USIMStatus: "READY", ConnectStatus: "Connected", PDPType: "IPV4V6"
  }});
  for (const [key, value] of Object.entries({RSRP: -105, RSRQ: "-9.5 dB", SINR: 13.2, RSSI: "-75 dBm", PLMN: "51500", MCC: "515", MNC: "00", HomePlmnId: "00101", PCI: 123, EARFCN: 1800, RetriesPIN: 3, NetworkType: "LTE", USIMStatus: "READY", ConnectStatus: "Connected", PDPType: "IPV4V6"})) {
    assert.equal(result.fields["data." + key].value, value);
  }
  assert.equal(result.carrier, undefined);
});

test("null and unexpected field types expose shape without interpreting values", () => {
  const {probe} = loadProbe();
  const result = probe.summarize({code: 200, data: {RSRP: null, SINR: {}, PLMN: 51500, NetworkType: []}});
  assert.deepEqual(plain(result.fields["data.RSRP"]), {type: "null"});
  assert.deepEqual(plain(result.fields["data.SINR"]), {type: "object", value: "omitted"});
  assert.deepEqual(plain(result.fields["data.PLMN"]), {type: "number", value: "omitted"});
  assert.deepEqual(plain(result.fields["data.NetworkType"]), {type: "array", value: "omitted"});
});

test("OTP and arbitrary token-like text is omitted from every text-field class", () => {
  const {probe} = loadProbe();
  for (const value of ["123456", "Abcdefghijklmnopqrstuvwxyz", PRIVATE]) {
    const result = probe.summarize({code: 200, data: {
      Operator: value, Status: value, NetworkType: value,
      DeviceModel: value, SoftwareVersion: value, FirmwareVersion: value
    }});
    assert.ok(Object.values(result.fields).every(field => field.value === "omitted"));
    assertPrivateOmitted(result, value);
  }
});

test("invalid numeric and signal values are omitted rather than guessed", () => {
  const {probe} = loadProbe();
  for (const value of [PRIVATE, "123456", NaN, Infinity, -Infinity, 1000, {}, []]) {
    const result = probe.summarize({code: 200, data: {RSRP: value}});
    assert.equal(result.fields["data.RSRP"].value, "omitted");
    assertPrivateOmitted(result);
  }
  for (const value of [-1, 0.5, 262144, "123", PRIVATE]) {
    const result = probe.summarize({code: 200, data: {PCI: value}});
    assert.equal(result.fields["data.PCI"].value, "omitted");
  }
});

test("unknown keys and nested credential containers never leave the summary", () => {
  const {probe} = loadProbe();
  const result = probe.summarize({code: 200, data: {
    [PRIVATE]: PRIVATE, cookie: PRIVATE, Authorization: PRIVATE,
    Other: {IMSI: PRIVATE}, Internet: {IMSI: PRIVATE, [PRIVATE]: PRIVATE}
  }});
  assert.deepEqual(Object.keys(result.fields), ["data.Internet.IMSI"]);
  assert.equal(result.fields["data.Internet.IMSI"].value, "masked");
  assertPrivateOmitted(result);
});

test("array and recursion limits retain only bounded reviewed paths", () => {
  const {probe} = loadProbe();
  const result = probe.summarize({code: 200, data: {Items: Array.from({length: 20}, () => ({RSRP: -105}))}});
  assert.equal(Object.keys(result.fields).length, 8);
  assert.equal(result.fields["data.Items[8].RSRP"], undefined);
  const nested = {RSRP: -105};
  let cursor = nested;
  for (let i = 0; i < 8; i += 1) { cursor.Internet = {RSRP: -106}; cursor = cursor.Internet; }
  const deep = probe.summarize({code: 200, data: nested});
  assert.equal(Object.keys(deep.fields).length, 5);
});

function browserHarness(origin = ORIGIN) {
  const controllerInstances = [];
  const logs = [];
  const requests = [];
  let complete;
  const completion = new Promise(resolve => { complete = resolve; });
  class BrowserController extends FakeController {
    constructor() { super(); controllerInstances.push(this); }
  }
  const context = {
    location: {origin}, localStorage: {getItem() { return PRIVATE; }},
    AbortController: BrowserController, TextDecoder,
    setTimeout() { return "synthetic-timer"; }, clearTimeout() {},
    async fetch(url, options) {
      requests.push({url, options});
      return streamResponse({code: 200, data: {ICCID: PRIVATE, RSRP: -105}}).response;
    },
    console: {log(value) { logs.push(value); complete(); }}
  };
  vm.runInNewContext(source, context, {filename: "d2_browser_probe.js"});
  return {context, controllerInstances, requests, logs, completion};
}

test("browser branch automatically prints only the sanitized report", async () => {
  const harness = browserHarness();
  await harness.completion;
  assert.equal(harness.requests.length, 7);
  assert.equal(harness.logs.length, 1);
  const report = JSON.parse(harness.logs[0]);
  assertPrivateOmitted(report);
  assert.equal(report.requests[0].summary.fields["data.ICCID"].value, "masked");
  assert.equal(report.requests[0].summary.fields["data.RSRP"].value, -105);
  assert.ok(Object.isFrozen(harness.context.SIM_MANAGER_D2_PROBE));
});

test("browser branch wrong-origin error is generic and sends no requests", async () => {
  const harness = browserHarness("https://evil.example");
  await harness.completion;
  assert.equal(harness.requests.length, 0);
  assert.deepEqual(harness.logs, ["D2 probe unavailable: use the signed-in local router HTTPS tab. No credentials printed."]);
  assertPrivateOmitted(harness.logs);
});

test("browser global cancellation aborts its controller and stops later reads", async () => {
  const harness = browserHarness();
  harness.context.SIM_MANAGER_D2_PROBE.cancel();
  await harness.completion;
  assert.equal(harness.requests.length, 1);
  assert.ok(harness.controllerInstances[0].signal.aborted);
  const report = JSON.parse(harness.logs[0]);
  assert.equal(report.requests[0].result, "cancelled_or_deadline");
  assertPrivateOmitted(report);
});

// The report records filtered field types/values, not raw HTTP payloads.
// Every concealed raw value below is synthetic, including numeric-looking text.
function reconstructSyntheticPayload(record) {
  const payload = {code: record.summary.code, msg: PRIVATE, data: {UnreviewedSyntheticField: PRIVATE}};
  for (const [fieldPath, field] of Object.entries(record.summary.fields)) {
    const parts = fieldPath.split(".");
    let target = payload;
    for (const part of parts.slice(0, -1)) {
      if (!Object.hasOwn(target, part)) target[part] = {};
      target = target[part];
    }
    let value;
    if (field.type === "null") value = null;
    else if (Object.hasOwn(field, "value") && !["masked", "omitted"].includes(field.value)) value = field.value;
    else if (field.type === "string") value = PRIVATE;
    else if (field.type === "number") value = 0;
    else if (field.type === "boolean") value = false;
    else if (field.type === "array") value = [PRIVATE];
    else if (field.type === "object") value = {synthetic: PRIVATE};
    else assert.fail("Unsupported observed fixture type");
    target[parts.at(-1)] = value;
  }
  return payload;
}

test("authenticated fixture contains seven user-reported filtered successes and explicit limitations", () => {
  const report = authenticatedFixture.report;
  assert.deepEqual(report.requests.map(record => record.path), EXPECTED_PATHS);
  assert.equal(report.state_changes_requested, false);
  assert.ok(report.requests.every(record => record.method === "GET" && record.http_status === 200
    && record.summary.code === 200 && record.summary.data_state === "object"));
  assert.equal(report.requests.reduce((count, record) => count + Object.keys(record.summary.fields).length, 0), 49);
  assert.ok(authenticatedFixture._fixture_notes.some(note => note.includes("not a raw HTTP response")));
  assertPrivateOmitted(report);
});

test("synthetic reconstruction matches every observed sanitized field path and type", () => {
  const {probe} = loadProbe();
  for (const record of authenticatedFixture.report.requests) {
    const payload = reconstructSyntheticPayload(record);
    const result = probe.summarize(payload);
    assert.deepEqual(plain(result), record.summary, record.query);
    assertPrivateOmitted(result);
  }
});

test("seven fake authenticated GETs reproduce the sanitized user report without state changes", async () => {
  const {probe} = loadProbe();
  const {env} = environment();
  const requests = [];
  const responses = [];
  env.fetch = async (url, options) => {
    const index = requests.length;
    requests.push({url, options});
    const record = authenticatedFixture.report.requests[index];
    assert.equal(url, ORIGIN + record.path);
    assert.equal(options.method, "GET");
    const response = streamResponse(reconstructSyntheticPayload(record), record.http_status);
    responses.push(response);
    return response.response;
  };
  const report = await probe.run(env);
  assert.deepEqual(plain(report), authenticatedFixture.report);
  assert.equal(requests.length, 7);
  assert.equal(report.state_changes_requested, false);
  assert.ok(responses.every(item => item.state.readerCancels === 1 && item.state.releases === 1));
  assertPrivateOmitted(report);
});

test("empty filtered wireless fields do not imply an empty raw data object", () => {
  const {probe} = loadProbe();
  const record = authenticatedFixture.report.requests.find(item => item.query === "wireless");
  const payload = reconstructSyntheticPayload(record);
  assert.ok(Object.keys(payload.data).length > 0);
  assert.deepEqual(record.summary.fields, {});
  assert.deepEqual(plain(probe.summarize(payload)), record.summary);
  assertPrivateOmitted(probe.summarize(payload));
});

test("observed PCI and RetriesPIN strings remain type-only rather than numeric interpretations", () => {
  const {probe} = loadProbe();
  const wanStatus = reconstructSyntheticPayload(authenticatedFixture.report.requests.find(item => item.query === "wanStatus"));
  const sim = reconstructSyntheticPayload(authenticatedFixture.report.requests.find(item => item.query === "sim"));
  wanStatus.data.ConnectionStatus.PCI = "123"; // Synthetic; the real string value was omitted.
  sim.data.RetriesPIN = "3"; // Synthetic; the real string value was omitted.
  assert.deepEqual(plain(probe.summarize(wanStatus).fields["data.ConnectionStatus.PCI"]), {type: "string", value: "omitted"});
  assert.deepEqual(plain(probe.summarize(sim).fields["data.RetriesPIN"]), {type: "string", value: "omitted"});
});

test("deviceDetails MSISDN and other identifiers remain masked even when raw strings are empty", () => {
  const {probe} = loadProbe();
  const record = authenticatedFixture.report.requests.find(item => item.query === "deviceDetails");
  assert.deepEqual(record.summary.fields["data.MSISDN"], {type: "string", value: "masked"});
  for (const raw of ["", "09900000001", PRIVATE]) {
    const payload = reconstructSyntheticPayload(record);
    for (const [fieldPath, field] of Object.entries(record.summary.fields)) {
      if (field.value === "masked") payload.data[fieldPath.split(".").at(-1)] = raw;
    }
    const result = probe.summarize(payload);
    assert.deepEqual(plain(result), record.summary);
    assertPrivateOmitted(result, "09900000001");
  }
});

test("null, missing and partial variations preserve observed shape semantics without fabricated values", () => {
  const {probe} = loadProbe();
  const record = authenticatedFixture.report.requests.find(item => item.query === "wanStatus");
  const payload = reconstructSyntheticPayload(record);
  payload.data.ConnectionStatus.RSRP0 = null;
  delete payload.data.ConnectionStatus.RSRQ;
  const result = probe.summarize(payload);
  assert.deepEqual(plain(result.fields["data.ConnectionStatus.RSRP0"]), {type: "null"});
  assert.equal(result.fields["data.ConnectionStatus.RSRQ"], undefined);
  assert.deepEqual(plain(result.fields["data.ConnectionStatus.RSRP1"]), record.summary.fields["data.ConnectionStatus.RSRP1"]);
  assertPrivateOmitted(result);
});

test("reported signal and band strings are retained without adding unverified units or mappings", () => {
  const {probe} = loadProbe();
  const record = authenticatedFixture.report.requests.find(item => item.query === "internet");
  const result = probe.summarize(reconstructSyntheticPayload(record));
  assert.deepEqual(plain(result.fields["data.RSRP"]), {type: "string", value: "-91"});
  assert.deepEqual(plain(result.fields["data.Band"]), {type: "string", value: "1/28"});
  assert.equal(result.fields["data.Operator"].value, "omitted");
  assert.equal(result.carrier, undefined);
  assert.equal(result.signal_units, undefined);
});

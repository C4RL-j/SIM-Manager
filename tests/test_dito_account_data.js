'use strict';
// Synthetic official-client results only; no account/network/credential capture.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../src/sim_manager/carriers/dito/account_data.js'), 'utf8');
const activeNumber = '09920000001';
const configPath = '/ecare/webs/common/configParam';
const summaryPath = '/ecare/webs/balance/balInfo/glSumInfo';
const detailPath = '/ecare/webs/balance/balInfo';
const subscriberPath = '/ecare/webs/subs/qrySubsDetail?prodInstIds=42';

function fixture() {
  const state = {
    auth: 'authenticated',
    subscriber: {prodInstId: 42, accNbr: '9920000001'},
    user: {subsId: 42},
    calls: [], privateAccess: [], consoleCalls: [], captureCount: 0,
    timers: new Map(), events: new Map(), aborts: 0,
  };
  const responses = new Map([
    [subscriberPath, {prodInstId: 42, accNbr: '9920000001'}],
    [configPath, {generalData: ['5000'], allNetSMS: ['6000'], offNetSMS: ['6001'],
      onNetSMS: ['6002'], allNetVoice: ['7000'], offNetVoice: ['7001'], onNetVoice: ['7002']}],
    [summaryPath, [
      {glId: 5000, acctResName: 'General data', formatRealBalance: '3.25', formatRealBalanceUnitName: 'GB'},
      {glId: 6000, acctResName: 'All networks', formatRealBalance: '12', formatRealBalanceUnitName: 'SMS'},
      {glId: 6002, acctResName: 'DITO texts', unlimitedFlag: 'Y'},
      {glId: 7001, acctResName: 'Other networks', formatRealBalance: '5', formatRealBalanceUnitName: 'mins'},
    ]],
    [detailPath, [
      {acctResId: 1, currencySymbol: '\u20b1', formatRealBalance: '0.00', expDate: '2026-12-31 23:59:59'},
      {acctResId: 101, acctResName: 'General data bucket', formatRealBalance: '2.00',
        formatRealBalanceUnitName: 'GB', expDate: '2026-10-30 23:59:59'},
      {acctResId: 102, acctResName: 'Bonus data bucket', formatRealBalance: '1,024.00',
        formatRealBalanceUnitName: 'MB', expDate: '2026-11-01 23:59:59'},
      {acctResId: 103, acctResName: 'Texts bucket', unlimitedFlag: 'Y'},
    ]],
  ]);
  let timerId = 0;
  const trap = label => function () { state.privateAccess.push(label); throw new Error('synthetic-private-value'); };
  const location = {origin: 'https://my.dito.ph', pathname: '/pto/home', search: '', hash: ''};
  const window = {location, __simManagerDitoAuthObserver: {poll: () => state.auth},
    addEventListener(name, callback) { state.events.set(name, callback); },
    fetch: trap('direct-fetch'),
  };
  window.top = window;
  Object.defineProperty(window, 'localStorage', {get: trap('storage')});
  Object.defineProperty(window, 'sessionStorage', {get: trap('session-storage')});
  Object.defineProperty(window, 'document', {get: trap('DOM')});
  const api = {
    '+n12': {I: () => state.subscriber, K: () => state.user},
    t3Un: {a(url, options) {
      state.calls.push({url, options});
      assert.equal(options.timeout, 8000);
      assert.equal(options.useCache, false);
      assert.equal(options.cache, 'no-store');
      assert.ok(['GET', 'POST'].includes(options.method));
      assert.ok(!Object.hasOwn(options, 'headers'));
      assert.ok(responses.has(url), 'Only the original reviewed read paths may be invoked');
      const response = responses.get(url);
      return typeof response === 'function' ? response(url, options) : Promise.resolve(response);
    }},
  };
  window.webpackJsonp = [];
  window.webpackJsonp.push = payload => {
    state.captureCount += 1;
    assert.deepEqual(Array.from(payload[0]), []);
    const loader = name => { assert.ok(Object.hasOwn(api, name)); return api[name]; };
    for (const entry of payload[2]) payload[1][entry[0]]({}, {}, loader);
  };
  class AbortController {
    constructor() { this.signal = {aborted: false}; }
    abort() { if (!this.signal.aborted) state.aborts += 1; this.signal.aborted = true; }
  }
  const context = vm.createContext({window, AbortController,
    setTimeout(callback, milliseconds) {
      assert.equal(milliseconds, 20000);
      state.timers.set(++timerId, callback);
      return timerId;
    },
    clearTimeout(id) { state.timers.delete(id); },
    console: new Proxy({}, {get: (_target, key) => (...values) => state.consoleCalls.push([key, ...values])}),
  });
  vm.runInContext(source, context);
  const helper = window.__simManagerDitoAccountData;
  const poll = request => JSON.parse(JSON.stringify(helper.poll(request)));
  return {state, responses, location, window, context, helper, poll};
}
async function settle() { await new Promise(resolve => setImmediate(resolve)); }
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

test('reuses original official getters, preserving types and values without invented sums or offers', async () => {
  const f = fixture();
  assert.ok(Object.isFrozen(f.helper));
  assert.equal(f.helper.start(1, activeNumber), true);
  assert.equal(f.poll(1).state, 'pending');
  assert.equal(f.helper.start(2, activeNumber), false, 'No overlapping reads');
  await settle();
  const result = f.poll(1);
  assert.equal(result.state, 'ok');
  assert.deepEqual(result.data, {
    load_balance: '\u20b1 0.00', data_remaining: '3.25 GB', active_promos: [],
    expiry: '2026-12-31 23:59:59', sms_allowance: 'All networks: 12 SMS; DITO texts: Unlimited',
    call_allowance: 'Other networks: 5 mins', data_buckets: [
      {name: 'General data bucket', remaining: '2.00 GB', expiry: '2026-10-30 23:59:59'},
      {name: 'Bonus data bucket', remaining: '1,024.00 MB', expiry: '2026-11-01 23:59:59'},
      {name: 'Texts bucket', remaining: 'Unlimited', expiry: null},
    ],
  });
  assert.deepEqual(f.state.calls.map(call => call.url), [configPath, summaryPath, detailPath]);
  for (const call of f.state.calls.slice(1)) assert.equal(call.options.data.prodInstId, 42);
  assert.equal(f.state.calls[0].options.data.configCode, 'webs.ecare.usageGL');
  assert.equal(f.state.captureCount, 1);
  assert.equal(f.state.timers.size, 0);
  f.responses.set(summaryPath, [
    {glId: 5000, acctResName: 'General data', formatRealBalance: '2.75', formatRealBalanceUnitName: 'GB'},
    {glId: 6000, acctResName: 'All networks', formatRealBalance: '9', formatRealBalanceUnitName: 'SMS'},
    {glId: 7001, acctResName: 'Other networks', formatRealBalance: '4', formatRealBalanceUnitName: 'mins'},
  ]);
  f.responses.set(detailPath, [
    {acctResId: 1, currencySymbol: '\u20b1', formatRealBalance: '17.50', expDate: '2027-01-31 23:59:59'},
    {acctResId: 101, acctResName: 'General data bucket', formatRealBalance: '1.75',
      formatRealBalanceUnitName: 'GB', expDate: '2026-11-30 23:59:59'},
    {acctResId: 102, acctResName: 'New reported resource', formatRealBalance: '900.00',
      formatRealBalanceUnitName: 'MB', expDate: '2026-12-01 23:59:59'},
  ]);
  assert.equal(f.helper.start(2, activeNumber), true);
  await settle();
  assert.deepEqual(f.poll(2), {request: 2, state: 'ok', data: {
    load_balance: '\u20b1 17.50', data_remaining: '2.75 GB', active_promos: [],
    expiry: '2027-01-31 23:59:59', sms_allowance: 'All networks: 9 SMS',
    call_allowance: 'Other networks: 4 mins', data_buckets: [
      {name: 'General data bucket', remaining: '1.75 GB', expiry: '2026-11-30 23:59:59'},
      {name: 'New reported resource', remaining: '900.00 MB', expiry: '2026-12-01 23:59:59'},
    ],
  }});
  assert.equal(result.data.load_balance, '\u20b1 0.00', 'The earlier snapshot is not mutated');
  assert.equal(f.state.calls.length, 6, 'Manual refresh performs fresh requests');
  assert.equal(f.state.captureCount, 1);
  assert.equal(f.helper.start(2, activeNumber), false, 'Completed request IDs cannot be reused');
});

test('requires observed authentication, exact origin/main frame/route and does not read before start', async () => {
  const f = fixture();
  await settle();
  assert.equal(f.state.calls.length, 0);
  for (const changes of [
    {auth: 'none'}, {auth: 'rejected'}, {auth: 'expired'},
  ]) {
    f.state.auth = changes.auth;
    assert.equal(f.helper.start(1, activeNumber), false);
  }
  f.state.auth = 'authenticated';
  for (const changes of [
    {origin: 'https://other.invalid'}, {pathname: '/'}, {search: '?account=synthetic'}, {hash: '#account'},
  ]) {
    const old = {...f.location}; Object.assign(f.location, changes);
    assert.equal(f.helper.start(1, activeNumber), false); Object.assign(f.location, old);
  }
  f.window.top = {}; assert.equal(f.helper.start(1, activeNumber), false);
  f.window.top = f.window;
  for (const request of [0, -1, 1.5, '1', Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(f.helper.start(request, activeNumber), false);
  }
  assert.equal(f.state.calls.length, 0);
  vm.runInContext(source, f.context);
  assert.equal(f.window.__simManagerDitoAccountData, f.helper, 'Duplicate insertion does not replace bridge');
});

test('compares canonical subscriber number in-page and keeps subscriber/session fields private', async () => {
  for (const number of ['09920000001', '9920000001', '639920000001', '+639920000001']) {
    const f = fixture();
    assert.equal(f.helper.start(1, number), true); await settle();
    assert.equal(f.poll(1).state, 'ok');
    assert.equal(JSON.stringify(f.poll(1)).includes(number), false);
  }
  for (const number of ['09920000002', '', '09920-000001', '6399200000010']) {
    const f = fixture();
    assert.equal(f.helper.start(1, number), true); await settle();
    assert.deepEqual(f.poll(1), {request: 1, state: 'account_mismatch', data: null});
    assert.equal(f.state.calls.length, 0);
  }
  const f = fixture();
  f.state.subscriber = {};
  Object.defineProperty(f.state.user, 'token', {get() { throw new Error('private-token-access'); }});
  f.helper.start(1, activeNumber); await settle();
  assert.equal(f.poll(1).state, 'ok');
  assert.equal(f.state.calls[0].url, subscriberPath);
  assert.equal(f.state.calls[0].options.method, 'GET');
  assert.deepEqual(f.state.privateAccess, []);
  assert.equal(JSON.stringify(f.poll(1)).includes('prodInstId'), false);
  assert.equal(JSON.stringify(f.poll(1)).includes('accNbr'), false);
});

test('rejects changed subscriber/product context and unsupported subscriber getters without leaking results', async () => {
  const f = fixture(); const pending = deferred();
  f.responses.set(configPath, () => pending.promise);
  f.helper.start(1, activeNumber); await settle();
  f.state.subscriber = {prodInstId: 43, accNbr: '9920000001'};
  pending.resolve({generalData: [5000]}); await settle();
  assert.deepEqual(f.poll(1), {request: 1, state: 'account_mismatch', data: null});
  assert.equal(f.state.calls.length, 1);
  for (const subscriber of [{}, {prodInstId: 42}, {prodInstId: 42, accNbr: '9920000002'}]) {
    const g = fixture(); g.state.subscriber = subscriber; g.state.user = {};
    g.helper.start(1, activeNumber); await settle();
    assert.equal(g.poll(1).state, 'account_mismatch');
    assert.equal(g.state.calls.length, 0);
  }
  const g = fixture(); g.window.webpackJsonp = null;
  g.helper.start(1, activeNumber); await settle();
  assert.equal(g.poll(1).state, 'unsupported'); assert.equal(g.state.calls.length, 0);
});

test('temporary failures, source security failures and returned login route have closed outcomes', async () => {
  const cases = [
    [() => Promise.reject(new Error('private-account-capture')), 'unavailable'],
    [false, 'unavailable'],
    [{code: 'SERVER-TEMPORARY', message: 'private-account-capture'}, 'unavailable'],
    [{code: 'PORTAL-SECURITY-0001', message: 'private-account-capture'}, 'expired'],
  ];
  for (const [response, outcome] of cases) {
    const f = fixture(); f.responses.set(configPath, response);
    f.helper.start(1, activeNumber); await settle();
    assert.deepEqual(f.poll(1), {request: 1, state: outcome, data: null});
    assert.equal(JSON.stringify(f.poll(1)).includes('private-account-capture'), false);
    assert.deepEqual(f.state.consoleCalls, []);
  }
  const f = fixture(); f.responses.set(configPath, () => {
    f.location.pathname = '/'; f.state.auth = 'disconnected'; return Promise.resolve(false);
  });
  f.helper.start(1, activeNumber); await settle();
  assert.deepEqual(f.poll(1), {request: 1, state: 'expired', data: null});
});

test('stop, page closure and bounded deadline discard late results and abort only owned requests', async () => {
  for (const action of ['stop', 'pagehide', 'timeout']) {
    const f = fixture(); const pending = deferred(); f.responses.set(configPath, () => pending.promise);
    f.helper.start(1, activeNumber); await settle();
    assert.equal(f.poll(1).state, 'pending');
    if (action === 'stop') f.helper.stop();
    if (action === 'pagehide') f.state.events.get('pagehide')();
    if (action === 'timeout') Array.from(f.state.timers.values())[0]();
    pending.resolve({generalData: [5000]}); await settle();
    assert.equal(f.poll(1).state, action === 'timeout' ? 'unavailable' : 'unsupported');
    assert.equal(f.state.calls.length, 1);
    assert.equal(f.state.timers.size, 0);
    assert.equal(f.state.aborts, 1);
    if (action === 'pagehide') assert.equal(f.helper.start(2, activeNumber), false);
  }
  const f = fixture(); const old = deferred(); f.responses.set(configPath, () => old.promise);
  f.helper.start(1, activeNumber); await settle(); f.helper.stop();
  f.responses.set(configPath, {generalData: [5000]}); f.helper.start(2, activeNumber); await settle();
  old.resolve({generalData: [7000]}); await settle();
  assert.equal(f.poll(2).data.data_remaining, '3.25 GB');
});

test('schema guards omit unknown values, bound buckets and never default missing allowances to zero', async () => {
  for (const [where, value] of [
    [configPath, 'unverified JSON text'], [summaryPath, {data: []}], [detailPath, {data: []}],
    [detailPath, [null]], [detailPath, Array.from({length: 65}, (_, index) => ({acctResId: index + 2, acctResName: 'bucket'}))],
    [detailPath, [{acctResId: 1}, {acctResId: 1}]],
  ]) {
    const f = fixture(); f.responses.set(where, value);
    f.helper.start(1, activeNumber); await settle();
    assert.deepEqual(f.poll(1), {request: 1, state: 'unsupported', data: null});
  }
  const f = fixture();
  f.responses.set(configPath, {}); f.responses.set(summaryPath, []);
  f.responses.set(detailPath, [{acctResId: 1, formatRealBalance: 0},
    {acctResId: 2, acctResName: 'Returned resource', formatRealBalance: 'unknown', expDate: 'tomorrow'},
    {acctResId: 3, acctResName: 'x'.repeat(161), formatRealBalance: '5'},
    {acctResId: 4, acctResName: 'unsafe\nname', formatRealBalance: '5'},
    {acctResId: 5, acctResName: 'Zero expiry', expDate: 0},
    {acctResId: 6, acctResName: 'Negative expiry', expDate: -1},
    {acctResId: 7, acctResName: 'Invalid calendar expiry', expDate: '2026-02-31 99:99:99'},
  ]);
  f.helper.start(1, activeNumber); await settle();
  assert.deepEqual(f.poll(1).data, {
    load_balance: '0', data_remaining: null, active_promos: [], expiry: null,
    sms_allowance: null, call_allowance: null,
    data_buckets: [{name: 'Returned resource', remaining: null, expiry: null},
      {name: 'Zero expiry', remaining: null, expiry: null},
      {name: 'Negative expiry', remaining: null, expiry: null},
      {name: 'Invalid calendar expiry', remaining: null, expiry: null}],
  });
});

test('bridge never reads credentials, browser storage or DOM and never exports raw account responses', async () => {
  const f = fixture();
  const privateValue = 'private-account-capture';
  for (const response of f.responses.values()) {
    if (response && typeof response === 'object') response.privateResponseField = privateValue;
  }
  Object.defineProperty(f.state.subscriber, 'cookie', {get() { throw new Error('private-cookie-access'); }});
  Object.defineProperty(f.state.subscriber, 'token', {get() { throw new Error('private-token-access'); }});
  f.helper.start(1, activeNumber); await settle();
  assert.equal(f.poll(1).state, 'ok');
  assert.deepEqual(f.state.privateAccess, []); assert.deepEqual(f.state.consoleCalls, []);
  const serialized = JSON.stringify(f.poll(1));
  for (const forbidden of [privateValue, activeNumber, '9920000001', 'prodInstId', 'accNbr', 'token', 'cookie']) {
    assert.equal(serialized.includes(forbidden), false);
  }
  assert.equal(serialized.length < 65536, true);
});

test('HTTP429 exports only a bounded Retry-After delay and stops the current read cycle', async () => {
  for (const [header, expected] of [['120', 120], ['7200', 3600], ['0', 1],
                                  ['Sun, 01 Jan 2090 00:00:00 GMT', 3600]]) {
    const f = fixture();
    const accessed = [];
    f.responses.set(configPath, {status: 429, headers: {get(name) { accessed.push(name); return header; }},
      privateResponseField: 'SYNTHETIC_PRIVATE_RESPONSE'});
    f.helper.start(1, activeNumber); await settle();
    assert.deepEqual(f.poll(1), {request: 1, state: 'rate_limited', data: null, retry_after: expected});
    assert.deepEqual(accessed, ['Retry-After']);
    assert.deepEqual(f.state.calls.map(call => call.url), [configPath]);
    assert.equal(f.state.timers.size, 0);
    assert.deepEqual(f.state.consoleCalls, []);
    assert.equal(JSON.stringify(f.poll(1)).includes('SYNTHETIC_PRIVATE'), false);
  }
});

test('thrown HTTP429 stays closed without usable headers and application codes are not HTTP evidence', async () => {
  for (const response of [
    {status: 429},
    {status: 429, headers: {get() { return '-1'; }}},
    {status: 429, headers: {get() { throw new Error('SYNTHETIC_PRIVATE_HEADER'); }}},
  ]) {
    const f = fixture();
    f.responses.set(configPath, () => Promise.reject({response, message: 'SYNTHETIC_PRIVATE_ERROR'}));
    f.helper.start(1, activeNumber); await settle();
    assert.deepEqual(f.poll(1), {request: 1, state: 'rate_limited', data: null});
    assert.deepEqual(f.state.consoleCalls, []);
    assert.deepEqual(f.state.privateAccess, []);
  }
  const f = fixture();
  f.responses.set(configPath, {code: 429, message: 'SYNTHETIC_PRIVATE_BODY'});
  f.helper.start(1, activeNumber); await settle();
  assert.deepEqual(f.poll(1), {request: 1, state: 'unavailable', data: null});
});

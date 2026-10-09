'use strict';
// Entirely synthetic browser/fetch responses. No Node or browser networking.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../src/sim_manager/carriers/dito/auth_observer.js'), 'utf8');
const ORIGIN = 'https://my.dito.ph';
const LOGIN = ORIGIN + '/ecare/webs/user/login';
const PRIVATE = 'SYNTHETIC_PRIVATE_ONLY';

function response(body, options = {}) {
  const result = {
    url: options.url || LOGIN, status: options.status || 200,
    ok: (options.status || 200) >= 200 && (options.status || 200) < 300,
    reads: 0,
    clone() {
      if (options.cloneError) throw new Error(PRIVATE);
      result.reads += 1;
      return { async json() { if (options.jsonError) throw new Error(PRIVATE); return body; } };
    }
  };
  return result;
}
function browser(options = {}) {
  let current = new URL(options.url || ORIGIN + '/');
  const events = {};
  const calls = [];
  const responses = [];
  const logs = [];
  const win = {
    get location() { return current; },
    history: {
      pushState(state, title, url) { current = new URL(url, current); },
      replaceState(state, title, url) { current = new URL(url, current); }
    },
    addEventListener(name, listener) { events[name] = listener; },
    fetch(input, init) {
      calls.push({input, init});
      if (responses.length === 0) throw new Error('Synthetic response missing');
      return Promise.resolve(responses.shift());
    }
  };
  win.top = options.subframe ? {} : win;
  for (const key of ['localStorage', 'sessionStorage', 'document']) {
    Object.defineProperty(win, key, {get() { throw new Error('Private storage access forbidden'); }});
  }
  if (options.noFetch) win.fetch = undefined;
  const context = {window: win, URL, console: {log(...v) { logs.push(v); }, error(...v) { logs.push(v); }}};
  vm.runInNewContext(source, context, {timeout: 1000});
  return {
    win, calls, responses, logs, context,
    poll() { return win.__simManagerDitoAuthObserver?.poll(); },
    async login(body, extra = {}) {
      const result = response(body, extra);
      responses.push(result);
      const returned = await win.fetch(LOGIN, {method: 'POST'});
      assert.equal(returned, result);
      return result;
    },
    navigate(url) { win.history.pushState(null, '', url); },
    pop(url) { current = new URL(url); events.popstate?.(); }
  };
}

test('installation is inert and polling exports only a closed state', () => {
  const b = browser();
  assert.equal(b.calls.length, 0);
  assert.equal(b.poll(), 'none');
  assert.equal(JSON.stringify(b.win.__simManagerDitoAuthObserver), '{}');
  assert.equal(b.logs.length, 0);
});
test('strict server success waits for site consent and subsequent success route', async () => {
  const b = browser();
  await b.login({loginSuccess: true, token: PRIVATE, refreshToken: PRIVATE, userData: {mobile: PRIVATE}});
  assert.equal(b.poll(), 'none');
  b.navigate('/privacy');
  assert.equal(b.poll(), 'none');
  b.navigate('/pto/home');
  assert.equal(b.poll(), 'authenticated');
  assert.equal(b.logs.length, 0);
});
test('URL alone cannot establish authentication', () => {
  const b = browser({url: ORIGIN + '/pto/home'});
  assert.equal(b.poll(), 'none');
  b.navigate('/pto/home');
  assert.equal(b.poll(), 'none');
});
test('preexisting success route cannot complete pending consent', async () => {
  const b = browser({url: ORIGIN + '/pto/home'});
  await b.login({loginSuccess: true});
  assert.equal(b.poll(), 'none');
});
test('nonboolean loginSuccess and alternate envelopes fail closed', async () => {
  for (const body of [{loginSuccess: 'true'}, {loginSuccess: 1}, {data: {loginSuccess: true}}, [], null, PRIVATE]) {
    const b = browser();
    await b.login(body);
    b.navigate('/pto/home');
    assert.equal(b.poll(), 'unsupported');
  }
});
test('rejected login is friendly closed state and can be retried manually', async () => {
  const b = browser();
  await b.login({loginSuccess: false, message: PRIVATE});
  assert.equal(b.poll(), 'rejected');
  await b.login({loginSuccess: true});
  b.navigate('/pto/home');
  assert.equal(b.poll(), 'authenticated');
});
test('authentication failure status cannot become successful', async () => {
  const b = browser();
  await b.login({loginSuccess: true}, {status: 500});
  b.navigate('/pto/home');
  assert.equal(b.poll(), 'unsupported');
});
test('401 login rejects without consuming its body', async () => {
  const b = browser();
  const r = await b.login({token: PRIVATE}, {status: 401});
  assert.equal(b.poll(), 'rejected');
  assert.equal(r.reads, 0);
});
test('source-backed security code never forwards diagnostics', async () => {
  const b = browser();
  await b.login({code: 'PORTAL-SECURITY-SYNTHETIC', message: PRIVATE});
  assert.equal(b.poll(), 'rejected');
  assert.equal(b.logs.length, 0);
});
test('clone and parse failures discard private exception text', async () => {
  for (const options of [{cloneError: true}, {jsonError: true}]) {
    const b = browser();
    await b.login({token: PRIVATE}, options);
    assert.equal(b.poll(), 'unsupported');
    assert.equal(b.logs.length, 0);
    assert.equal(JSON.stringify(b.win.__simManagerDitoAuthObserver).includes(PRIVATE), false);
  }
});
test('account API response is never cloned or interpreted', async () => {
  const b = browser();
  const url = ORIGIN + '/ecare/webs/account/SYNTHETIC/balance';
  const r = response({loginSuccess: true, code: 'PORTAL-SECURITY', token: PRIVATE}, {url, status: 401});
  b.responses.push(r);
  await b.win.fetch(url);
  b.navigate('/pto/home');
  assert.equal(b.poll(), 'none');
  assert.equal(r.reads, 0);
});
test('unrelated and credentialed request URLs cannot prove login', async () => {
  for (const url of ['https://evil.example/ecare/webs/user/login', 'https://my.dito.ph.evil.example/ecare/webs/user/login', 'http://my.dito.ph/ecare/webs/user/login', 'https://user@my.dito.ph/ecare/webs/user/login', 'https://my.dito.ph\\@evil.example/ecare/webs/user/login']) {
    const b = browser();
    const r = response({loginSuccess: true}, {url});
    b.responses.push(r);
    await b.win.fetch(url, {method: 'POST'});
    b.navigate('/pto/home');
    assert.equal(b.poll(), 'none');
    assert.equal(r.reads, 0);
  }
});
test('redirected login responses cannot prove authentication', async () => {
  const b = browser();
  const r = await b.login({loginSuccess: true}, {url: 'https://evil.example/ecare/webs/user/login'});
  b.navigate('/pto/home');
  assert.equal(b.poll(), 'none');
  assert.equal(r.reads, 0);
});
test('normalizable hostile paths are not considered an observed auth request', async () => {
  for (const url of [ORIGIN + '/ecare/webs/user/../user/login', ORIGIN + '/ecare/webs/%75ser/login']) {
    const b = browser();
    const r = response({loginSuccess: true});
    b.responses.push(r);
    await b.win.fetch(url, {method: 'POST'});
    b.navigate('/pto/home');
    assert.equal(b.poll(), 'none');
    assert.equal(r.reads, 0);
  }
});
test('only exact success route without query or fragment is accepted', async () => {
  for (const route of ['/pto/home/', '/pto/home?token=' + PRIVATE, '/pto/home#hash', 'https://evil.example/pto/home']) {
    const b = browser();
    await b.login({loginSuccess: true});
    b.navigate(route);
    assert.equal(b.poll(), 'none');
  }
});
test('connected session expires on evidenced first-party auth HTTP401', async () => {
  const b = browser();
  await b.login({loginSuccess: true});
  b.navigate('/pto/home');
  const url = ORIGIN + '/ecare/webs/common/configParam';
  const r = response({token: PRIVATE}, {url, status: 401});
  b.responses.push(r);
  await b.win.fetch(url, {method: 'POST'});
  assert.equal(b.poll(), 'expired');
  assert.equal(r.reads, 0);
});
test('site returning to sign-in conservatively disconnects without guessing expiry', async () => {
  const b = browser();
  await b.login({loginSuccess: true});
  b.navigate('/pto/home');
  b.win.history.replaceState(null, '', '/');
  assert.equal(b.poll(), 'disconnected');
});
test('source-backed logout success consumes only its numeric result', async () => {
  const b = browser();
  await b.login({loginSuccess: true});
  b.navigate('/pto/home');
  const url = ORIGIN + '/ecare/webs/user/logout';
  b.responses.push(response(0, {url}));
  await b.win.fetch(url);
  b.navigate('/');
  assert.equal(b.poll(), 'disconnected');
});
test('request objects are observed without reading credential bodies or headers', async () => {
  const b = browser();
  const input = {url: LOGIN, method: 'POST'};
  for (const key of ['body', 'headers']) Object.defineProperty(input, key, {get() { throw new Error(PRIVATE); }});
  b.responses.push(response({loginSuccess: true}));
  await b.win.fetch(input);
  b.navigate('/pto/home');
  assert.equal(b.poll(), 'authenticated');
});
test('wrong origin, subframes and missing fetch cannot install an observer', () => {
  for (const options of [{url: 'https://evil.example/'}, {subframe: true}, {noFetch: true}]) {
    const b = browser(options);
    assert.equal(b.poll(), undefined);
    assert.equal(b.calls.length, 0);
  }
});
test('a stale response cannot win a newer sign-in attempt', async () => {
  const b = browser();
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  const r = response(null);
  r.clone = () => ({json: () => pending});
  b.responses.push(r);
  const first = b.win.fetch(LOGIN, {method: 'POST'});
  await b.login({loginSuccess: false});
  release({loginSuccess: true, token: PRIVATE});
  await first;
  b.navigate('/pto/home');
  assert.equal(b.poll(), 'rejected');
});

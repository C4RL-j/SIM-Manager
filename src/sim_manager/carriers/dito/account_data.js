/* Source-backed read-only MyDITO account bridge. No private session export. */
(function () {
  'use strict';
  const origin = 'https://my.dito.ph';
  const successPath = '/pto/home';
  const configPath = '/ecare/webs/common/configParam';
  const summaryPath = '/ecare/webs/balance/balInfo/glSumInfo';
  const detailPath = '/ecare/webs/balance/balInfo';
  const subscriberPath = '/ecare/webs/subs/qrySubsDetail?prodInstIds=';
  const captureId = '__sim_manager_dito_account_capture__';
  const maxText = 160;
  let revision = 0;
  let lastRequest = 0;
  let current = null;
  let captured = null;
  let disposed = false;

  function route() {
    return window.top === window && window.location.origin === origin &&
      window.location.pathname === successPath && !window.location.search &&
      !window.location.hash;
  }
  function authenticated() {
    try {
      const observer = window.__simManagerDitoAuthObserver;
      return route() && observer && observer.poll() === 'authenticated';
    } catch (_) { return false; }
  }
  function record(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }
  function text(value) {
    return typeof value === 'string' && value.length > 0 && value.length <= maxText &&
      value.trim().length > 0 && !Array.from(value).some(function (character) {
        const code = character.codePointAt(0);
        return code < 32 || code === 127 || (code >= 0xd800 && code <= 0xdfff);
      }) ? value : null;
  }
  function id(value) {
    if (typeof value === 'number') {
      return Number.isSafeInteger(value) && value > 0 ? String(value) : null;
    }
    return typeof value === 'string' && /^[1-9][0-9]{0,23}$/.test(value) ? value : null;
  }
  function phone(value) {
    if (typeof value === 'number' && Number.isSafeInteger(value)) value = String(value);
    if (typeof value !== 'string') return null;
    value = value.trim();
    if (/^09[0-9]{9}$/.test(value)) return value.slice(1);
    if (/^9[0-9]{9}$/.test(value)) return value;
    if (/^(?:\+63|63)9[0-9]{9}$/.test(value)) return value.replace(/^\+?63/, '');
    return null;
  }
  function formatted(value) {
    if (typeof value === 'number') {
      if (!Number.isFinite(value) || Math.abs(value) > 1e15) return null;
      value = String(value);
    }
    return typeof value === 'string' && value.length <= 32 &&
      /^-?(?:[0-9]{1,16}|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,8})?$/.test(value) ? value : null;
  }
  function expiry(value) {
    if (typeof value === 'number' && Number.isSafeInteger(value) && value > 0) {
      const date = new Date(value); // The official Home uses dayjs(number), i.e. milliseconds.
      return Number.isFinite(date.valueOf()) ? date.toISOString() : null;
    }
    const result = text(value);
    const match = result && /^([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[ T]([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:\.[0-9]{1,3})?)?(?:Z|[+-]([0-9]{2}):?([0-9]{2}))?)?$/.exec(result);
    if (!match || Number(match[1]) === 0 || Number(match[2]) < 1 || Number(match[2]) > 12 ||
        Number(match[3]) < 1 || Number(match[3]) > 31 || Number(match[4] || 0) > 23 ||
        Number(match[5] || 0) > 59 || Number(match[6] || 0) > 59 ||
        Number(match[7] || 0) > 23 || Number(match[8] || 0) > 59) return null;
    const date = new Date(0);
    date.setUTCFullYear(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    return date.getUTCMonth() === Number(match[2]) - 1 &&
      date.getUTCDate() === Number(match[3]) ? result : null;
  }
  function amount(row, currency) {
    if (!record(row)) return null;
    if (!currency && row.unlimitedFlag === 'Y') return 'Unlimited';
    const value = formatted(row.formatRealBalance);
    if (value === null) return null;
    const unit = text(currency ? row.currencySymbol : row.formatRealBalanceUnitName);
    const result = unit ? (currency ? unit + ' ' + value : value + ' ' + unit) : value;
    return text(result);
  }
  function responseIssue(value) {
    if (record(value) && value.status === 429) return 'rate_limited';
    if (record(value) && typeof value.code === 'string' && value.code.includes('PORTAL-SECURITY')) return 'expired';
    if (value === false || (record(value) && (value.code || value.message))) return 'unavailable';
    return null;
  }
  function retryAfter(response) {
    try {
      const headers = response.headers;
      const value = headers && typeof headers.get === 'function' ? headers.get('Retry-After') : null;
      if (typeof value !== 'string' || value.length > 128) return null;
      let seconds = null;
      if (/^[0-9]{1,9}$/.test(value)) seconds = Number(value);
      else if (/^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), [0-9]{2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) [0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2} GMT$/.test(value)) {
        const date = Date.parse(value);
        if (Number.isFinite(date)) seconds = Math.ceil((date - Date.now()) / 1000);
      }
      return Number.isFinite(seconds) ? Math.min(3600, Math.max(1, seconds)) : null;
    } catch (_) { return null; }
  }
  function finishResponseIssue(operation, value) {
    const issue = responseIssue(value);
    if (!issue) return false;
    setResult(operation, issue, null, issue === 'rate_limited' ? retryAfter(value) : null);
    return true;
  }
  function modules() {
    if (!captured) {
      const chunks = window.webpackJsonp;
      if (!Array.isArray(chunks) || typeof chunks.push !== 'function') return null;
      // The public webpack4 bootstrap executes entry modules using this queue.
      // The extra entry captures its existing module loader, never session material.
      chunks.push([[], { [captureId]: function (_module, _exports, require) { captured = require; } }, [[captureId]]]);
    }
    if (typeof captured !== 'function') return null;
    const common = captured('+n12');
    const client = captured('t3Un');
    if (!common || !client || typeof common.I !== 'function' ||
        typeof common.K !== 'function' || typeof client.a !== 'function') return null;
    return { subscriber: common.I, user: common.K, request: client.a };
  }
  function setResult(operation, state, data = null, retry = null) {
    if (disposed || current !== operation || operation.revision !== revision) return;
    const result = {request: operation.request, state, data};
    if (state === 'rate_limited' && Number.isInteger(retry) && retry >= 1 && retry <= 3600) result.retry_after = retry;
    operation.result = Object.freeze(result);
    cancel(operation);
  }
  function cancel(operation) {
    clearTimeout(operation.timer);
    try { if (operation.abort) operation.abort.abort(); } catch (_) {}
    operation.abort = null;
  }
  function securityState() {
    return window.location.origin === origin && window.location.pathname === '/' ? 'expired' : 'unsupported';
  }
  function knownRows(rows) {
    return Array.isArray(rows) && rows.length <= 256 && rows.every(record);
  }
  function glId(value) {
    const result = id(value);
    const number = result === null ? null : Number(result);
    return Number.isSafeInteger(number) ? number : null;
  }
  function summaryRow(rows, config, key) {
    const list = config[key];
    if (!Array.isArray(list) || list.length === 0) return null;
    const expected = glId(list[0]);
    if (expected === null) return null;
    const found = rows.filter(row => glId(row.glId) === expected);
    return found.length === 1 ? found[0] : null;
  }
  function allowance(rows, config, keys) {
    const seen = new Set();
    const parts = [];
    for (const key of keys) {
      const row = summaryRow(rows, config, key);
      if (!row || seen.has(glId(row.glId))) continue;
      seen.add(glId(row.glId));
      const remaining = amount(row, false);
      if (remaining === null) continue;
      const name = text(row.acctResName);
      parts.push(name ? name + ': ' + remaining : remaining);
    }
    return parts.length ? text(parts.join('; ')) : null;
  }
  function normalize(config, summaries, details) {
    if (!record(config) || !knownRows(summaries) || !knownRows(details)) return null;
    const books = details.filter(row => row.acctResId === 1);
    if (books.length > 1) return null;
    const book = books.length === 1 ? books[0] : null;
    const otherRows = details.filter(row => Number.isSafeInteger(row.acctResId) && row.acctResId > 1);
    if (otherRows.length > 64) return null;
    const buckets = [];
    for (const row of otherRows) {
      const name = text(row.acctResName);
      if (!name) continue;
      buckets.push(Object.freeze({name, remaining: amount(row, false), expiry: expiry(row.expDate)}));
    }
    const general = summaryRow(summaries, config, 'generalData');
    const result = Object.freeze({
      load_balance: amount(book, true),
      data_remaining: amount(general, false),
      // Home labels resource buckets "My Promo Details"; no commercial offer name is evidenced.
      active_promos: Object.freeze([]),
      expiry: book ? expiry(book.expDate) : null,
      sms_allowance: allowance(summaries, config, ['allNetSMS', 'offNetSMS', 'onNetSMS']),
      call_allowance: allowance(summaries, config, ['allNetVoice', 'offNetVoice', 'onNetVoice']),
      data_buckets: Object.freeze(buckets),
    });
    if (JSON.stringify(result).length > 65536) return null;
    if (!result.load_balance && !result.data_remaining && !result.expiry &&
        !result.sms_allowance && !result.call_allowance && !result.data_buckets.length) return null;
    return result;
  }
  function alive(operation) {
    return !disposed && current === operation && operation.revision === revision && operation.result.state === 'pending';
  }
  async function retrieve(operation, expectedPhone) {
    try {
      if (!alive(operation)) return;
      if (!authenticated()) { setResult(operation, securityState()); return; }
      const api = modules();
      if (!api) { setResult(operation, 'unsupported'); return; }
      const target = phone(expectedPhone);
      if (!target) { setResult(operation, 'account_mismatch'); return; }
      // Bypass both the original client's cache and the browser HTTP cache.
      const options = {timeout: 8000, useCache: false, cache: 'no-store'};
      if (operation.abort) options.signal = operation.abort.signal;
      let subscriber = api.subscriber();
      let fallbackId = null;
      if (!record(subscriber) || !id(subscriber.prodInstId)) {
        const user = api.user();
        fallbackId = record(user) ? id(user.subsId) : null;
        if (!fallbackId) { setResult(operation, 'account_mismatch'); return; }
        subscriber = await api.request(subscriberPath + fallbackId, {...options, method: 'GET'});
        if (!alive(operation)) return;
        if (!authenticated()) { setResult(operation, securityState()); return; }
        if (finishResponseIssue(operation, subscriber)) return;
      }
      const productValue = record(subscriber) ? subscriber.prodInstId : null;
      const product = id(productValue);
      if (!product || phone(subscriber.accNbr) !== target) { setResult(operation, 'account_mismatch'); return; }
      subscriber = null;
      const sameContext = function () {
        if (!authenticated()) return false;
        const latest = api.subscriber();
        if (record(latest) && id(latest.prodInstId)) {
          return id(latest.prodInstId) === product && phone(latest.accNbr) === target;
        }
        const user = api.user();
        return fallbackId !== null && record(user) && id(user.subsId) === fallbackId;
      };
      const config = await api.request(configPath, {...options, method: 'POST', data: {configCode: 'webs.ecare.usageGL'}});
      if (!alive(operation)) return;
      if (!authenticated()) { setResult(operation, securityState()); return; }
      if (!sameContext()) { setResult(operation, 'account_mismatch'); return; }
      if (finishResponseIssue(operation, config)) return;
      if (!record(config)) { setResult(operation, 'unsupported'); return; }
      const values = await Promise.all([
        api.request(summaryPath, {...options, method: 'POST', data: {prodInstId: productValue}}),
        api.request(detailPath, {...options, method: 'POST', data: {prodInstId: productValue}}),
      ]);
      if (!alive(operation)) return;
      if (!authenticated()) { setResult(operation, securityState()); return; }
      if (!sameContext()) { setResult(operation, 'account_mismatch'); return; }
      if (finishResponseIssue(operation, values[0]) || finishResponseIssue(operation, values[1])) return;
      const data = normalize(config, values[0], values[1]);
      setResult(operation, data ? 'ok' : 'unsupported', data);
    } catch (error) {
      if (!alive(operation)) return;
      try {
        const response = record(error) && record(error.response) ? error.response : error;
        if (record(response) && response.status === 429) {
          setResult(operation, 'rate_limited', null, retryAfter(response));
          return;
        }
      } catch (_) {}
      setResult(operation, authenticated() ? 'unavailable' : securityState());
    }
  }
  function stop() {
    revision += 1;
    if (current) {
      cancel(current);
    }
    current = null;
  }
  function start(request, expectedPhone) {
    if (disposed || !Number.isSafeInteger(request) || request <= lastRequest ||
        typeof expectedPhone !== 'string' || !authenticated() ||
        (current && current.result.state === 'pending')) return false;
    stop();
    lastRequest = request;
    const operation = {request, revision, timer: null, abort: null,
      result: Object.freeze({request, state: 'pending', data: null})};
    if (typeof AbortController === 'function') operation.abort = new AbortController();
    current = operation;
    operation.timer = setTimeout(function () { setResult(operation, 'unavailable'); }, 20000);
    Promise.resolve().then(function () { return retrieve(operation, expectedPhone); });
    return true;
  }
  function poll(request) {
    if (!Number.isSafeInteger(request) || request <= 0) return null;
    return current && current.request === request ? current.result :
      Object.freeze({request, state: 'unsupported', data: null});
  }
  if (window.top !== window || window.location.origin !== origin || window.__simManagerDitoAccountData) return;
  Object.defineProperty(window, '__simManagerDitoAccountData', {
    value: Object.freeze({start, poll, stop}), configurable: false, writable: false,
  });
  window.addEventListener('pagehide', function () { disposed = true; stop(); });
})();

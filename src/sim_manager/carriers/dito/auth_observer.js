/* MyDITO auth-only observer. It never sends requests or exports private data. */
(function () {
  'use strict';
  const origin = 'https://my.dito.ph';
  const loginPath = '/ecare/webs/user/login';
  const logoutPath = '/ecare/webs/user/logout';
  const successPath = '/pto/home';
  const authMethods = new Map([
    [loginPath, 'POST'], [logoutPath, 'GET'], ['/ecare/webs/captcha/check', 'POST'],
    ['/ecare/webs/user/login/check', 'POST'], ['/ecare/webs/common/configParam', 'POST'],
    ['/ecare/webs/content/qryContentByCode', 'POST'], ['/ecare/webs/cust/sign/privacyPolicy', 'POST'],
    ['/ecare/webs/common/defCurrencyType', 'GET'], ['/ecare/common/currencyType/default', 'GET']
  ]);
  let state = 'none';
  let proof = false;
  let connected = false;
  let attempt = 0;
  const nativeFetch = window.fetch;
  function route() {
    if (proof && window.location.origin === origin &&
        window.location.pathname === successPath && !window.location.search &&
        !window.location.hash) {
      connected = true;
      state = 'authenticated';
    } else if (connected && window.location.origin === origin &&
               window.location.pathname === '/') {
      connected = false;
      proof = false;
      state = 'disconnected';
    }
  }
  function address(input) {
    try {
      const raw = typeof input === 'string' ? input : input && input.url;
      if (typeof raw !== 'string' || /[\\\u0000-\u0020\u007f]/.test(raw)) return null;
      const rawPath = raw.split(/[?#]/, 1)[0];
      if (rawPath.includes('%') || /(?:^|\/)\.{1,2}(?:\/|$)/.test(rawPath)) return null;
      const url = new URL(raw, origin + '/');
      if (url.origin !== origin || url.username || url.password ||
          url.pathname.includes('%') || url.pathname.includes('//')) return null;
      return url;
    } catch (_) { return null; }
  }
  function securityFailure(body) {
    return body !== null && typeof body === 'object' && !Array.isArray(body) &&
      typeof body.code === 'string' && body.code.includes('PORTAL-SECURITY');
  }
  async function observe(response, url, method, generation) {
    // Ignore every account/asset/unrelated body, even if it contains auth-like keys.
    if (!url || authMethods.get(url.pathname) !== method) return;
    if (!response || !address(response.url) ||
        address(response.url).pathname !== url.pathname) return;
    const isLogin = url.pathname === loginPath && method === 'POST';
    const isLogout = url.pathname === logoutPath && method === 'GET';
    if (response.status === 401) {
      if (connected) { connected = false; proof = false; state = 'expired'; }
      else if (isLogin && generation === attempt) { proof = false; state = 'rejected'; }
      return;
    }
    // Bootstrap responses are not parsed. Their HTTP 401 is sufficient evidence.
    if (!isLogin && !isLogout) return;
    try {
      const body = await response.clone().json();
      if (isLogin && generation !== attempt) return;
      if (securityFailure(body)) {
        proof = false;
        state = connected ? 'expired' : 'rejected';
        connected = false;
      } else if (isLogout && response.ok && body === 0) {
        connected = false;
        proof = false;
        state = 'disconnected';
      } else if (isLogin && response.ok && body !== null &&
                 typeof body === 'object' && !Array.isArray(body) &&
                 body.loginSuccess === true) {
        proof = true;
        state = 'none';
      } else if (isLogin && body !== null && typeof body === 'object' &&
                 !Array.isArray(body) && body.loginSuccess === false) {
        proof = false;
        state = 'rejected';
      } else if (isLogin) {
        proof = false;
        state = 'unsupported';
      }
    } catch (_) {
      if (isLogin && generation === attempt) { proof = false; state = 'unsupported'; }
    }
  }
  if (window.location.origin !== origin || window.top !== window ||
      typeof nativeFetch !== 'function') return;
  if (window.__simManagerDitoAuthObserver) return;
  Object.defineProperty(window, '__simManagerDitoAuthObserver', {
    value: Object.freeze({ poll: function () { return state; } }),
    configurable: false, writable: false
  });
  window.fetch = function (input, init) {
    const url = address(input);
    const method = String((init && init.method) ||
      (typeof input !== 'string' && input && input.method) || 'GET').toUpperCase();
    if (url && url.pathname === loginPath && method === 'POST') {
      attempt += 1;
      proof = false;
      state = 'none';
    }
    const generation = attempt;
    return nativeFetch.apply(this, arguments).then(function (response) {
      // Wait only for the narrow cloned auth result, preserving the original body.
      return observe(response, url, method, generation).then(function () { return response; });
    }, function (error) {
      // The site's native network error remains its own. Export no exception text.
      if (url && url.pathname === loginPath && method === 'POST' && generation === attempt) {
        proof = false;
        state = 'unsupported';
      }
      throw error;
    });
  };
  for (const name of ['pushState', 'replaceState']) {
    const native = window.history[name];
    window.history[name] = function () {
      const result = native.apply(this, arguments);
      route();
      return result;
    };
  }
  window.addEventListener('popstate', route);
})();

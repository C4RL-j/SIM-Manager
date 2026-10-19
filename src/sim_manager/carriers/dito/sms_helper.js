/* Explicit SMS assistance only: no field reads, requests or sign-in submission.
 * The original form/selectors were publicly verified on 2026-10-09. Unknown
 * structure, login modes, routes and visible challenges disable assistance.
 */
(() => {
  'use strict';
  const OVERLAYS = 'iframe, dialog, [role="dialog"], [aria-modal="true"], .ant-modal, .ant-modal-wrap, .ant-modal-mask, .ant-drawer, .ant-drawer-mask';
  let request = 0;
  let stopped = false;

  function loginPage() {
    try {
      const url = new URL(window.location.href);
      return window.top === window && url.protocol === 'https:' &&
        url.hostname === 'my.dito.ph' && (!url.port || url.port === '443') &&
        !url.username && !url.password && url.pathname === '/' &&
        !url.search && !url.hash;
    } catch (_) { return false; }
  }

  function one(parent, selector) {
    const nodes = parent.querySelectorAll(selector);
    return nodes.length === 1 ? nodes[0] : null;
  }

  function visible(node) {
    return node.getClientRects().length !== 0;
  }

  function shape() {
    if (stopped || !loginPage() || !document.body) return null;
    const root = one(document, '.loginComponent___1mTUY');
    const layout = root && one(root, '.loginContain___3yi25');
    const card = layout && one(layout, '.loginForm___2LvyN');
    if (!root || !layout || !card || layout.parentElement !== root ||
        card.parentElement !== layout) return null;
    const title = one(card, '.loginTitle___3y1YZ');
    // Only the fixed public mode title is read; never fields, errors or SMS text.
    if (!title || title.childElementCount !== 0 || title.textContent !== 'Sign In with SMS') return null;
    const form = one(card, 'form');
    if (!form) return null;
    const code = one(form, 'input[placeholder="SMS code"]');
    const send = one(form, '.sendCodeCom___qnsTR');
    const resend = send && one(send, 'span.timeBox___M0k-r');
    const submit = one(form, 'button[type="submit"]');
    const inputs = form.querySelectorAll('input');
    if (!code || !send || !resend || !submit || !send.contains(code) ||
        inputs.length !== 2 || code.disabled || code.readOnly ||
        (code.getAttribute('type') || 'text').toLowerCase() !== 'text') return null;
    const maximum = code.getAttribute('maxlength');
    if (maximum !== null && maximum !== '6') return null;
    const phone = inputs[0] === code ? inputs[1] : inputs[0];
    const type = (phone.getAttribute('type') || 'text').toLowerCase();
    const phoneItem = phone.closest('.ant-form-item');
    const codeItem = code.closest('.ant-form-item');
    if (!['text', 'tel', 'number'].includes(type) || !phoneItem || !codeItem ||
        phoneItem === codeItem || !form.contains(phoneItem) || !form.contains(codeItem) ||
        !visible(phone) || !visible(code) || !visible(resend) || !visible(submit)) return null;
    const overlays = document.querySelectorAll(OVERLAYS);
    if (overlays.length > 32 || Array.from(overlays).some(visible)) return null;
    return {code, resend};
  }

  function observe() {
    try { return {request, fillable: Boolean(shape())}; }
    catch (_) { return {request, fillable: false}; }
  }

  function requested(event) {
    try {
      if (!event || event.isTrusted !== true || request >= Number.MAX_SAFE_INTEGER) return;
      const match = shape();
      if (match && event.target && match.resend.contains(event.target) &&
          match.resend.matches('.send___2zLy_') &&
          !match.resend.matches('.countDown___3eXL4') &&
          match.resend.getAttribute('aria-disabled') !== 'true' &&
          !match.resend.hasAttribute('disabled')) request += 1;
    } catch (_) { /* Do not alter the official click or expose page exceptions. */ }
  }

  function fill(code, expectedRequest) {
    try {
      if (typeof code !== 'string' || code.length !== 6 || !/^[0-9]{6}$/.test(code) ||
          !Number.isSafeInteger(expectedRequest) || expectedRequest <= 0 ||
          expectedRequest !== request) return false;
      const match = shape();
      if (!match) return false;
      // Bypass React's instance tracker while preserving the official listeners.
      // This native setter never reads the current value or touches the number.
      const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
      if (!descriptor || typeof descriptor.set !== 'function') return false;
      descriptor.set.call(match.code, code);
      match.code.dispatchEvent(new Event('input', {bubbles: true}));
      match.code.dispatchEvent(new Event('change', {bubbles: true}));
      return true;
    } catch (_) { return false; }
  }

  function stop() {
    stopped = true;
    try { document.removeEventListener('click', requested, true); } catch (_) { /* silent */ }
  }

  if (!loginPage()) return;
  try {
    if (window.__simManagerDitoSmsHelper) return;
    Object.defineProperty(window, '__simManagerDitoSmsHelper', {
      value: Object.freeze({observe, fill}), writable: false, configurable: false,
    });
    document.addEventListener('click', requested, true);
    window.addEventListener('pagehide', stop, {once: true});
  } catch (_) { stop(); }
})();

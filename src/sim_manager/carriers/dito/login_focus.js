/* Presentation only: the original official SMS form and every handler remain.
 * Selectors/shape were checked against public p__Login.a8b21259.async.js on
 * 2026-10-09. A different layout, login mode or visible challenge stays full.
 */
(() => {
  'use strict';
  const ATTRIBUTE = 'data-sim-manager-dito-login-focus';
  const ROOT = '.loginComponent___1mTUY';
  const CONTAIN = '.pageContain___3snYk';
  const PAGE = '.pageComponent___2BkvW';
  const LAYOUT = '.loginContain___3yi25';
  const CARD = '.loginForm___2LvyN';
  const TITLE = '.loginTitle___3y1YZ';
  const OVERLAYS = 'iframe, dialog, [role="dialog"], [aria-modal="true"], .ant-modal, .ant-modal-wrap, .ant-modal-mask, .ant-drawer, .ant-drawer-mask';
  const CSS = `
    [${ATTRIBUTE}="hide"] { display: none !important; }
    [${ATTRIBUTE}="ancestor"], [${ATTRIBUTE}="footer"], [${ATTRIBUTE}="footer-content"] {
      width: 100% !important; max-width: 100% !important;
      min-width: 0 !important; box-sizing: border-box !important;
    }
    [${ATTRIBUTE}="footer-content"] { padding: 8px 12px !important; }
    [${ATTRIBUTE}="footer-row"], [${ATTRIBUTE}="footer-legal"] {
      display: flex !important; flex-wrap: wrap !important;
      width: 100% !important; max-width: 100% !important;
      min-width: 0 !important; box-sizing: border-box !important;
      overflow-wrap: anywhere !important;
      height: auto !important;
    }
    [${ATTRIBUTE}="footer-legal"] { flex: 1 1 100% !important; }
    [${ATTRIBUTE}="footer-legal"] a {
      white-space: normal !important; overflow-wrap: anywhere !important;
    }
    [${ATTRIBUTE}="root"] {
      display: flex !important; align-items: center !important;
      justify-content: center !important; min-width: 0 !important;
      width: 100% !important; max-width: 100% !important;
      min-height: calc(100vh - 64px) !important; height: auto !important;
      box-sizing: border-box !important; padding: 12px 10px !important;
      overflow: visible !important;
    }
    [${ATTRIBUTE}="layout"] {
      display: flex !important; align-items: center !important;
      justify-content: center !important; position: relative !important;
      width: 100% !important; max-width: 480px !important;
      min-width: 0 !important; height: auto !important; margin: 0 !important;
      padding: 0 !important; box-sizing: border-box !important;
    }
    [${ATTRIBUTE}="card"] {
      position: relative !important; float: none !important;
      width: 100% !important; max-width: 420px !important;
      min-width: 0 !important; height: auto !important;
      margin: 0 !important; padding: 24px 28px !important;
      box-sizing: border-box !important;
    }
  `;
  let observer = null;
  let style = null;
  let owned = [];
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
    if (!loginPage() || !document.body || !document.head) return null;
    const root = one(document, ROOT);
    const contain = root && root.parentElement;
    const page = contain && contain.parentElement;
    const layout = root && one(root, LAYOUT);
    const card = layout && one(layout, CARD);
    if (!root || !contain || !page || !contain.matches(CONTAIN) || !page.matches(PAGE) ||
        !layout || !card || layout.parentElement !== root || card.parentElement !== layout) return null;
    if (Array.from(root.children).some(node => node !== layout && !node.matches('img.backgroundImg___AIwrQ')) ||
        Array.from(layout.children).some(node => node !== card && !node.matches('img.bubble1___2mY27, .loginLeft___2omVj, .bubble___2vWPU'))) return null;
    const title = one(card, TITLE);
    // Read only the evidenced text-only public mode title, never form/error text.
    if (!title || title.childElementCount !== 0 || title.textContent !== 'Sign In with SMS') return null;
    const form = one(card, 'form');
    if (!form) return null;
    const code = one(form, 'input[placeholder="SMS code"]');
    const send = one(form, '.sendCodeCom___qnsTR');
    const resend = send && one(send, 'span.timeBox___M0k-r');
    const submit = one(form, 'button[type="submit"]');
    const inputs = form.querySelectorAll('input');
    if (!code || !send || !resend || !submit || !send.contains(code) || inputs.length !== 2) return null;
    // Public native DOM omits the component's maxLength prop; both known shapes
    // are accepted without writing any attribute or reading the input value.
    const maximum = code.getAttribute('maxlength');
    if (maximum !== null && maximum !== '6') return null;
    const phone = inputs[0] === code ? inputs[1] : inputs[0];
    const type = (phone.getAttribute('type') || 'text').toLowerCase();
    const phoneItem = phone.closest('.ant-form-item');
    const codeItem = code.closest('.ant-form-item');
    if (!['text', 'tel', 'number'].includes(type) ||
        !phoneItem || !codeItem || phoneItem === codeItem ||
        !form.contains(phoneItem) || !form.contains(codeItem) ||
        !visible(phone) || !visible(code) || !visible(submit)) return null;
    // An open consent/security dialog restores the site's complete presentation.
    const overlays = document.querySelectorAll(OVERLAYS);
    if (overlays.length > 32 || Array.from(overlays).some(visible)) return null;
    return {root, layout, card, contain, page};
  }

  function removePresentation() {
    for (const [node, role] of owned) {
      if (node.getAttribute(ATTRIBUTE) === role) node.removeAttribute(ATTRIBUTE);
    }
    owned = [];
    if (style) style.remove();
    style = null;
  }

  function mark(node, role) {
    if (node.hasAttribute(ATTRIBUTE)) return false;
    node.setAttribute(ATTRIBUTE, role);
    owned.push([node, role]);
    return true;
  }

  function safeChrome(node, card) {
    // Footer contains legal links and is deliberately never a hide candidate.
    const protectedNodes = 'form, input, button, textarea, select, iframe, dialog, [role="dialog"], [aria-modal="true"], .ant-modal, .term___23Qj1, a[href*="privacy"], a[href*="terms"]';
    return !node.contains(card) && !card.contains(node) &&
      !node.matches(protectedNodes) && !node.querySelector(protectedNodes);
  }

  function watch() {
    if (observer && !stopped && document.body) {
      observer.observe(document.body, {
        childList: true, subtree: true, attributes: true,
        attributeFilter: ['class', 'style', 'hidden', 'role', 'aria-modal', 'type', 'placeholder', 'maxlength'],
      });
      // Only the public text-only mode title needs text-node observation.
      // No input, error, legal or other page text is observed/read here.
      const title = one(document, TITLE);
      if (title) observer.observe(title, {characterData: true, subtree: true});
    }
  }

  function refresh() {
    if (stopped) return;
    // Our own mutations cannot feed the observer back into itself.
    if (observer) observer.disconnect();
    try {
      removePresentation();
      const match = shape();
      if (match && mark(match.root, 'root') && mark(match.layout, 'layout') && mark(match.card, 'card') &&
          mark(match.contain, 'ancestor') && mark(match.page, 'ancestor')) {
        for (const selector of ['.backgroundImg___AIwrQ', '.loginLeft___2omVj', '.bubble___2vWPU', '.bubble1___2mY27']) {
          const nodes = match.root.querySelectorAll(selector);
          if (nodes.length > 8) { removePresentation(); return; }
          for (const node of nodes) if (safeChrome(node, match.card)) mark(node, 'hide');
        }
        for (const selector of ['.pageHeader___3FaDJ', '.header___17TWW']) {
          const nodes = document.querySelectorAll(selector);
          if (nodes.length > 8) { removePresentation(); return; }
          for (const node of nodes) if (safeChrome(node, match.card)) mark(node, 'hide');
        }
        // Public empty-page DOM verified these fixed-width footer wrappers.
        // Keep the original legal row and links; only safe marketing is hidden.
        const footerPage = one(document, '.pageFooter___lIB3B');
        const footer = footerPage && one(footerPage, '.footerComponent___tkORO');
        const content = footer && one(footer, '.content___3QhJX');
        const row = footer && one(footer, '.footer___cQk2w');
        const legal = row && one(row, '.leftImg___2I0v5');
        if (footer && content && row && legal && footer.parentElement === footerPage &&
            content.parentElement === footer && row.parentElement === footer && legal.parentElement === row) {
          mark(footerPage, 'footer');
          mark(footer, 'footer-content');
          mark(row, 'footer-row');
          mark(legal, 'footer-legal');
          const imageBox = one(content, '.imgBox___ZW4QJ');
          const menus = one(content, '.right___FPWPF');
          const columns = menus && menus.querySelectorAll('.menu___2cz5G');
          const knownMarketing = imageBox && menus && content.children.length === 2 &&
            imageBox.parentElement === content && menus.parentElement === content &&
            imageBox.children.length === 1 && imageBox.children[0].matches('img') &&
            columns.length === 6 && menus.children.length === 6 &&
            Array.from(columns).every(column => column.parentElement === menus &&
              column.children.length === 2 && column.children[0].matches('span') && column.children[1].matches('ul'));
          if (knownMarketing && safeChrome(content, match.card)) mark(content, 'hide');
          const social = one(row, '.rightImg___1ZBoU');
          if (social && social.parentElement === row && [3, 4].includes(social.children.length) &&
              Array.from(social.children).every(link => link.matches('a') && link.children.length === 1 && link.children[0].matches('img')) &&
              safeChrome(social, match.card)) mark(social, 'hide');
        }
        style = document.createElement('style');
        style.textContent = CSS;
        document.head.appendChild(style);
      } else {
        removePresentation();
      }
    } catch (_) {
      // No site exception or private content reaches console/application code.
      try { removePresentation(); } catch (_) { /* full page is the fallback */ }
    } finally { watch(); }
  }

  function restore() {
    stopped = true;
    if (observer) observer.disconnect();
    try { removePresentation(); } catch (_) { /* silent presentation fallback */ }
  }

  if (!loginPage() || typeof MutationObserver !== 'function') return;
  try {
    if (window.__simManagerDitoLoginFocus) return;
    Object.defineProperty(window, '__simManagerDitoLoginFocus', {
      value: Object.freeze({restore}), writable: false, configurable: false,
    });
    observer = new MutationObserver(refresh);
    window.addEventListener('popstate', refresh);
    window.addEventListener('hashchange', refresh);
    window.addEventListener('pagehide', restore, {once: true});
    refresh();
  } catch (_) { restore(); }
})();

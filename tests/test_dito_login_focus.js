'use strict';
// Synthetic DOM only. No browser, network, carrier login or private input read.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../src/sim_manager/carriers/dito/login_focus.js'), 'utf8');
const ATTRIBUTE = 'data-sim-manager-dito-login-focus';

function matches(node, selector) {
  return selector.split(',').some(part => {
    let plain = part.trim();
    const attributes = [];
    plain = plain.replace(/\[([^\]=*]+)(\*?=)(?:"([^"]*)"|'([^']*)')\]/g, (_, name, operator, double, single) => {
      attributes.push([name, operator, double ?? single]);
      return '';
    });
    const classes = [];
    plain = plain.replace(/\.([A-Za-z0-9_-]+)/g, (_, name) => { classes.push(name); return ''; });
    return (!plain || plain.toLowerCase() === node.tagName.toLowerCase()) &&
      classes.every(name => (node.attributes.class || '').split(/\s+/).includes(name)) &&
      attributes.every(([name, operator, value]) => operator === '=' ? node.attributes[name] === value : (node.attributes[name] || '').includes(value));
  });
}

class Element {
  constructor(tag, attributes = {}, text = '') {
    this.tagName = tag.toUpperCase();
    this.attributes = {...attributes};
    this.children = [];
    this.parentElement = null;
    this._text = text;
    this.rendered = true;
    this.writes = [];
  }
  get childElementCount() { return this.children.length; }
  get value() { throw new Error('Private input value read is forbidden'); }
  set value(_) { throw new Error('Input mutation is forbidden'); }
  get textContent() {
    if (this.attributes.class !== 'loginTitle___3y1YZ') throw new Error('Only the public mode title may be read');
    return this._text;
  }
  set textContent(text) {
    assert.equal(this.tagName, 'STYLE', 'Only our new style may receive text');
    this._text = text;
  }
  getAttribute(name) {
    if (name === 'value') throw new Error('Private input attribute read is forbidden');
    return this.attributes[name] ?? null;
  }
  hasAttribute(name) { return Object.hasOwn(this.attributes, name); }
  setAttribute(name, value) {
    assert.equal(name, ATTRIBUTE, 'Only presentation attributes may change');
    this.attributes[name] = value;
    this.writes.push([name, value]);
  }
  removeAttribute(name) {
    assert.equal(name, ATTRIBUTE);
    delete this.attributes[name];
  }
  appendChild(node) {
    if (node.parentElement) node.remove();
    this.children.push(node);
    node.parentElement = this;
    return node;
  }
  remove() {
    if (!this.parentElement) return;
    this.parentElement.children = this.parentElement.children.filter(node => node !== this);
    this.parentElement = null;
  }
  contains(node) { return this === node || this.children.some(child => child.contains(node)); }
  matches(selector) { return matches(this, selector); }
  closest(selector) {
    for (let node = this; node; node = node.parentElement) if (node.matches(selector)) return node;
    return null;
  }
  querySelectorAll(selector) {
    const found = [];
    function visit(node) {
      for (const child of node.children) {
        if (child.matches(selector)) found.push(child);
        visit(child);
      }
    }
    visit(this);
    return found;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  getClientRects() {
    for (let node = this; node; node = node.parentElement) if (!node.rendered) return [];
    return [{}];
  }
}

function fixture(options = {}) {
  const html = new Element('html');
  const head = html.appendChild(new Element('head'));
  const body = html.appendChild(new Element('body'));
  const header = body.appendChild(new Element('header', {class: 'pageHeader___3FaDJ'}));
  const page = body.appendChild(new Element('div', {class: 'pageComponent___2BkvW'}));
  const contain = page.appendChild(new Element('div', {class: 'pageContain___3snYk'}));
  const root = new Element('div', {class: 'loginComponent___1mTUY'});
  const background = root.appendChild(new Element('img', {class: 'backgroundImg___AIwrQ'}));
  const layout = root.appendChild(new Element('div', {class: 'loginContain___3yi25'}));
  const bubble = layout.appendChild(new Element('img', {class: 'bubble1___2mY27'}));
  const marketing = layout.appendChild(new Element('div', {class: 'loginLeft___2omVj'}));
  const card = layout.appendChild(new Element('div', {class: 'loginForm___2LvyN'}));
  const title = card.appendChild(new Element('div', {class: 'loginTitle___3y1YZ'}, 'Sign In with SMS'));
  const form = card.appendChild(new Element('form', {name: 'PasswordLoginForm'}));
  const phoneItem = form.appendChild(new Element('div', {class: 'ant-form-item'}));
  const phone = phoneItem.appendChild(new Element('input', {type: 'tel'}));
  const codeItem = form.appendChild(new Element('div', {class: 'ant-form-item'}));
  const send = codeItem.appendChild(new Element('div', {class: 'sendCodeCom___qnsTR'}));
  const code = send.appendChild(new Element('input', {placeholder: 'SMS code', type: 'text'}));
  if (options.codeMaximum !== undefined) code.attributes.maxlength = options.codeMaximum;
  const resend = send.appendChild(new Element('span', {class: 'timeBox___M0k-r'}));
  const submit = form.appendChild(new Element('button', {type: 'submit'}));
  const footerPage = body.appendChild(new Element('footer', {class: 'pageFooter___lIB3B'}));
  const footer = footerPage.appendChild(new Element('div', {class: 'footerComponent___tkORO'}));
  const footerContent = footer.appendChild(new Element('div', {class: 'content___3QhJX'}));
  const footerImageBox = footerContent.appendChild(new Element('div', {class: 'imgBox___ZW4QJ'}));
  footerImageBox.appendChild(new Element('img'));
  const footerMenus = footerContent.appendChild(new Element('div', {class: 'right___FPWPF'}));
  for (let index = 0; index < 6; index += 1) {
    const column = footerMenus.appendChild(new Element('div', {class: 'menu___2cz5G'}));
    column.appendChild(new Element('span'));
    column.appendChild(new Element('ul'));
  }
  const footerRow = footer.appendChild(new Element('div', {class: 'footer___cQk2w'}));
  const footerLegal = footerRow.appendChild(new Element('div', {class: 'leftImg___2I0v5'}));
  const legal = footerLegal.appendChild(new Element('a', {class: 'term___23Qj1', href: '/privacy'}));
  const footerSocial = footerRow.appendChild(new Element('div', {class: 'rightImg___1ZBoU'}));
  for (let index = 0; index < (options.socialCount ?? 3); index += 1) footerSocial.appendChild(new Element('a')).appendChild(new Element('img'));
  if (!options.late) contain.appendChild(root);
  if (options.missing) code.remove();
  if (options.overlay) body.appendChild(options.overlay);
  const listeners = new Map();
  const observers = [];
  let current = new URL(options.url || 'https://my.dito.ph/');
  const window = {
    get location() { return current; },
    addEventListener(name, handler) { listeners.set(name, handler); },
  };
  window.top = options.subframe ? {} : window;
  for (const name of ['fetch', 'localStorage', 'sessionStorage']) {
    Object.defineProperty(window, name, {get() { throw new Error('Network/storage is forbidden'); }});
  }
  const document = {
    head, body,
    querySelectorAll(selector) { return html.querySelectorAll(selector); },
    createElement(tag) { assert.equal(tag, 'style'); return new Element(tag); },
    get cookie() { throw new Error('Cookie reads are forbidden'); },
  };
  class MutationObserver {
    constructor(callback) { this.callback = callback; this.connected = false; this.targets = []; observers.push(this); }
    observe(target, settings) {
      assert.equal(settings.subtree, true);
      if (target === body) assert.notEqual(settings.characterData, true);
      else {
        assert.equal(target, title, 'Text observation must be scoped to the public mode title');
        assert.equal(settings.characterData, true);
      }
      this.targets.push({target, settings});
      this.connected = true;
    }
    disconnect() { this.connected = false; }
  }
  const forbidden = () => { throw new Error('Logging/network/timers are forbidden'); };
  const context = {window, document, URL, MutationObserver, fetch: forbidden, setTimeout: forbidden, setInterval: forbidden, console: {log: forbidden, error: forbidden, warn: forbidden}};
  vm.runInNewContext(source, context, {timeout: 1000});
  return {
    window, document, body, head, root, layout, card, title, form, phone, code, resend, submit,
    header, page, contain, footerPage, footer, footerContent, footerMenus, footerRow, footerLegal, footerSocial, legal, marketing, background, bubble, observers,
    mutate() { for (const observer of observers) if (observer.connected) observer.callback([]); },
    event(name) { listeners.get(name)?.(); },
    navigate(url, event = 'popstate') { current = new URL(url, current); listeners.get(event)?.(); },
    focused() { return root.getAttribute(ATTRIBUTE) === 'root'; },
  };
}

test('recognized original SMS form is centered without cloning or touching controls/legal', () => {
  const f = fixture();
  assert.equal(f.focused(), true);
  assert.equal(f.code.getAttribute('maxlength'), null);
  assert.equal(fixture({codeMaximum: '6'}).focused(), true);
  assert.equal(f.head.children.length, 1);
  assert.match(f.head.children[0]._text, /padding: 0 !important/);
  assert.equal(f.marketing.getAttribute(ATTRIBUTE), 'hide');
  assert.equal(f.header.getAttribute(ATTRIBUTE), 'hide');
  assert.equal(f.contain.getAttribute(ATTRIBUTE), 'ancestor');
  assert.equal(f.page.getAttribute(ATTRIBUTE), 'ancestor');
  assert.equal(f.footerContent.getAttribute(ATTRIBUTE), 'hide');
  assert.equal(f.footerSocial.getAttribute(ATTRIBUTE), 'hide');
  assert.equal(fixture({socialCount: 4}).footerSocial.getAttribute(ATTRIBUTE), 'hide');
  assert.equal(fixture({socialCount: 5}).footerSocial.hasAttribute(ATTRIBUTE), false);
  assert.equal(f.footerLegal.getAttribute(ATTRIBUTE), 'footer-legal');
  assert.equal(f.legal.hasAttribute(ATTRIBUTE), false);
  assert.equal(f.legal.parentElement, f.footerLegal);
  assert.equal(f.card.parentElement, f.layout);
  assert.equal(f.form.parentElement, f.card);
  for (const control of [f.phone, f.code, f.resend, f.submit]) {
    assert.equal(control.writes.length, 0);
    assert.equal(f.form.contains(control), true);
  }
});

test('missing, duplicate, changed ancestry and password/reset mode remain normal', () => {
  assert.equal(fixture({missing: true}).focused(), false);
  const titleOnly = fixture();
  assert.equal(titleOnly.observers[0].targets.some(({target, settings}) => target === titleOnly.title && settings.characterData === true), true);
  titleOnly.title._text = 'Sign In with Password';
  titleOnly.observers[0].callback([{type: 'characterData', target: {parentElement: titleOnly.title}}]);
  assert.equal(titleOnly.focused(), false);
  assert.equal(titleOnly.head.children.length, 0);
  for (const change of [
    f => { f.title._text = 'Sign In with Password'; },
    f => { f.title._text = 'Forgot Password'; },
    f => { f.code.attributes.maxlength = '8'; },
    f => { f.phone.attributes.type = 'password'; },
    f => { f.page.attributes.class = 'changed-page'; },
    f => { f.layout.appendChild(new Element('section')); },
    f => { f.form.appendChild(new Element('input', {type: 'text'})); },
  ]) {
    const f = fixture();
    change(f);
    f.mutate();
    assert.equal(f.focused(), false);
    assert.equal(f.head.children.length, 0);
    assert.equal(f.marketing.hasAttribute(ATTRIBUTE), false);
  }
});

test('other origins, routes, URL credentials and subframes are inert', () => {
  for (const url of ['http://my.dito.ph/', 'https://other.example/', 'https://my.dito.ph:444/', 'https://user:secret@my.dito.ph/', 'https://my.dito.ph/pto/home', 'https://my.dito.ph/?x=1', 'https://my.dito.ph/#login']) {
    const f = fixture({url});
    assert.equal(f.focused(), false);
    assert.equal(f.observers.length, 0);
    assert.equal(f.window.__simManagerDitoLoginFocus, undefined);
  }
  assert.equal(fixture({subframe: true}).focused(), false);
  const f = fixture();
  f.navigate('/pto/home');
  assert.equal(f.focused(), false);
  assert.equal(f.header.hasAttribute(ATTRIBUTE), false);
});

test('late official card may focus; visible CAPTCHA/consent/security overlay restores all styling', () => {
  const late = fixture({late: true});
  assert.equal(late.focused(), false);
  late.contain.appendChild(late.root);
  late.mutate();
  assert.equal(late.focused(), true);
  for (const overlay of [new Element('div', {class: 'ant-modal-wrap'}), new Element('section', {role: 'dialog'}), new Element('iframe')]) {
    const initial = fixture({overlay});
    assert.equal(initial.focused(), false);
    assert.equal(initial.head.children.length, 0);
    overlay.remove();
    const f = fixture();
    f.body.appendChild(overlay);
    f.mutate();
    assert.equal(f.focused(), false);
    assert.equal(f.head.children.length, 0);
    assert.equal(overlay.parentElement, f.body);
    assert.equal(overlay.writes.length, 0);
    overlay.rendered = false;
    f.mutate();
    assert.equal(f.focused(), true);
    overlay.remove();
  }
});

test('a header containing form or required legal controls is never hidden', () => {
  for (const protectedNode of [new Element('input'), new Element('button'), new Element('a', {href: '/privacy-policy'}), new Element('div', {class: 'term___23Qj1'})]) {
    const f = fixture();
    f.header.appendChild(protectedNode);
    f.mutate();
    assert.equal(f.focused(), true);
    assert.equal(f.header.hasAttribute(ATTRIBUTE), false);
    assert.equal(protectedNode.writes.length, 0);
  }
  const protectedFooter = fixture();
  protectedFooter.footerContent.appendChild(new Element('a', {href: '/terms'}));
  protectedFooter.mutate();
  assert.equal(protectedFooter.footerContent.hasAttribute(ATTRIBUTE), false);
  assert.equal(protectedFooter.legal.hasAttribute(ATTRIBUTE), false);
  const changedFooter = fixture();
  changedFooter.footerMenus.children[0].appendChild(new Element('section'));
  changedFooter.footerSocial.appendChild(new Element('a'));
  changedFooter.mutate();
  assert.equal(changedFooter.footerContent.hasAttribute(ATTRIBUTE), false);
  assert.equal(changedFooter.footerSocial.hasAttribute(ATTRIBUTE), false);
});

test('manual full page and pagehide remove only owned styling and stop future work', () => {
  for (const stop of [f => f.window.__simManagerDitoLoginFocus.restore(), f => f.event('pagehide')]) {
    const f = fixture();
    for (let index = 0; index < 10; index += 1) f.mutate();
    assert.equal(f.head.children.length, 1);
    stop(f);
    f.mutate();
    f.event('hashchange');
    assert.equal(f.focused(), false);
    assert.equal(f.head.children.length, 0);
    assert.equal(f.observers.every(observer => !observer.connected), true);
    assert.equal(f.header.hasAttribute(ATTRIBUTE), false);
    assert.equal(f.footer.hasAttribute(ATTRIBUTE), false);
    assert.equal(f.form.contains(f.phone), true);
  }
});

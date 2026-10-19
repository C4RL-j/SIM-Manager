'use strict';
// Synthetic DOM, values and trusted events only; no network or real sign-in.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../src/sim_manager/carriers/dito/sms_helper.js'), 'utf8');

function matches(node, selector) {
  return selector.split(',').some(part => {
    let plain = part.trim();
    const attributes = [];
    plain = plain.replace(/\[([^\]=]+)="([^"]*)"\]/g, (_, name, value) => {
      attributes.push([name, value]);
      return '';
    });
    const classes = [];
    plain = plain.replace(/\.([A-Za-z0-9_-]+)/g, (_, name) => { classes.push(name); return ''; });
    return (!plain || plain.toLowerCase() === node.tagName.toLowerCase()) &&
      classes.every(name => (node.attributes.class || '').split(/\s+/).includes(name)) &&
      attributes.every(([name, value]) => node.attributes[name] === value);
  });
}

class Element {
  constructor(tag, attributes = {}, publicTitle = '') {
    this.tagName = tag.toUpperCase();
    this.attributes = {...attributes};
    this.children = [];
    this.parentElement = null;
    this._publicTitle = publicTitle;
    this.rendered = true;
    this.listeners = new Map();
    this.events = [];
    this.writes = [];
    this.disabled = false;
    this.readOnly = false;
  }
  get childElementCount() { return this.children.length; }
  get textContent() {
    assert.equal(this.attributes.class, 'loginTitle___3y1YZ', 'Only the public title may be read');
    return this._publicTitle;
  }
  getAttribute(name) {
    assert.notEqual(name, 'value', 'Private value attributes cannot be read');
    return this.attributes[name] ?? null;
  }
  hasAttribute(name) { return Object.hasOwn(this.attributes, name); }
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
    const visit = node => {
      for (const child of node.children) {
        if (child.matches(selector)) found.push(child);
        visit(child);
      }
    };
    visit(this);
    return found;
  }
  getClientRects() {
    for (let node = this; node; node = node.parentElement) if (!node.rendered) return [];
    return [{}];
  }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(listener);
  }
  removeEventListener(type, listener) {
    this.listeners.set(type, (this.listeners.get(type) || []).filter(item => item !== listener));
  }
  dispatchEvent(event) {
    if (!event.target) event.target = this;
    this.events.push(event.type);
    for (const listener of this.listeners.get(event.type) || []) listener(event);
    if (event.bubbles && this.parentElement) this.parentElement.dispatchEvent(event);
    return true;
  }
  click() { throw new Error('Automatic clicks are forbidden'); }
  submit() { throw new Error('Automatic submission is forbidden'); }
  requestSubmit() { throw new Error('Automatic submission is forbidden'); }
}

class NativeInput extends Element {
  constructor(attributes = {}) {
    super('input', attributes);
    // A React-like instance override must be bypassed, without reading it.
    Object.defineProperty(this, 'value', {
      get() { throw new Error('Reading a private field is forbidden'); },
      set() { throw new Error('Use the native setter for official React listeners'); },
    });
  }
  get value() { throw new Error('Reading a private field is forbidden'); }
  set value(value) { this.writes.push(value); }
}

class Event {
  constructor(type, options = {}) {
    this.type = type;
    this.bubbles = Boolean(options.bubbles);
    this.isTrusted = false;
  }
  preventDefault() { throw new Error('Do not interfere with official events'); }
  stopPropagation() { throw new Error('Do not interfere with official events'); }
}

function fixture(options = {}) {
  const html = new Element('html');
  const body = html.appendChild(new Element('body'));
  const root = body.appendChild(new Element('div', {class: 'loginComponent___1mTUY'}));
  const layout = root.appendChild(new Element('div', {class: 'loginContain___3yi25'}));
  const card = layout.appendChild(new Element('div', {class: 'loginForm___2LvyN'}));
  const title = card.appendChild(new Element('div', {class: 'loginTitle___3y1YZ'}, 'Sign In with SMS'));
  const form = card.appendChild(new Element('form'));
  const phoneItem = form.appendChild(new Element('div', {class: 'ant-form-item'}));
  const phone = phoneItem.appendChild(new NativeInput({type: 'text', placeholder: 'xxx xxx xxxx'}));
  const codeItem = form.appendChild(new Element('div', {class: 'ant-form-item'}));
  const send = codeItem.appendChild(new Element('div', {class: 'sendCodeCom___qnsTR'}));
  const code = send.appendChild(new NativeInput({type: 'text', placeholder: 'SMS code'}));
  const resend = send.appendChild(new Element('span', {class: 'timeBox___M0k-r send___2zLy_'}));
  const submit = form.appendChild(new Element('button', {type: 'submit'}));
  const document = new Element('document');
  document.appendChild(html);
  document.body = body;
  const window = new Element('window');
  window.location = {href: options.url || 'https://my.dito.ph/'};
  window.top = options.subframe ? {} : window;
  const context = vm.createContext({document, window, URL, HTMLInputElement: NativeInput, Event});
  // Any diagnostic, networking, clipboard or storage access fails the test.
  for (const name of ['console', 'fetch', 'XMLHttpRequest', 'localStorage', 'sessionStorage', 'navigator']) {
    Object.defineProperty(context, name, {get() { throw new Error('Private/external access is forbidden'); }});
    Object.defineProperty(window, name, {get() { throw new Error('Private/external access is forbidden'); }});
  }
  const install = () => vm.runInContext(source, context);
  install();
  const helper = window.__simManagerDitoSmsHelper;
  const click = (target = resend, trusted = true) => {
    const event = new Event('click');
    event.isTrusted = trusted;
    event.target = target;
    document.dispatchEvent(event);
  };
  const observe = () => JSON.parse(JSON.stringify(helper.observe()));
  return {document, window, body, root, layout, card, title, form, phoneItem,
    phone, codeItem, code, send, resend, submit, helper, click, observe, install};
}

test('only trusted clicks on the original available SMS request control advance its counter', () => {
  const f = fixture();
  assert.deepEqual(f.observe(), {request: 0, fillable: true});
  f.click(f.resend, false);
  f.click(f.code);
  f.click(f.phone);
  f.click(f.submit);
  const unrelated = f.body.appendChild(new Element('span', {class: 'timeBox___M0k-r'}));
  f.click(unrelated);
  assert.equal(f.observe().request, 0);
  f.resend.attributes['aria-disabled'] = 'true';
  f.click();
  delete f.resend.attributes['aria-disabled'];
  f.resend.attributes.disabled = '';
  f.click();
  delete f.resend.attributes.disabled;
  f.resend.attributes.class = 'timeBox___M0k-r countDown___3eXL4';
  f.click();
  f.resend.attributes.class = 'timeBox___M0k-r send___2zLy_ countDown___3eXL4';
  f.click();
  f.resend.attributes.class = 'timeBox___M0k-r';
  f.click();
  assert.equal(f.observe().request, 0, 'countdown, conflicting and unknown states cannot start a request');
  f.resend.attributes.class = 'timeBox___M0k-r send___2zLy_';
  f.click();
  f.click(f.resend.appendChild(new Element('span')));
  assert.equal(f.observe().request, 2);
  assert.deepEqual(f.code.writes, []);
  assert.deepEqual(f.phone.writes, []);
  assert.deepEqual(f.form.events, []);
});

test('explicit current-request fill uses the native setter and official input/change handlers only', () => {
  const f = fixture();
  const official = [];
  f.form.addEventListener('input', event => official.push([event.type, event.target === f.code, event.bubbles]));
  f.form.addEventListener('change', event => official.push([event.type, event.target === f.code, event.bubbles]));
  assert.equal(f.helper.fill('123456', 0), false);
  f.click();
  f.resend.attributes.class = 'timeBox___M0k-r countDown___3eXL4';
  f.click();
  assert.deepEqual(f.observe(), {request: 1, fillable: true});
  assert.equal(f.helper.fill('123456', 1), true);
  assert.deepEqual(f.code.writes, ['123456']);
  assert.deepEqual(f.phone.writes, []);
  assert.deepEqual(official, [['input', true, true], ['change', true, true]]);
  assert.deepEqual(f.form.events, ['input', 'change']);
  assert.deepEqual(f.submit.events, []);
  f.resend.attributes.class = 'timeBox___M0k-r send___2zLy_';
  f.click();
  assert.equal(f.helper.fill('654321', 1), false, 'old request cannot replay after another SMS request');
  assert.equal(f.helper.fill('654321', 2), true);
  for (const [code, request] of [['12345', 2], ['1234567', 2], ['abcdef', 2], ['１２３４５６', 2],
    ['123456\n', 2], [123456, 2], ['123456', '2'], ['123456', 2.1], ['123456', NaN]]) {
    assert.equal(f.helper.fill(code, request), false);
  }
  assert.equal(f.code.writes.length, 2);
});

test('changed modes, ambiguous controls, hidden/disabled fields and unfamiliar structure fail safely', () => {
  const changes = [
    f => { f.title._publicTitle = 'Sign In with Password'; },
    f => { f.title.appendChild(new Element('span')); },
    f => { f.card.appendChild(new Element('form')); },
    f => { f.form.appendChild(new NativeInput()); },
    f => { f.send.appendChild(new NativeInput({placeholder: 'SMS code'})); },
    f => { f.send.appendChild(new Element('span', {class: 'timeBox___M0k-r'})); },
    f => { f.form.appendChild(new Element('button', {type: 'submit'})); },
    f => { f.phone.attributes.type = 'password'; },
    f => { f.code.attributes.type = 'password'; },
    f => { f.code.attributes.maxlength = '8'; },
    f => { f.code.disabled = true; },
    f => { f.code.readOnly = true; },
    f => { f.phone.rendered = false; },
    f => { f.code.rendered = false; },
    f => { f.resend.rendered = false; },
    f => { f.submit.rendered = false; },
    f => { f.layout.remove(); },
    f => { f.root.appendChild(f.card); },
    f => { f.phoneItem.appendChild(f.send); },
    f => { f.body.appendChild(new Element('div', {class: 'loginComponent___1mTUY'})); },
  ];
  for (const change of changes) {
    const f = fixture();
    f.click();
    change(f);
    assert.equal(f.observe().fillable, false);
    assert.equal(f.helper.fill('123456', 1), false);
    f.click();
    assert.equal(f.observe().request, 1);
    assert.deepEqual(f.code.writes, []);
    assert.deepEqual(f.phone.writes, []);
  }
  const known = fixture();
  known.code.attributes.maxlength = '6';
  known.click();
  assert.equal(known.helper.fill('123456', 1), true);
});

test('visible security/consent surfaces disable helper without mutating the official page', () => {
  for (const [tag, attributes] of [['iframe', {}], ['dialog', {}], ['div', {role: 'dialog'}],
    ['div', {'aria-modal': 'true'}], ['div', {class: 'ant-modal-mask'}], ['div', {class: 'ant-drawer'}]]) {
    const f = fixture();
    f.click();
    const challenge = f.body.appendChild(new Element(tag, attributes));
    assert.deepEqual(f.observe(), {request: 1, fillable: false});
    assert.equal(f.helper.fill('123456', 1), false);
    f.click();
    assert.equal(f.observe().request, 1);
    challenge.rendered = false;
    assert.equal(f.observe().fillable, true);
    assert.equal(f.helper.fill('123456', 1), true);
    assert.equal(challenge.parentElement, f.body);
  }
  const crowded = fixture();
  crowded.click();
  for (let i = 0; i < 33; i += 1) {
    const dialog = crowded.body.appendChild(new Element('dialog'));
    dialog.rendered = false;
  }
  assert.equal(crowded.observe().fillable, false);
});

test('exact official root/main-frame restriction, repeated installation and page hide preserve isolation', () => {
  for (const options of [{url: 'http://my.dito.ph/'}, {url: 'https://my.dito.ph.evil.test/'},
    {url: 'https://my.dito.ph:444/'}, {url: 'https://user:pass@my.dito.ph/'},
    {url: 'https://my.dito.ph/pto/home'}, {url: 'https://my.dito.ph/?x=1'},
    {url: 'https://my.dito.ph/#login'}, {subframe: true}]) {
    assert.equal(fixture(options).helper, undefined);
  }
  const f = fixture({url: 'https://my.dito.ph:443/'});
  f.install();
  assert.equal(f.window.__simManagerDitoSmsHelper, f.helper);
  f.click();
  assert.equal(f.observe().request, 1, 'only one capture handler exists');
  f.window.location.href = 'https://my.dito.ph/pto/home';
  assert.equal(f.observe().fillable, false);
  assert.equal(f.helper.fill('123456', 1), false);
  f.window.location.href = 'https://my.dito.ph/';
  f.window.dispatchEvent(new Event('pagehide'));
  f.click();
  assert.deepEqual(f.observe(), {request: 1, fillable: false});
  assert.equal(f.helper.fill('123456', 1), false);
});

test('privacy guards and unexpected page exceptions expose metadata only and never submit', () => {
  const f = fixture();
  f.click();
  assert.deepEqual(Object.keys(f.helper).sort(), ['fill', 'observe']);
  assert.deepEqual(Object.keys(f.observe()).sort(), ['fillable', 'request']);
  f.code.getClientRects = () => { throw new Error('synthetic private page error'); };
  assert.deepEqual(f.observe(), {request: 1, fillable: false});
  assert.equal(f.helper.fill('123456', 1), false);
  f.click();
  assert.equal(f.observe().request, 1);
  assert.deepEqual(f.code.writes, []);
  assert.deepEqual(f.phone.writes, []);
  assert.deepEqual(f.form.events, []);
  assert.doesNotMatch(source, /(?:console\.|fetch\(|XMLHttpRequest|localStorage|sessionStorage|clipboard|\.value\b|\.click\(|\.submit\(|requestSubmit\()/);
  assert.doesNotMatch(source, /\.textContent\s*=/, 'helper does not change page text or styling');
});

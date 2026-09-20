// Concept-free DOM construction and structural composition.

const flat = values => values.flat(Infinity).filter(value => value != null && value !== false);

function requireDocument(document) {
  if (!document || typeof document.createElement !== 'function' || typeof document.createTextNode !== 'function') {
    throw new Error('WebGUI requires a DOM-compatible document');
  }
  return document;
}

function isNode(value) {
  return value != null && typeof value === 'object' && Number.isInteger(value.nodeType);
}

function child(document, value) {
  return isNode(value) ? value : document.createTextNode(String(value));
}

class DOMStructure {
  constructor({ document = globalThis.document } = {}) {
    this.document = requireDocument(document);
    this.listeners = [];
  }

  h(tag, props = {}, children = []) {
    const node = this.document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (value == null) continue;
      if (key === 'innerHTML') throw new Error('WebGUI does not accept innerHTML; compose nodes or use text');
      if (key === 'className') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key === 'dataset') Object.assign(node.dataset, value);
      else if (key === 'style') Object.assign(node.style, value);
      else if (key === 'on') {
        for (const [event, handler] of Object.entries(value)) {
          if (typeof handler !== 'function') throw new Error(`WebGUI event handler ${event} must be a function`);
          node.addEventListener(event, handler);
          this.listeners.push(() => node.removeEventListener(event, handler));
        }
      } else if (key === 'attrs') {
        for (const [name, attribute] of Object.entries(value)) node.setAttribute(name, attribute);
      } else if (key in node) node[key] = value;
      else node.setAttribute(key, value);
    }
    node.append(...flat([children]).map(value => child(this.document, value)));
    return node;
  }

  button(text, props = {}, children = []) {
    return this.h('button', { type: 'button', ...props, dataset: { ui: 'button', ...(props.dataset ?? {}) } }, children.length ? children : text);
  }
  input(props = {}) { return this.h('input', { ...props, dataset: { ui: 'input', ...(props.dataset ?? {}) } }); }
  select(props = {}, children = []) { return this.h('select', { ...props, dataset: { ui: 'select', ...(props.dataset ?? {}) } }, children); }
  option(value, text, props = {}) { return this.h('option', { ...props, value, text }); }
  textarea(props = {}) { return this.h('textarea', { ...props, dataset: { ui: 'textarea', ...(props.dataset ?? {}) } }); }
  field(text, control, props = {}) { return this.h('label', { ...props, dataset: { ui: 'field', ...(props.dataset ?? {}) } }, [text, control]); }
  row(children, props = {}) { return this.h('div', { ...props, dataset: { ui: 'row', ...(props.dataset ?? {}) } }, children); }
  stack(children, props = {}) { return this.h('div', { ...props, dataset: { ui: 'stack', ...(props.dataset ?? {}) } }, children); }
  dialog({ id, title, children = [], dataset = {}, className = '' } = {}) {
    const card = this.h('div', { className, dataset: { ui: 'dialog-card' }, attrs: { role: 'document' } }, [this.h('h3', { text: title ?? '' }), children]);
    return this.h('div', { id, hidden: true, dataset: { ui: 'dialog', ...dataset }, attrs: { role: 'dialog', 'aria-modal': 'true' } }, [card]);
  }
  replace(parent, children = []) {
    parent.replaceChildren(...flat([children]).map(value => child(this.document, value)));
    return parent;
  }
  mount(parent, children) {
    parent.append(...flat([children]).map(value => child(this.document, value)));
    return children;
  }
  vars(node, values) {
    for (const [name, value] of Object.entries(values)) node.style.setProperty(`--${name}`, value);
    return node;
  }
  show(node) { node.hidden = false; return node; }
  hide(node) { node.hidden = true; return node; }
  destroy() {
    for (const dispose of this.listeners.splice(0)) dispose();
  }
}

export { DOMStructure, flat };

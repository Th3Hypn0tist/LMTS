import { WebGUI } from '../WebGUI/webgui.js';

const gui = new WebGUI({ theme: null });
const root = document.querySelector('#app');

function h(tag, props = {}, children = []) {
  return gui.h(tag, props, children);
}

function replaceRoot(children) {
  gui.replace(root, children);
}

function stat(value, label, tone = '') {
  return h('div', { className: 'stat' + (tone ? ' ' + tone : '') }, [
    h('strong', { text: String(value) }),
    h('span', { text: label }),
  ]);
}

function statusPill(value) {
  const labels = {
    compatible: 'Compatible',
    partial: 'Partial',
    fail: 'Failed',
    unknown: 'Unknown',
  };
  return h('span', { className: 'status status-' + value }, [
    h('i'),
    h('span', { text: labels[value] || value }),
  ]);
}

function selectControl(label, value, options, onChange) {
  const select = h('select', {
    value: value || '',
    on: { change: event => onChange(event.target.value) },
  }, options.map(item => h('option', {
    value: item.value,
    text: item.label,
    selected: String(item.value) === String(value || ''),
  })));

  return h('label', { className: 'control' }, [
    h('span', { text: label }),
    select,
  ]);
}

export { h, replaceRoot, selectControl, stat, statusPill };

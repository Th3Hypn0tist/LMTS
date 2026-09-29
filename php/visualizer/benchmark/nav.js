import { h } from './ui.js';

function brand(section) {
  return h('div', { className: 'brand' }, [
    h('a', { className: 'brand-logo', href: '/', title: 'AIGM' }, [
      h('img', { src: '/images/AIGM-LOGO.png', alt: 'AIGM' }),
    ]),
    h('span', { className: 'brand-divider' }),
    h('a', { className: 'brand-lmts', href: '/lmts/', text: 'LMTS' }),
    h('span', { className: 'brand-section', text: section }),
  ]);
}

function topbar(active = 'benchmark', section = 'Benchmark') {
  const items = [
    ['benchmark', '/lmts/', 'Benchmark'],
    ['systems', '/lmts/systems/', 'Systems'],
    ['rankings', '/lmts/rankings/', 'Rankings'],
  ];

  return h('header', { className: 'topbar' }, [
    brand(section),
    h('nav', { className: 'nav' }, items.map(([id, href, label]) =>
      h('a', {
        className: active === id ? 'active' : '',
        href,
        text: label,
      })
    )),
  ]);
}

function topbarRoot(active = 'benchmark', section = 'Benchmark') {
  return topbar(active, section);
}

export { topbar, topbarRoot };

import { h } from './ui.js';

function brand(breadcrumb) {
  return h('div', { className: 'brand' }, [
    h('a', { className: 'brand-logo', href: '/', title: 'AIGM' }, [
      h('img', { src: '/images/AIGM-LOGO.png', alt: 'AIGM' }),
    ]),
    h('span', { className: 'brand-divider' }),
    h('a', { className: 'brand-lmts', href: '/lmts', text: 'LMTS' }),
    h('span', { className: 'breadcrumb', text: '/ ' + breadcrumb }),
  ]);
}

function topbar(active = 'benchmark', breadcrumb = 'Benchmark') {
  const items = [
    ['benchmark', '../', 'Benchmark'],
    ['systems', '../systems/', 'Systems'],
    ['rankings', '../rankings/', 'Rankings'],
  ];

  return h('header', { className: 'topbar' }, [
    brand(breadcrumb),
    h('nav', { className: 'nav' }, items.map(([id, href, label]) =>
      h('a', {
        className: active === id ? 'active' : '',
        href,
        text: label,
      })
    )),
  ]);
}

function topbarRoot(active = 'benchmark', breadcrumb = 'Benchmark') {
  const items = [
    ['benchmark', './', 'Benchmark'],
    ['systems', './systems/', 'Systems'],
    ['rankings', './rankings/', 'Rankings'],
  ];

  return h('header', { className: 'topbar' }, [
    brand(breadcrumb),
    h('nav', { className: 'nav' }, items.map(([id, href, label]) =>
      h('a', {
        className: active === id ? 'active' : '',
        href,
        text: label,
      })
    )),
  ]);
}

export { topbar, topbarRoot };

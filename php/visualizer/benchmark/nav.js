import { h } from './ui.js';

function topbar(active = 'benchmark') {
  const items = [
    ['benchmark', '../', 'Benchmark'],
    ['systems', '../systems/', 'Systems'],
    ['rankings', '../rankings/', 'Rankings'],
  ];

  return h('header', { className: 'topbar' }, [
    h('a', { className: 'brand', href: '/', title: 'AIGM' }, [
      h('img', { src: '/images/AIGM-LOGO.png', alt: 'AIGM' }),
      h('span', { className: 'brand-divider' }),
      h('span', { text: 'LMTS' }),
      h('span', { className: 'breadcrumb', text: '/ Benchmark' }),
    ]),
    h('nav', { className: 'nav' }, items.map(([id, href, label]) =>
      h('a', {
        className: active === id ? 'active' : '',
        href,
        text: label,
      })
    )),
  ]);
}

function topbarRoot(active = 'benchmark') {
  const items = [
    ['benchmark', './', 'Benchmark'],
    ['systems', './systems/', 'Systems'],
    ['rankings', './rankings/', 'Rankings'],
  ];

  return h('header', { className: 'topbar' }, [
    h('a', { className: 'brand', href: '/', title: 'AIGM' }, [
      h('img', { src: '/images/AIGM-LOGO.png', alt: 'AIGM' }),
      h('span', { className: 'brand-divider' }),
      h('span', { text: 'LMTS' }),
      h('span', { className: 'breadcrumb', text: '/ Benchmark' }),
    ]),
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

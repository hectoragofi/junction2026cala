import { api, initApi, state as apiState } from './api.js';
import { $, esc, installGlobal, closeSheet, closeLayer, hideTip, closeModals } from './ui.js';
import { openAsk, renderAskPage } from './views/ask.js';

const app = $('#app');
export const store = { portfolio: null };

const ICONS = {
  feed: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M4 5h12M4 10h12M4 15h7"/></svg>',
  map: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="10" cy="10" r="2.2"/><circle cx="4" cy="5" r="1.6"/><circle cx="16" cy="5" r="1.6"/><circle cx="15" cy="16" r="1.6"/><path d="M8.2 8.8 5.3 6.1M11.8 8.8l2.9-2.7M11.4 11.8l2.6 2.8"/></svg>',
  check: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3.5" y="3.5" width="13" height="13" rx="4"/><path d="m7 10 2 2 4-4"/></svg>',
  ask: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="9" cy="9" r="5.5"/><path d="M13 13l4 4"/></svg>',
};
const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

export function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }

function renderChrome(active) {
  const hasPf = !!store.portfolio?.companies?.length;
  const bare = active === 'start' && !hasPf;
  const link = (k, label, href) => `<a href="${href}" class="${active === k ? 'on' : ''}" ${active === k ? 'aria-current="page"' : ''}>${label}</a>`;
  $('#hdr').className = 'hdr' + (bare ? ' bare' : '');
  $('#hdr').innerHTML = `<div class="hdr-in${active === 'map' ? '' : ''}">
    <a href="#/" class="logo" aria-label="Perimeter home"><span class="logo-mark"></span>Perimeter</a>
    ${hasPf ? `<nav class="seg" aria-label="Main">${link('feed', 'Feed', '#/')}${link('map', 'Map', '#/map')}${link('check', 'Check', '#/check')}</nav>` : ''}
    <div class="hdr-right">
      ${apiState.mock ? `<span class="mockbadge" title="${esc(apiState.reason)}">Demo data</span>` : ''}
      <button type="button" class="askbtn" data-open-ask>Ask anything <kbd class="kbd">${isMac ? '⌘' : 'Ctrl'} K</kbd></button>
      <button type="button" class="iconbtn" data-open-ask aria-label="Ask anything">${ICONS.ask.replace('<svg', '<svg width="18" height="18"')}</button>
    </div></div>`;
  const tb = $('#tabbar');
  if (bare) { tb.innerHTML = ''; tb.style.display = 'none'; return; }
  tb.style.display = '';
  const t = (k, label, href) => `<a href="${href}" class="${active === k ? 'on' : ''}" ${active === k ? 'aria-current="page"' : ''}>${ICONS[k]}${label}</a>`;
  tb.innerHTML = (hasPf ? t('feed', 'Feed', '#/') + t('map', 'Map', '#/map') : t('feed', 'Start', '#/')) + t('check', 'Check', '#/check') + `<a href="#/ask" class="${active === 'ask' ? 'on' : ''}">${ICONS.ask}Ask</a>`;
}

let cleanup = null;
let routeSeq = 0;
async function route() {
  const seq = ++routeSeq;
  cleanup?.(); cleanup = null;
  closeSheet(); closeLayer(); hideTip(); closeModals();
  const raw = location.hash.replace(/^#/, '') || '/';
  const [pathPart, query = ''] = raw.split('?');
  const qs = new URLSearchParams(query);
  const parts = pathPart.split('/').filter(Boolean);
  const name = parts[0] || '';
  const ctx = { app, qs, parts, store, go, isCurrent: () => seq === routeSeq, onCleanup: fn => { cleanup = fn; } };
  window.scrollTo(0, 0);

  if (name === '' || name === 'feed') {
    if (!store.portfolio) {
      try { store.portfolio = await api.portfolio(); } catch { store.portfolio = { companies: [], building: false }; }
      if (seq !== routeSeq) return;
    }
    const pf = store.portfolio;
    if (!pf.companies?.length && !pf.building) {
      renderChrome('start');
      return (await import('./views/start.js')).render(ctx);
    }
    if (pf.building) {
      renderChrome('feed');
      return (await import('./views/start.js')).renderBuilding(ctx);
    }
    renderChrome('feed');
    return (await import('./views/feed.js')).render(ctx);
  }
  if (name === 'start') { renderChrome('start'); return (await import('./views/start.js')).render(ctx); }
  if (name === 'map') { await ensurePortfolio(); if (seq !== routeSeq) return; renderChrome('map'); return (await import('./views/map.js')).render(ctx); }
  if (name === 'check') { await ensurePortfolio(); if (seq !== routeSeq) return; renderChrome('check'); return (await import('./views/check.js')).render(ctx); }
  if (name === 'ask') { await ensurePortfolio(); if (seq !== routeSeq) return; renderChrome('ask'); return renderAskPage(ctx); }
  renderChrome('');
  app.innerHTML = `<main class="main"><div class="card state"><b>Page not found</b><span>That link doesn’t go anywhere.</span><a class="btn" href="#/">Back to feed</a></div></main>`;
}
async function ensurePortfolio() {
  if (store.portfolio) return;
  try { store.portfolio = await api.portfolio(); } catch { store.portfolio = { companies: [], building: false }; }
}
export async function refreshPortfolio() {
  try { store.portfolio = await api.portfolio(); } catch {}
  return store.portfolio;
}

async function boot() {
  app.innerHTML = `<main class="main"><div class="ph"><div class="sk" style="height:32px;width:240px"></div><div class="sk sk-line" style="width:380px;margin-top:8px"></div></div><div class="sk" style="height:140px;border-radius:14px"></div><div class="sk" style="height:140px;border-radius:14px"></div></main>`;
  await initApi();
  installGlobal({ onAsk: q => openAsk(q) });
  document.addEventListener('click', e => {
    if (e.target.closest('[data-open-ask]')) { e.preventDefault(); openAsk(); }
  });
  document.addEventListener('keydown', e => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openAsk(); }
    else if (e.key === '/' && !/INPUT|TEXTAREA/.test(document.activeElement?.tagName) && !document.querySelector('.scrim')) { e.preventDefault(); openAsk(); }
  });
  addEventListener('hashchange', route);
  route();
}
boot();

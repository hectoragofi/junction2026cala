import { api, initApi, state as apiState, who, setView } from './api.js';
import { $, esc, initials, installGlobal, closeSheet, closeLayer, hideTip, closeModals, openMenu, toast } from './ui.js';
import { openAsk, renderAskPage } from './views/ask.js';

const app = $('#app');
// portfolio = /api/portfolio of the space being viewed; me = /api/profile (own profile + what is being viewed)
export const store = { portfolio: null, me: null };

const ICONS = {
  feed: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M4 5h12M4 10h12M4 15h7"/></svg>',
  map: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="10" cy="10" r="2.2"/><circle cx="4" cy="5" r="1.6"/><circle cx="16" cy="5" r="1.6"/><circle cx="15" cy="16" r="1.6"/><path d="M8.2 8.8 5.3 6.1M11.8 8.8l2.9-2.7M11.4 11.8l2.6 2.8"/></svg>',
  check: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="3.5" y="3.5" width="13" height="13" rx="4"/><path d="m7 10 2 2 4-4"/></svg>',
  ask: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="9" cy="9" r="5.5"/><path d="M13 13l4 4"/></svg>',
  user: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="10" cy="7" r="3.2"/><path d="M3.8 17c.9-3.2 3.3-4.8 6.2-4.8s5.3 1.6 6.2 4.8"/></svg>',
};
const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

export function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }

// ---------- profile helpers ----------
export const hasProfile = () => !!store.me?.exists;
export const viewingDemo = () => !hasProfile() || who.view === 'demo';
export const myProfile = () => store.me?.profile || null;
/** The seat of what is on screen: the demo is an investor portfolio. */
export const seat = () => viewingDemo() ? 'investor' : (myProfile()?.role || 'investor');
export const myCompany = () => seat() === 'founder' ? (myProfile()?.my_company || store.portfolio?.companies?.[0] || null) : null;
export function profileLabel(p = myProfile()) {
  if (!p) return 'Demo portfolio';
  return p.name || (p.role === 'founder' ? p.my_company?.name : p.fund_or_company_name) || (p.role === 'founder' ? 'Founder' : 'Investor');
}
export async function loadMe() {
  try { store.me = await api.profile(); } catch { store.me = store.me || { exists: false, profile: null }; }
  if (!store.me.exists && who.view !== 'demo') setView('me');
  return store.me;
}
/** Switch between the shared demo and the visitor's own profile. */
export async function switchView(v, { to = '#/' } = {}) {
  setView(v);
  store.portfolio = null;
  await loadMe();
  go(to);
}

function whoMenu(btn) {
  const items = [];
  if (hasProfile()) {
    items.push({ label: 'Profile and settings', k: 'profile' });
    items.push(who.view === 'demo' ? { label: 'Back to my profile', k: 'me' } : { label: 'Explore the demo', k: 'demo' });
  } else {
    items.push({ label: 'Make it yours', k: 'welcome' });
    items.push({ label: 'Profile and settings', k: 'profile' });
  }
  openMenu(btn, items, it => {
    if (it.k === 'profile') go('#/profile');
    else if (it.k === 'welcome') go('#/welcome');
    else switchView(it.k);
  });
}

export function renderChrome(active) {
  const hasPf = !!store.portfolio?.companies?.length;
  const bare = active === 'welcome' || (active === 'start' && !hasPf);
  const demo = viewingDemo();
  const founder = seat() === 'founder';
  const link = (k, label, href) => `<a href="${href}" class="${active === k ? 'on' : ''}" ${active === k ? 'aria-current="page"' : ''}>${label}</a>`;
  const label = demo ? 'Demo portfolio' : profileLabel();
  const av = demo ? ICONS.user.replace('<svg', '<svg width="16" height="16"') : esc(initials(label));
  $('#hdr').className = 'hdr' + (bare ? ' bare' : '');
  $('#hdr').innerHTML = `<div class="hdr-in">
    <a href="#/" class="logo" aria-label="Perimeter home"><span class="logo-mark"></span>Perimeter</a>
    ${hasPf && !bare ? `<nav class="seg" aria-label="Main">${link('feed', 'Feed', '#/')}${link('map', 'Map', '#/map')}${link('check', 'Check', '#/check')}<a href="/ask">Ask</a></nav>` : ''}
    <div class="hdr-right">
      ${apiState.mock ? `<span class="mockbadge" title="${esc(apiState.reason)}">Demo data</span>` : ''}
      ${bare ? '' : `<button type="button" class="askbtn" data-open-ask>Ask anything <kbd class="kbd">${isMac ? '⌘' : 'Ctrl'} K</kbd></button>
      <button type="button" class="iconbtn" data-open-ask aria-label="Ask anything">${ICONS.ask.replace('<svg', '<svg width="18" height="18"')}</button>`}
      ${bare && !hasProfile() ? '' : `<button type="button" class="who${active === 'profile' ? ' on' : ''}" id="whoBtn" aria-haspopup="menu" aria-label="Profile: ${esc(label)}${demo ? ' (demo)' : ''}">
        <span class="who-av${demo ? ' demo' : founder ? ' f' : ''}">${av}</span>
        <span class="who-t">${esc(label)}</span>${demo ? '<span class="demo-badge">Demo</span>' : ''}</button>`}
    </div></div>`;
  $('#whoBtn') && ($('#whoBtn').onclick = e => whoMenu(e.currentTarget));
  const tb = $('#tabbar');
  if (bare) { tb.innerHTML = ''; tb.style.display = 'none'; return; }
  tb.style.display = '';
  const t = (k, label, href) => `<a href="${href}" class="${active === k ? 'on' : ''}" ${active === k ? 'aria-current="page"' : ''}>${ICONS[k]}${label}</a>`;
  tb.innerHTML = (hasPf ? t('feed', founder ? 'Home' : 'Feed', '#/') + t('map', 'Map', '#/map') : t('feed', 'Start', '#/')) + t('check', 'Check', '#/check') + `<a href="/ask">${ICONS.ask}Ask</a>`;
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

  if (name === 'welcome' || name === 'start') {
    renderChrome('welcome');
    return (await import('./views/welcome.js')).render(ctx);
  }
  if (name === 'profile') {
    await ensurePortfolio(); if (seq !== routeSeq) return;
    renderChrome('profile');
    return (await import('./views/profile.js')).render(ctx);
  }
  if (name === '' || name === 'feed') {
    // New visitors start with onboarding; "Explore the demo" sets the demo view.
    if (!hasProfile() && who.view !== 'demo') { renderChrome('welcome'); return (await import('./views/welcome.js')).render(ctx); }
    await ensurePortfolio(); if (seq !== routeSeq) return;
    const pf = store.portfolio;
    if (!pf.companies?.length && !pf.building) {
      if (viewingDemo()) {  // fresh server: the demo portfolio has never been built
        try { await api.demo(); store.portfolio = { companies: [], building: true }; } catch (e) { toast('Couldn’t load the demo: ' + e.message); }
        if (seq !== routeSeq) return;
        renderChrome('feed');
        return (await import('./views/start.js')).renderBuilding(ctx);
      }
      renderChrome('feed');
      app.innerHTML = `<main class="main"><div class="card state in"><span class="ic">+</span><b>Nothing to watch yet</b><span>${seat() === 'founder' ? 'Add your company to see your rivals and the investors around you.' : 'Add the companies you back to start watching their perimeter.'}</span><a class="btn dark" href="#/profile">${seat() === 'founder' ? 'Add your company' : 'Add companies'}</a></div></main>`;
      return;
    }
    if (pf.building && !(pf.status || []).some(x => x.status !== 'mapping')) {
      renderChrome('feed');
      return (await import('./views/start.js')).renderBuilding(ctx);
    }
    renderChrome('feed');
    return (await import('./views/feed.js')).render(ctx);
  }
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
  app.innerHTML = `<main class="main"><div class="ph"><div class="sk" style="height:32px;width:240px"></div><div class="sk sk-line" style="width:380px;max-width:80vw;margin-top:8px"></div></div><div class="sk" style="height:140px;border-radius:14px"></div><div class="sk" style="height:140px;border-radius:14px"></div></main>`;
  await initApi();
  await loadMe();
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

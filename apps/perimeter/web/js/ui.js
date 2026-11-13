// Shared render helpers, chips, popovers, modal, sheet, toast.
import { api } from './api.js';

export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];

export function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function parseDate(d) {
  if (!d) return null;
  const m = /^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?/.exec(d);
  if (!m) return null;
  return new Date(+m[1], m[2] ? +m[2] - 1 : 0, m[3] ? +m[3] : 1);
}
// "12 Nov" this year, "12 Nov 2025" otherwise, "2024" for year-only.
export function fmtDate(d, { year = 'auto' } = {}) {
  if (!d) return '';
  if (/^\d{4}$/.test(d)) return d;
  const x = parseDate(d);
  if (!x) return String(d);
  if (/^\d{4}-\d{2}$/.test(d)) return year === true || x.getFullYear() !== new Date().getFullYear() ? `${MONTHS[x.getMonth()]} ${x.getFullYear()}` : MONTHS[x.getMonth()];
  const showY = year === true || (year === 'auto' && x.getFullYear() !== new Date().getFullYear());
  return `${x.getDate()} ${MONTHS[x.getMonth()]}${showY ? ' ' + x.getFullYear() : ''}`;
}
export function fmtMonth(d) {
  if (!d) return '—';
  if (/^\d{4}$/.test(d)) return d;
  const x = parseDate(d);
  return x ? `${MONTHS[x.getMonth()]} ${x.getFullYear()}` : esc(d);
}
export function fmtNum(n) { return (n ?? 0).toLocaleString('en-US'); }
export function initials(name) {
  return String(name || '?').replace(/[^\p{L}\p{N} ]/gu, '').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '?';
}
export function host(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return ''; }
}
// Cala sometimes returns registry-style ALL-CAPS names; show them in title case.
export function nm(name) {
  const n = String(name ?? '');
  if (n.length < 5 || n !== n.toUpperCase() || !/[A-Z]/.test(n)) return n;
  return n.split(/(\s+)/).map(w => (w.replace(/[^A-Z]/g, '').length <= 3 ? w : w[0] + w.slice(1).toLowerCase())).join('');
}
export function plural(n, one, many = one + 's') { return `${n} ${n === 1 ? one : many}`; }

// ---------- registries so chips can carry rich objects through innerHTML ----------
const reg = new Map();
let regId = 0;
export function keep(obj) { const id = 'r' + (++regId); reg.set(id, obj); return id; }
export function lookup(id) { return reg.get(id); }

function srcLabel(s) {
  const parts = [s.name || host(s.url) || 'Source'];
  if (s.date) parts.push(fmtDate(s.date));
  return parts.join(' · ');
}
export function srcChip(s) {
  if (!s) return '';
  return `<button type="button" class="src" data-src="${keep(s)}" aria-haspopup="dialog" title="${esc(srcLabel(s))}">${esc(srcLabel(s))}</button>`;
}
// Up to `max` chips, then a "+N" chip that opens a list popover.
export function srcChips(list, max = 2) {
  list = (list || []).filter(Boolean);
  if (!list.length) return '';
  const head = list.slice(0, max).map(srcChip).join('');
  const rest = list.slice(max);
  return head + (rest.length ? `<button type="button" class="src" data-srcs="${keep(rest)}" aria-haspopup="dialog">+${rest.length}</button>` : '');
}
export function entLink(ref, label) {
  if (!ref || !ref.name) return '';
  if (!ref.id) return esc(label ?? ref.name);
  return `<button type="button" class="ent" data-ent="${keep(ref)}">${esc(label ?? nm(ref.name))}</button>`;
}
export function avatar(ref) {
  const t = (ref.type || '').toLowerCase();
  const cls = t === 'company' ? 'co' : t === 'investor' ? 'inv' : '';
  return `<span class="av ${cls}" aria-hidden="true">${esc(initials(ref.name))}</span>`;
}
export function entChip(ref) {
  return `<button type="button" class="echip" data-ent="${keep(ref)}">${avatar(ref)}${esc(nm(ref.name))}</button>`;
}
export function entPill(ref, label, cls = 'n', extra = '') {
  return `<button type="button" class="pill ${cls}" data-ent="${keep(ref)}" ${extra}>${esc(label ?? nm(ref.name))}</button>`;
}
export function tipAttr(text) { return `data-tip="${esc(text)}"`; }

// ---------- severity / status labels ----------
export function sevPill(sev, high = 'High') {
  if (sev === 'high') return `<span class="pill hi">${high}</span>`;
  if (sev === 'medium') return `<span class="pill med">Medium</span>`;
  if (sev === 'low') return `<span class="pill low">Low</span>`;
  return '';
}
export function statusPill(status, confidence) {
  if (status === 'confirmed') return `<span class="pill conf">Confirmed</span>`;
  if (status === 'reported') return `<span class="pill rep">Reported</span>`;
  if (status === 'possible') return `<span class="pill poss">Possible match${confidence != null ? ' · ' + Math.round(confidence * 100) + '%' : ''}</span>`;
  return '';
}

// ---------- floating layers ----------
let layer = null; // {el, close, anchor}
export function closeLayer() {
  if (!layer) return;
  const l = layer; layer = null;
  l.el.remove();
  l.onClose?.();
  if (l.anchor) { l.anchor.setAttribute('aria-expanded', 'false'); if (l.restore !== false) l.anchor.focus({ preventScroll: true }); }
}
function place(el, anchor) {
  const r = anchor.getBoundingClientRect();
  const w = el.offsetWidth, h = el.offsetHeight;
  let left = Math.min(Math.max(12, r.left), window.innerWidth - w - 12);
  let top = r.bottom + 8;
  if (top + h > window.innerHeight - 12 && r.top - h - 8 > 12) top = r.top - h - 8;
  el.style.left = left + 'px'; el.style.top = Math.max(12, top) + 'px';
}
export function openPopover(anchor, html, { cls = 'pop', role = 'dialog', label = 'Details' } = {}) {
  // a chip inside an open popover (e.g. "+N more" list) opens its detail in place of that popover, at the same spot
  const inner = layer && layer.el.contains(anchor);
  if (inner) { layer.restore = false; anchor = layer.anchor; }
  const same = !inner && layer && layer.anchor === anchor;
  closeLayer();
  if (same) return null;
  const el = document.createElement('div');
  el.className = cls; el.setAttribute('role', role); el.setAttribute('aria-label', label);
  el.innerHTML = html;
  document.body.appendChild(el);
  place(el, anchor);
  anchor.setAttribute('aria-expanded', 'true');
  layer = { el, anchor };
  const f = el.querySelector('a,button:not(.x),[tabindex]') || el.querySelector('button');
  f?.focus({ preventScroll: true });
  return el;
}
export function openMenu(anchor, items, onPick) {
  const html = items.map((it, i) => `<button type="button" role="menuitem" data-i="${i}" class="${it.on ? 'on' : ''}">${esc(it.label)}${it.hint ? `<small>${esc(it.hint)}</small>` : ''}</button>`).join('');
  const el = openPopover(anchor, html, { cls: 'menu', role: 'menu', label: 'Options' });
  if (!el) return;
  el.addEventListener('click', e => {
    const b = e.target.closest('[data-i]'); if (!b) return;
    closeLayer(); onPick(items[+b.dataset.i]);
  });
  el.addEventListener('keydown', e => {
    const bs = $$('button', el); const i = bs.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); bs[(i + 1) % bs.length].focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); bs[(i - 1 + bs.length) % bs.length].focus(); }
  });
}

function sourcePopHTML(s) {
  const h = host(s.url);
  const isCala = /cala/i.test(s.name || '') || /cala\.ai/.test(h);
  const kind = isCala ? 'Cala' : h ? 'article' : 'record';
  return `<span class="cap">Source · ${esc(kind)}</span>
    <button type="button" class="x" aria-label="Close" data-close>×</button>
    <span class="pop-t">${esc(s.name || h || 'Source')}</span>
    <span class="meta" style="color:var(--muted)">${[h && !isCala ? esc(h) : '', s.date ? esc(fmtDate(s.date, { year: true })) : 'Undated'].filter(Boolean).join(' · ')}</span>
    ${s.url ? `<div class="pop-q">${esc(s.url)}</div>` : `<div class="pop-q">Record in Cala's knowledge graph. No public link.</div>`}
    ${s.url ? `<a class="btn" style="align-self:flex-start" href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener noreferrer">Open source ↗</a>` : ''}`;
}
export function safeUrl(u) {
  try { const x = new URL(u, location.href); return /^https?:$/.test(x.protocol) ? x.href : '#'; } catch { return '#'; }
}

// ---------- tooltip (hover/focus, data-tip) ----------
let tipEl = null;
function showTip(target) {
  hideTip();
  const text = target.getAttribute('data-tip'); if (!text) return;
  tipEl = document.createElement('div'); tipEl.className = 'tip'; tipEl.setAttribute('role', 'tooltip');
  tipEl.innerHTML = text; // already escaped at attribute creation; may contain <b>
  document.body.appendChild(tipEl);
  const r = target.getBoundingClientRect();
  const w = tipEl.offsetWidth;
  tipEl.style.left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8) + 'px';
  tipEl.style.top = (r.top - tipEl.offsetHeight - 8 < 8 ? r.bottom + 8 : r.top - tipEl.offsetHeight - 8) + 'px';
}
export function hideTip() { tipEl?.remove(); tipEl = null; }
export function floatTip(html, x, y) {
  hideTip();
  tipEl = document.createElement('div'); tipEl.className = 'tip'; tipEl.innerHTML = html;
  document.body.appendChild(tipEl);
  tipEl.style.left = Math.min(x + 14, innerWidth - tipEl.offsetWidth - 8) + 'px';
  tipEl.style.top = Math.min(y + 14, innerHeight - tipEl.offsetHeight - 8) + 'px';
}

// ---------- modal ----------
let modalStack = [];
export function openModal(html, { cls = '', label = 'Dialog', onClose } = {}) {
  closeLayer();
  const prev = document.activeElement;
  const scrim = document.createElement('div');
  scrim.className = 'scrim';
  scrim.innerHTML = `<div class="modal ${cls}" role="dialog" aria-modal="true" aria-label="${esc(label)}">${html}</div>`;
  document.body.appendChild(scrim);
  const m = { el: scrim, box: scrim.firstElementChild, close() { scrim.remove(); modalStack = modalStack.filter(x => x !== m); onClose?.(); prev?.focus?.({ preventScroll: true }); } };
  scrim.addEventListener('mousedown', e => { if (e.target === scrim) m.close(); });
  scrim.addEventListener('click', e => { if (e.target.closest('[data-close]')) m.close(); });
  modalStack.push(m);
  document.body.style.overflow = 'hidden';
  const obs = () => { if (!modalStack.length && !sheet) document.body.style.overflow = ''; };
  const oc = m.close; m.close = () => { oc(); obs(); };
  return m;
}
export function trapFocus(e, root) {
  if (e.key !== 'Tab') return;
  const f = $$('a[href],button:not([disabled]),input,textarea,[tabindex]:not([tabindex="-1"])', root).filter(x => x.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

export function closeModals() { [...modalStack].reverse().forEach(m => m.close()); }

// ---------- toast ----------
let toastT;
export function toast(msg, action) {
  $('.toast')?.remove(); clearTimeout(toastT);
  const t = document.createElement('div'); t.className = 'toast'; t.setAttribute('role', 'status');
  t.innerHTML = `<span>${esc(msg)}</span>${action ? `<button type="button">${esc(action.label)}</button>` : ''}`;
  if (action) t.querySelector('button').onclick = () => { t.remove(); action.run(); };
  document.body.appendChild(t);
  toastT = setTimeout(() => t.remove(), action ? 6000 : 3200);
}

// ---------- entity side sheet ----------
let sheet = null;
export function closeSheet() {
  if (!sheet) return;
  sheet.scrim.remove(); sheet.el.remove();
  const p = sheet.prev; sheet = null; document.body.style.overflow = modalStack.length ? 'hidden' : '';
  p?.focus?.({ preventScroll: true });
}
const REL_LABELS = { rivals: 'Rivals', competitors: 'Rivals', investors: 'Investors', people: 'People', founders: 'Founders', board: 'Board', executives: 'Executives', subsidiaries: 'Subsidiaries', parents: 'Parents', portfolio: 'Portfolio', investments: 'Investments', companies: 'Companies', employers: 'Worked at' };
// Cala relation keys ("IS_CEO_OF", "DESIGNED_BY (incoming)") as plain section headings: [outgoing, incoming]
const CALA_RELS = {
  PARTICIPATES_IN_CORPORATE_EVENT: ['Corporate events', 'Participants'], PARTICIPATES_IN_FUNDING_ROUND: ['Funding rounds', 'Participants'],
  INVESTED_IN: ['Invested in', 'Investors'], WORKS_AT: ['Works at', 'People'], FOUNDED: ['Founded', 'Founders'],
  IS_MEMBER_OF: ['Member of', 'Members'], IS_CEO_OF: ['CEO of', 'CEO'], IS_CTO_OF: ['CTO of', 'CTO'], IS_COO_OF: ['COO of', 'COO'],
  IS_CFO_OF: ['CFO of', 'CFO'], IS_CCO_OF: ['CCO of', 'CCO'], IS_CMO_OF: ['CMO of', 'CMO'], IS_CSO_OF: ['CSO of', 'CSO'], IS_CRO_OF: ['CRO of', 'CRO'],
  IS_CHAIRMAN_OF: ['Chair of', 'Chair'], IS_PRESIDENT_OF: ['President of', 'President'], IS_VICEPRESIDENT_OF: ['Vice president of', 'Vice presidents'],
  IS_MANAGING_DIRECTOR_OF: ['Managing director of', 'Managing directors'], IS_EXECUTIVE_OF: ['Executive at', 'Executives'],
  IS_BOARD_MEMBER_OF: ['Board seats', 'Board'], IS_CONTROL_PERSON_OF: ['Controls', 'Control persons'],
  IS_BENEFICIARY_OWNER_OF: ['Beneficial owner of', 'Beneficial owners'], IS_DIRECT_PARENT_OF: ['Subsidiaries', 'Parent'],
  IS_ULTIMATE_PARENT_OF: ['Ultimately owns', 'Ultimate parent'], IS_SUBSIDIARY_OF: ['Parent', 'Subsidiaries'],
  OPERATES_IN_INDUSTRY: ['Industries', 'Companies'], HAS_NATIONALITY: ['Nationality', 'Nationals'],
  IS_REGISTERED_IN: ['Registered in', 'Registered companies'], HAS_HEADQUARTERS_IN: ['Headquarters', 'Headquartered here'],
  HAS_PRESENCE_IN: ['Present in', 'Present here'], HAS_OPERATIONAL_PRESENCE_IN: ['Operates in', 'Operating here'],
  LISTED_ON: ['Listed on', 'Listed companies'], TRADED_ON: ['Traded on', 'Traded here'], DESIGNED_BY: ['Designed by', 'Designs'],
  CREATED_BY: ['Created by', 'Created'], OPERATED_BY: ['Operated by', 'Operates'], MANUFACTURED_BY: ['Made by', 'Makes'],
  FEATURED_IN: ['Featured in', 'Features'], SPOKE_AT: ['Spoke at', 'Speakers'], STUDIED_AT: ['Studied at', 'Alumni'],
  RECEIVED_AWARD: ['Awards', 'Recipients'], PUBLISHED_BY: ['Published by', 'Publishes'], GRANTED_BY: ['Granted by', 'Granted'],
  HAS_DOMAIN_NAME: ['Domains', 'Owner'],
};
function relLabel(k) {
  if (REL_LABELS[k]) return REL_LABELS[k];
  const inc = / \(incoming\)$/.test(k), key = k.replace(/ \(incoming\)$/, '');
  if (CALA_RELS[key]) return CALA_RELS[key][inc ? 1 : 0];
  const t = key.replace(/^(IS|HAS)_/, '').replace(/_OF$/, '').replace(/_/g, ' ').toLowerCase();
  return (inc ? 'Linked: ' : '') + t.replace(/^\w/, c => c.toUpperCase());
}
const isoish = v => /^\d{4}-\d{2}(-\d{2})?(T[\d:.]+Z?)?$/.test(v);
export async function openEntity(ref) {
  closeLayer(); hideTip();
  const prev = document.activeElement;
  closeSheet();
  const scrim = document.createElement('div'); scrim.className = 'sheet-scrim';
  const el = document.createElement('aside'); el.className = 'sheet'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-label', ref.name || 'Entity');
  const head = (e) => `<div class="sheet-h">${avatar(e).replace('class="av', 'style="width:40px;height:40px;font-size:14px;border-radius:' + ((e.type || '').toLowerCase() === 'company' ? '12px' : '99px') + '" class="av')}
      <div class="grow" style="min-width:0;display:flex;flex-direction:column;gap:2px"><span class="cap">${esc(e.type || 'Entity')}${e.sub ? ' · ' + esc(e.sub) : ''}</span><h2>${esc(nm(e.name))}</h2></div>
      <button type="button" class="x" aria-label="Close" data-close-sheet>×</button></div>`;
  el.innerHTML = head(ref) + `<div class="sheet-b"><div class="sk sk-line" style="width:90%"></div><div class="sk sk-line" style="width:70%"></div><div class="sk" style="height:120px"></div><div class="sk" style="height:80px"></div></div>`;
  document.body.append(scrim, el);
  document.body.style.overflow = 'hidden';
  sheet = { el, scrim, prev };
  scrim.onclick = closeSheet;
  el.addEventListener('click', e => { if (e.target.closest('[data-close-sheet]')) closeSheet(); });
  el.addEventListener('keydown', e => trapFocus(e, el));
  el.querySelector('.x').focus();
  try {
    const d = await api.entity(ref.id);
    if (!sheet || sheet.el !== el) return;
    const facts = (d.facts || []).filter(f => f.value);
    const rels = Object.entries(d.relations || {}).filter(([, v]) => v && v.length);
    el.innerHTML = head({ ...ref, ...d, sub: ref.sub }) + `<div class="sheet-b stagger">
      ${d.description ? `<p class="muted">${esc(d.description)}</p>` : ''}
      ${facts.length ? `<section class="sec"><h3 class="h">Facts</h3><dl class="kv">${facts.map(f => `<dt>${esc(f.label)}</dt><dd><span>${esc(isoish(f.value) ? fmtDate(f.value.slice(0, 10), { year: true }) : f.value)}</span>${srcChips(f.sources, 1)}</dd>`).join('')}</dl></section>` : ''}
      ${rels.map(([k, v]) => `<section class="sec"><h3 class="h">${esc(relLabel(k))} <span style="color:var(--line-2)">· ${v.length}</span></h3><div class="chips">${v.slice(0, 24).map(entChip).join('')}</div></section>`).join('')}
      ${!facts.length && !rels.length && !d.description ? `<div class="state"><b>Not much on file</b><span>Cala has no facts or relations for this entity yet.</span></div>` : ''}
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${(d.type || ref.type || 'Company').toLowerCase() !== 'person' ? `<a class="btn dark lg" href="#/check/${encodeURIComponent(d.id || ref.id)}" data-close-sheet>Run check</a>` : ''}
        <button type="button" class="btn lg" data-ask="${esc('What should a VC know about ' + (d.name || ref.name) + '?')}">Ask about ${esc(d.name || ref.name)}</button>
      </div></div>`;
  } catch (err) {
    if (!sheet || sheet.el !== el) return;
    el.querySelector('.sheet-b').innerHTML = `<div class="card scard"><span class="cap">Source error</span><span>Cala didn’t respond for ${esc(ref.name)}.</span><button type="button" class="btn" style="align-self:flex-start" data-retry>Retry</button></div>`;
    el.querySelector('[data-retry]').onclick = () => openEntity(ref);
  }
}

// Generic side sheet (same chrome as the entity sheet) for overlap details etc.
export function openPanel({ cap = '', title = '', body = '', label = title }) {
  closeLayer(); hideTip();
  const prev = document.activeElement;
  closeSheet();
  const scrim = document.createElement('div'); scrim.className = 'sheet-scrim';
  const el = document.createElement('aside'); el.className = 'sheet'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-label', label);
  el.innerHTML = `<div class="sheet-h"><div class="grow" style="min-width:0;display:flex;flex-direction:column;gap:4px"><span class="cap">${esc(cap)}</span><h2>${esc(title)}</h2></div><button type="button" class="x" aria-label="Close" data-close-sheet>×</button></div><div class="sheet-b stagger">${body}</div>`;
  document.body.append(scrim, el);
  document.body.style.overflow = 'hidden';
  sheet = { el, scrim, prev };
  scrim.onclick = closeSheet;
  el.addEventListener('click', e => { if (e.target.closest('[data-close-sheet]')) closeSheet(); });
  el.addEventListener('keydown', e => trapFocus(e, el));
  el.querySelector('.x').focus();
  return el;
}

// ---------- global delegation ----------
export function installGlobal({ onAsk }) {
  document.addEventListener('click', e => {
    const s = e.target.closest('[data-src]');
    if (s) { e.preventDefault(); const src = lookup(s.dataset.src); if (src) openPopover(s, sourcePopHTML(src), { label: 'Source' }); return; }
    const ss = e.target.closest('[data-srcs]');
    if (ss) {
      e.preventDefault();
      const list = lookup(ss.dataset.srcs) || [];
      openPopover(ss, `<span class="cap">More sources</span><button type="button" class="x" aria-label="Close" data-close>×</button><div class="chips" style="flex-direction:column;align-items:flex-start">${list.map(srcChip).join('')}</div>`, { label: 'Sources' });
      return;
    }
    const en = e.target.closest('[data-ent]');
    if (en) { e.preventDefault(); const ref = lookup(en.dataset.ent); if (ref) openEntity(ref); return; }
    const ask = e.target.closest('[data-ask]');
    if (ask) { e.preventDefault(); closeSheet(); onAsk(ask.dataset.ask); return; }
    if (e.target.closest('[data-close]') && layer && layer.el.contains(e.target)) { closeLayer(); return; }
    if (layer && !layer.el.contains(e.target) && !layer.anchor?.contains(e.target)) { layer.restore = false; closeLayer(); }
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (layer) { e.preventDefault(); closeLayer(); return; }
    if (sheet) { e.preventDefault(); closeSheet(); return; }
    if (modalStack.length) { e.preventDefault(); modalStack[modalStack.length - 1].close(); }
  });
  let tipTarget = null;
  document.addEventListener('mouseover', e => {
    const t = e.target.closest?.('[data-tip]');
    if (t === tipTarget) return;
    tipTarget = t; t ? showTip(t) : hideTip();
  });
  document.addEventListener('focusin', e => { const t = e.target.closest?.('[data-tip]'); if (t) { tipTarget = t; showTip(t); } });
  document.addEventListener('focusout', () => { tipTarget = null; hideTip(); });
  addEventListener('scroll', e => { hideTip(); if (layer && !(e.target instanceof Node && layer.el.contains(e.target))) { layer.restore = false; closeLayer(); } }, { passive: true, capture: true });
  addEventListener('resize', () => { if (layer) { layer.restore = false; closeLayer(); } });
}

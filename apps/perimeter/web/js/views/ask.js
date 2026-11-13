import { api } from '../api.js';
import { $, esc, srcChips, entChip, openModal, trapFocus, safeUrl } from '../ui.js';

const THINKING = [
  'Searching Cala’s knowledge graph', 'Resolving the companies you mentioned', 'Following ownership and board links',
  'Reading funding rounds and corporate events', 'Cross-checking facts against sources', 'Writing a sourced answer',
];
const SUGGESTIONS = [
  'Which investors in my portfolio also back a rival?',
  'Who sits on more than one board around my companies?',
  'What changed around Mollie in the last month?',
  'Which rivals raised money this year, and from whom?',
];
const ICON_Q = '<svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="9" cy="9" r="5.5"/><path d="M13 13l4 4"/></svg>';
const ICON_ARR = '<svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M5 10h10M11 6l4 4-4 4"/></svg>';

// ---------- tiny safe markdown ----------
function inline(s) {
  s = esc(s);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/__([^_]+)__/g, '<strong>$1</strong>');
  s = s.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, '$1<em>$2</em>').replace(/(^|[^_\w])_([^_\n]+)_(?!\w)/g, '$1<em>$2</em>');
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, t, u) => `<a href="${esc(safeUrl(u.replace(/&amp;/g, '&')))}" target="_blank" rel="noopener noreferrer">${t}</a>`);
  return s;
}
export function md(src) {
  const lines = String(src || '').replace(/\r/g, '').split('\n');
  const out = []; let list = null; let para = []; let table = null;
  const flushP = () => { if (para.length) { out.push(`<p>${inline(para.join(' '))}</p>`); para = []; } };
  const flushL = () => { if (list) { out.push(`<${list.t}>${list.items.map(i => `<li>${inline(i)}</li>`).join('')}</${list.t}>`); list = null; } };
  const flushT = () => { if (table) { const [h, ...rows] = table.filter(r => !/^\s*\|?\s*:?-{2,}/.test(r)); const cells = r => r.replace(/^\s*\||\|\s*$/g, '').split('|').map(c => c.trim()); out.push(`<table><thead><tr>${cells(h).map(c => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${cells(r).map(c => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`); table = null; } };
  for (const ln of lines) {
    let m;
    if (/^\s*\|.*\|\s*$/.test(ln)) { flushP(); flushL(); (table ||= []).push(ln); continue; } else flushT();
    if (!ln.trim()) { flushP(); flushL(); continue; }
    if ((m = /^(#{1,4})\s+(.*)$/.exec(ln))) { flushP(); flushL(); out.push(`<h3>${inline(m[2])}</h3>`); continue; }
    if ((m = /^\s*[-*•]\s+(.*)$/.exec(ln))) { flushP(); if (!list || list.t !== 'ul') { flushL(); list = { t: 'ul', items: [] }; } list.items.push(m[1]); continue; }
    if ((m = /^\s*\d+[.)]\s+(.*)$/.exec(ln))) { flushP(); if (!list || list.t !== 'ol') { flushL(); list = { t: 'ol', items: [] }; } list.items.push(m[1]); continue; }
    if (list && /^\s{2,}\S/.test(ln)) { list.items[list.items.length - 1] += ' ' + ln.trim(); continue; }
    flushL(); para.push(ln.trim());
  }
  flushP(); flushL(); flushT();
  return out.join('');
}

// Shared ask component: renders input + body into `root`. Returns {ask(q)}.
function mountAsk(root, { compact }) {
  root.innerHTML = `<form class="pal-in" autocomplete="off">${ICON_Q}<label class="sr" for="askIn">Ask anything</label>
      <input id="askIn" placeholder="Ask about your portfolio, a company, an investor…" spellcheck="false">
      ${compact ? '<kbd class="kbd">Esc</kbd>' : '<button type="submit" class="btn dark">Ask</button>'}</form>
    <div class="pal-b" id="askB"></div>`;
  const input = root.querySelector('#askIn'), body = root.querySelector('#askB');
  let seq = 0, timers = [];
  const clear = () => { timers.forEach(t => clearInterval(t)); timers = []; };
  function idle() {
    body.innerHTML = `<span class="cap">Try asking</span><div class="sugg">${SUGGESTIONS.map(s => `<button type="button" data-q="${esc(s)}">${ICON_ARR}${esc(s)}</button>`).join('')}</div>
      <span class="note">Answers come from Cala’s knowledge graph, with sources. Complex questions take 20–40 seconds.</span>`;
  }
  async function ask(q) {
    q = q.trim(); if (!q) return;
    input.value = q;
    const my = ++seq; clear();
    const t0 = Date.now(); let i = 0;
    body.innerHTML = `<div class="think" aria-live="polite">
        <div class="think-row"><span class="orb" aria-hidden="true"><i></i><i></i><i></i></span><span class="think-t" id="thT">${THINKING[0]}…</span><span class="meta grow" style="text-align:right" id="thS">0 s</span></div>
        <div class="bar"><i id="thBar" style="width:4%"></i></div>
        <div style="display:flex;flex-direction:column;gap:8px;margin-top:6px"><div class="sk sk-line" style="width:92%"></div><div class="sk sk-line" style="width:84%"></div><div class="sk sk-line" style="width:66%"></div></div>
      </div>`;
    timers.push(setInterval(() => {
      const s = (Date.now() - t0) / 1000;
      const sEl = body.querySelector('#thS'), bar = body.querySelector('#thBar');
      if (sEl) sEl.textContent = Math.round(s) + ' s';
      if (bar) bar.style.width = Math.min(94, 100 * (1 - Math.exp(-s / 16))) + '%';
    }, 500));
    timers.push(setInterval(() => {
      i = Math.min(i + 1, THINKING.length - 1);
      const t = body.querySelector('#thT'); if (!t) return;
      t.style.opacity = 0; setTimeout(() => { t.textContent = THINKING[i] + '…'; t.style.opacity = 1; }, 250);
    }, 4200));
    try {
      const r = await api.ask(q);
      if (my !== seq) return; clear();
      body.innerHTML = `<div class="sec in" style="gap:14px">
        <div class="answer-meta"><span class="cap">Answer from Cala</span><span class="meta">· ${(r.seconds ?? (Date.now() - t0) / 1000).toFixed(0)} s</span></div>
        <div class="md">${md(r.answer_md)}</div>
        ${(r.entities || []).length ? `<div class="sec" style="gap:8px"><span class="cap">Mentioned</span><div class="chips">${r.entities.map(entChip).join('')}</div></div>` : ''}
        ${(r.sources || []).length ? `<div class="sec" style="gap:8px"><span class="cap">Sources</span><div class="chips">${srcChips(r.sources, 8)}</div></div>` : ''}
      </div>`;
    } catch (err) {
      if (my !== seq) return; clear();
      body.innerHTML = `<div class="card scard"><span class="cap">Source error</span><span>Cala didn’t answer that one. ${esc(err.message)}</span><button type="button" class="btn" style="align-self:flex-start" data-retry>Retry</button></div>`;
      body.querySelector('[data-retry]').onclick = () => ask(q);
    }
  }
  root.querySelector('form').onsubmit = e => { e.preventDefault(); ask(input.value); };
  input.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); ask(input.value); } });
  body.addEventListener('click', e => { const b = e.target.closest('[data-q]'); if (b) ask(b.dataset.q); });
  idle();
  return { ask, input, destroy: () => { seq++; clear(); } };
}

let palette = null;
export function openAsk(q) {
  if (palette) { if (q) palette.comp.ask(q); palette.comp.input.focus(); return; }
  const m = openModal('', { cls: 'pal', label: 'Ask anything', onClose: () => { palette?.comp.destroy(); palette = null; } });
  const comp = mountAsk(m.box, { compact: true });
  m.box.addEventListener('keydown', e => trapFocus(e, m.box));
  palette = { m, comp };
  comp.input.focus();
  if (q) comp.ask(q);
}

export function renderAskPage(ctx) {
  ctx.app.innerHTML = `<main class="main"><div class="ph in"><h1>Ask</h1><p>Questions about your perimeter, answered from Cala with sources.</p></div><div class="card in" id="askPage" style="overflow:hidden"></div></main>`;
  const comp = mountAsk($('#askPage'), { compact: false });
  comp.input.focus();
  const q = ctx.qs.get('q'); if (q) comp.ask(q);
  ctx.onCleanup(() => comp.destroy());
}

import { api } from '../api.js';
import { refreshPortfolio, seat, myCompany, viewingDemo, hasProfile, switchView } from '../app.js';
import { pathHTML, openOverlap, installPathHandlers } from '../overlap.js';
import { $, $$, esc, srcChips, entLink, entPill, sevPill, statusPill, openMenu, openModal, toast, parseDate, fmtDate, trapFocus, plural } from '../ui.js';

const KIND_LABEL = { overlap_investor: 'Investor overlap', overlap_board: 'Board overlap', funding: 'Funding', mna: 'M&A', regulatory: 'Regulatory', legal: 'Legal', hiring: 'Hiring', news: 'News', page_change: 'Page change' };
const CATS = ['All', 'Risk', 'Funding', 'Overlaps'];

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? 'Good evening' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}
function bucket(d) {
  const x = parseDate(d);
  if (!x) return 'Earlier';
  const now = new Date(); const t0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.round((t0 - x) / 864e5);
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return 'This week';
  if (x.getMonth() === now.getMonth() && x.getFullYear() === now.getFullYear()) return 'Earlier this month';
  const M = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'][x.getMonth()];
  return x.getFullYear() === now.getFullYear() ? M : (now - x < 400 * 864e5 ? `${M} ${x.getFullYear()}` : 'Earlier');
}
const isCard = it => it.status === 'possible' || it.severity === 'high' || it.severity === 'medium' || it.kind?.startsWith('overlap');

function metaLine(it) {
  const bits = [];
  if (it.subject?.name) bits.push(`${entLink(it.subject)} · ${esc(it.subject.relation || '')}`);
  else if (it.company?.name) bits.push(entLink(it.company) + (it.status === 'possible' ? ' · yours' : ''));
  if (it.date && bucket(it.date) !== 'Today') bits.push(esc(fmtDate(it.date)));
  return `<span class="meta">${bits.join(' · ')}</span>`;
}

function cardHTML(it, founder = false) {
  const possible = it.status === 'possible';
  const overlap = it.kind?.startsWith('overlap');
  const labels = possible
    ? `${statusPill('possible', it.confidence)}<span class="pill rep">Reported</span>`
    : overlap ? `<span class="pill soft">${KIND_LABEL[it.kind]}</span>${it.severity === 'high' ? sevPill('high', 'High risk') : ''}`
    : `${it.severity === 'high' ? sevPill('high', 'High risk') : `<span class="pill med">${esc(KIND_LABEL[it.kind] || it.category)}</span>`}${statusPill(it.status)}`;
  const draft = !founder && (it.actions || []).includes('draft_note');
  const actions = possible
    ? `<div class="acts yn"><button type="button" class="btn" data-yes="${esc(it.id)}">Yes, it’s them</button><button type="button" class="btn" data-no="${esc(it.id)}">Not this company</button><span class="grow"></span>${srcChips(it.sources)}</div>`
    : `<div class="acts">${srcChips(it.sources, overlap && it.path?.length ? 1 : 2)}<span class="grow"></span>
        ${it.severity === 'high' && !overlap && !draft ? `<button type="button" class="btn ghost" data-no="${esc(it.id)}">Not this company</button>` : ''}
        ${overlap && it.path?.length ? `<button type="button" class="btn" data-overlap="${esc(it.id)}">See the overlap</button>` : ''}
        ${draft ? `<button type="button" class="btn dark" data-draft="${esc(it.id)}"><span>Draft note<span class="mhide"> to founder</span></span></button>` : ''}</div>`;
  return `<article class="card fcard${possible ? ' possible' : ''}${overlap && it.path?.length ? ' clickable' : ''}" data-item="${esc(it.id)}">
    <div class="lbls">${labels}${metaLine(it)}</div>
    <h3>${esc(it.title)}</h3>
    ${overlap ? pathHTML(it.path) : ''}
    ${it.body ? `<p>${esc(it.body)}</p>` : ''}
    ${actions}</article>`;
}
function rowHTML(it) {
  const who = it.subject?.name ? `${entLink(it.subject)} · ${esc(it.subject.relation || '')}` : it.company?.name ? entLink(it.company) : '';
  const when = it.date ? esc(fmtDate(it.date)) : '';
  return `<div class="crow" data-item="${esc(it.id)}"><span class="pill rep">${esc(KIND_LABEL[it.kind] || it.category)}</span>
    <div class="t"><span class="tt" title="${esc(it.title)}">${esc(it.title)}</span>${who || when ? `<span class="meta">${[who, when].filter(Boolean).join(' · ')}</span>` : ''}</div>
    <span class="srcs">${srcChips(it.sources, 1)}</span></div>`;
}

export async function render(ctx) {
  const { app, store } = ctx;
  const companies = store.portfolio?.companies || [];
  const founder = seat() === 'founder';
  const co = founder ? (myCompany()?.name || companies[0]?.name || 'your company') : null;
  // the backend phrases from an investor's seat; a founder is a portfolio of one
  const phrase = t => !founder || !t ? t : t.replace(/ across your 1 compan(y|ies)\./, ` around ${co}.`);
  let filter = { cat: 'All', company: null };
  let data = null;
  const hidden = new Set();
  const confirmed = new Set();

  app.innerHTML = `<main class="main">
    <div class="ph in"><h1>${greeting()}</h1><p id="sum"><span class="sk sk-line" style="display:inline-block;width:340px"></span></p></div>
    ${demoBanner()}
    ${founder ? '<section class="card fhome in" id="fhome" aria-label="Around you"><div class="sk sk-line" style="width:120px"></div><div class="sk" style="height:28px;width:90%"></div><div class="sk sk-line" style="width:140px;margin-top:6px"></div><div class="sk" style="height:28px;width:70%"></div></section>' : ''}
    <div id="buildBar"></div>
    <div class="filters in" id="filters" role="toolbar" aria-label="Filter feed"></div>
    <div id="feed" class="sec" style="gap:28px">${[0, 1, 2].map(() => `<div class="card fcard"><div class="sk sk-line" style="width:160px"></div><div class="sk" style="height:18px;width:85%"></div><div class="sk sk-line" style="width:60%"></div></div>`).join('')}</div>
  </main>`;

  try { data = await api.feed(); }
  catch (err) {
    if (!ctx.isCurrent()) return;
    $('#sum').textContent = 'Your feed couldn’t load.';
    $('#feed').innerHTML = `<div class="card scard"><span class="cap">Source error</span><span>Cala didn’t respond. ${esc(err.message)}</span><button type="button" class="btn" style="align-self:flex-start" id="retry">Retry</button></div>`;
    $('#retry').onclick = () => render(ctx);
    return;
  }
  if (!ctx.isCurrent()) return;
  $('#sum').textContent = data.partial ? 'Here is what Cala has so far. The rest fills in as it lands.' : phrase(data.summary) || '';
  if (founder) drawHome(ctx, co);

  const items = () => [...(data.items || [])].sort((a, b) => (b.date || '').localeCompare(a.date || '')).filter(i => !hidden.has(i.id)).map(i => confirmed.has(i.id) ? { ...i, status: 'confirmed' } : i);
  function drawFilters() {
    const all = items();
    const ct = c => c === 'All' ? all.length : all.filter(i => i.category === c).length;
    const coName = filter.company ? (companies.find(c => c.id === filter.company)?.name || all.find(i => i.company?.id === filter.company)?.company.name) : null;
    $('#filters').innerHTML = CATS.map(c => `<button type="button" class="fpill ${filter.cat === c ? 'on' : ''}" data-cat="${c}" aria-pressed="${filter.cat === c}">${c}<span class="ct">${ct(c)}</span></button>`).join('')
      + (founder ? '' : `<button type="button" class="fpill ${filter.company ? 'on' : ''}" id="coPick" aria-haspopup="menu">${esc(coName || 'All companies')} ▾</button>`);
    $$('[data-cat]').forEach(b => b.onclick = () => { filter.cat = b.dataset.cat; draw(); });
    if ($('#coPick')) $('#coPick').onclick = e => {
      const cos = companies.length ? companies : [...new Map(all.map(i => [i.company.id, i.company])).values()];
      openMenu(e.currentTarget, [{ label: 'All companies', id: null, on: !filter.company }, ...cos.map(c => ({ label: c.name, id: c.id, on: filter.company === c.id, hint: String(all.filter(i => i.company?.id === c.id).length) }))], it => { filter.company = it.id; draw(); });
    };
  }
  function draw() {
    drawFilters();
    const list = items().filter(i => (filter.cat === 'All' || i.category === filter.cat) && (!filter.company || i.company?.id === filter.company));
    const feed = $('#feed');
    drawBuild();
    if (!list.length && data.partial) {
      feed.innerHTML = skCards(2);
      return;
    }
    if (!list.length) {
      const nAll = items().length;
      feed.innerHTML = `<div class="card state in"><span class="ic">✓</span><b>All quiet</b><span>${nAll ? 'Nothing matches this filter.' : founder ? `Nothing has changed around ${esc(co)} yet.` : `Watching ${plural(companies.length, 'company', 'companies')}. Nothing has changed around them yet.`}</span>${nAll ? '<button type="button" class="btn" id="clr">Clear filters</button>' : ''}</div>`;
      $('#clr') && ($('#clr').onclick = () => { filter = { cat: 'All', company: null }; draw(); });
      return;
    }
    const groups = new Map();
    list.forEach(i => { const b = bucket(i.date); if (!groups.has(b)) groups.set(b, []); groups.get(b).push(i); });
    feed.innerHTML = [...groups].map(([name, its]) => {
      const cards = its.filter(isCard), rows = its.filter(i => !isCard(i));
      return `<section class="sec"><h2 class="h">${esc(name)}</h2><div class="sec stagger">${cards.map(c => cardHTML(c, founder)).join('')}${rows.length ? `<div class="card">${rows.map(rowHTML).join('')}</div>` : ''}</div></section>`;
    }).join('') + (data.partial ? skCards(1) : '');
  }
  // First build of a new portfolio: render what has landed, keep polling until the build finishes.
  function drawBuild() {
    const bar = $('#buildBar'); if (!bar) return;
    if (!data.partial) { bar.innerHTML = ''; return; }
    const st = data.status || [];
    const ready = st.filter(s => s.status !== 'mapping').length;
    const rivals = st.length && st.every(s => s.status === 'rivals');
    bar.innerHTML = `<div class="card buildbar in" aria-live="polite"><span class="spin" aria-hidden="true"></span><span class="grow">${rivals ? 'Reading rivals, screening news and sanctions' : founder ? `Mapping ${esc(co)}` : `Mapping your companies · ${ready} of ${st.length || companies.length} ready`}</span><span class="meta">Updates as Cala answers</span></div>`;
  }
  let pollT;
  async function poll() {
    try {
      const d = await api.feed();
      if (!ctx.isCurrent()) return;
      const was = data.items?.length;
      data = d; $('#sum').textContent = d.partial ? 'Here is what Cala has so far. The rest fills in as it lands.' : phrase(d.summary) || '';
      if (!d.partial) { draw(); toast('Perimeter ready'); refreshPortfolio(); if (founder) drawHome(ctx, co); return; }
      if (d.items?.length !== was) draw(); else drawBuild();
    } catch {}
    pollT = setTimeout(poll, 3500);
  }
  if (data.partial) { pollT = setTimeout(poll, 2500); ctx.onCleanup(() => clearTimeout(pollT)); }
  draw();

  installPathHandlers();
  $('[data-demo-act]')?.addEventListener('click', e => { if (e.currentTarget.dataset.demoAct === 'me') switchView('me'); else ctx.go('#/welcome'); });
  $('#feed').addEventListener('click', async e => {
    const ov = e.target.closest('[data-overlap]') || (!e.target.closest('button,a,input') && e.target.closest('.fcard.clickable'));
    if (ov) { const id = ov.dataset.overlap || ov.dataset.item; return openOverlap(data.items.find(i => i.id === id), { onDraft: openDraft }); }
    const d = e.target.closest('[data-draft]');
    if (d) return openDraft(data.items.find(i => i.id === d.dataset.draft));
    const y = e.target.closest('[data-yes]');
    if (y) { const id = y.dataset.yes; confirmed.add(id); draw(); toast('Marked as a match. We’ll keep watching it.', { label: 'Undo', run: () => { confirmed.delete(id); draw(); } }); return; }
    const n = e.target.closest('[data-no]');
    if (n) {
      const id = n.dataset.no; const card = n.closest('[data-item]');
      card?.classList.add('hidden-out');
      setTimeout(() => { hidden.add(id); draw(); }, 220);
      toast('Hidden. We won’t show this match again.', { label: 'Undo', run: () => { hidden.delete(id); draw(); } });
    }
  });
}

/** Shared-demo strip: say what this is and offer the way to your own seat. */
function demoBanner() {
  if (!viewingDemo()) return '';
  const mine = hasProfile();
  return `<div class="card buildbar demobar in"><span class="demo-badge">Demo</span><span class="grow">${mine ? 'You’re viewing the shared demo portfolio.' : 'Shared demo: four European fintechs, seen from an investor’s seat.'}</span><button type="button" class="btn ${mine ? '' : 'acc'}" data-demo-act="${mine ? 'me' : 'welcome'}">${mine ? 'Back to my profile' : 'Make it yours'}</button></div>`;
}

/** Founder home: your rivals and the investors around you, straight from the perimeter. */
async function drawHome(ctx, co) {
  let per;
  try { per = await api.perimeter(); } catch { $('#fhome')?.remove(); return; }
  if (!ctx.isCurrent()) return;
  const box = $('#fhome'); if (!box) return;
  const me = (per.companies || [])[0];
  if (!me) { if (!per.partial) box.remove(); return; }
  const rivals = me.rivals || [];
  const seen = new Set(); // Cala often holds several legal entities with one short name
  const inv = [...(me.investors || [])].sort((a, b) => (b.shared_with?.length || 0) - (a.shared_with?.length || 0))
    .filter(i => { const k = shortName(i.name).toLowerCase(); if (seen.has(k)) return false; seen.add(k); return true; });
  const hot = inv.filter(i => i.shared_with?.length);
  const pill = i => i.shared_with?.length
    ? entPill({ ...i, type: 'Investor' }, `${shortName(i.name)} · also backs ${i.shared_with[0]}`, 'hot', `data-tip="${esc(`<b>${esc(i.name)}</b><br><span>Backs ${esc(co)} and ${esc(i.shared_with.join(', '))}</span>`)}"`)
    : entPill({ ...i, type: 'Investor' }, shortName(i.name), 'n');
  box.innerHTML = `<div class="fh-row"><div class="fh-h"><span class="cap">Your rivals</span><span class="meta">${rivals.length || ''}</span></div>
      <div class="chips">${rivals.length ? rivals.map(r => entPill({ ...r, type: 'Company' }, shortName(r.name), 'n')).join('') : `<span class="meta">${per.partial ? 'Finding them in Cala…' : 'Cala lists no close rivals yet.'}</span>`}</div></div>
    <div class="fh-row"><div class="fh-h"><span class="cap">Investors around you</span><span class="meta">${hot.length ? `${hot.length} also ${hot.length === 1 ? 'backs' : 'back'} a rival` : inv.length || ''}</span></div>
      <div class="chips">${inv.length ? inv.slice(0, 10).map(pill).join('') + (inv.length > 10 ? `<span class="meta" style="align-self:center">+${inv.length - 10} more</span>` : '') : '<span class="meta">No investors in Cala yet.</span>'}</div></div>
    <div class="fh-f"><span class="meta grow">From Cala’s knowledge graph, every edge sourced.</span><a class="btn" href="#/map">See the map</a><a class="btn dark" href="/ask">Ask about ${esc(co)}</a></div>`;
}
const shortName = n => String(n || '').replace(/\s+(Fund|Capital)\s+[IVX]+\b.*$/i, '').trim();

const skCards = n => Array.from({ length: n }, () => `<div class="card fcard" aria-hidden="true"><div class="lbls"><span class="sk" style="height:24px;width:96px;border-radius:99px"></span><span class="sk sk-line" style="width:160px"></span></div><div class="sk" style="height:18px;width:80%"></div><div class="sk sk-line" style="width:95%"></div><div class="sk sk-line" style="width:60%"></div></div>`).join('');

async function openDraft(item) {
  if (!item) return;
  const m = openModal(`<div class="modal-h"><div class="grow" style="display:flex;flex-direction:column;gap:2px"><span class="cap">Note to the founder · ${esc(item.company?.name || '')}</span><h2 style="font-size:17px;font-weight:600;letter-spacing:-.01em">Draft note</h2></div><button type="button" class="x" aria-label="Close" data-close>×</button></div>
    <div class="modal-b" id="draftB"><div class="field"><span class="cap">Subject</span><div class="sk" style="height:40px"></div></div><div class="field"><span class="cap">Body</span><div class="sk" style="height:220px"></div></div><span class="meta" style="display:flex;gap:8px;align-items:center"><span class="spin"></span>Writing from Cala facts and sources only…</span></div>
    <div class="modal-f"><button type="button" class="btn" data-close>Cancel</button><a class="btn" id="mailto" href="#" aria-disabled="true">Open in mail</a><button type="button" class="btn dark" id="copyD" disabled>Copy note</button></div>`, { label: 'Draft note to founder' });
  m.box.addEventListener('keydown', e => trapFocus(e, m.box));
  m.box.querySelector('.x').focus();
  try {
    const d = await api.draft(item.id);
    if (!document.body.contains(m.el)) return;
    $('#draftB').innerHTML = `<div class="field in"><label for="dSub">Subject</label><input id="dSub" value="${esc(d.subject)}"></div>
      <div class="field in"><label for="dBody">Body</label><textarea id="dBody" rows="12">${esc(d.body)}</textarea></div>
      <span class="note">Facts and sources only. Edit before sending.</span>`;
    const upd = () => { $('#mailto').href = `mailto:?subject=${encodeURIComponent($('#dSub').value)}&body=${encodeURIComponent($('#dBody').value)}`; };
    upd(); $('#dSub').oninput = upd; $('#dBody').oninput = upd;
    $('#mailto').removeAttribute('aria-disabled');
    const c = $('#copyD'); c.disabled = false;
    c.onclick = async () => {
      const text = `Subject: ${$('#dSub').value}\n\n${$('#dBody').value}`;
      try { await navigator.clipboard.writeText(text); } catch { const t = $('#dBody'); t.select(); document.execCommand('copy'); }
      c.textContent = 'Copied ✓'; toast('Note copied to clipboard');
      setTimeout(() => { if (c.isConnected) c.textContent = 'Copy note'; }, 1800);
    };
    $('#dBody').focus(); $('#dBody').setSelectionRange(0, 0); $('#dBody').scrollTop = 0;
  } catch (err) {
    $('#draftB').innerHTML = `<div class="card scard"><span class="cap">Couldn’t draft</span><span>${esc(err.message)}</span></div>`;
  }
}

import { api } from '../api.js';
import { nm, $, $$, esc, srcChips, srcChip, entLink, sevPill, statusPill, fmtDate, fmtMonth, toast, plural, lookup, openPopover } from '../ui.js';
import { refreshPortfolio } from '../app.js';

const STEPS = [
  ['match', 'Matching the company'], ['profile', 'Reading Cala profile'], ['people', 'Mapping people and owners'],
  ['events', 'Reading corporate events'], ['rivals', 'Finding closest rivals'], ['screen', 'Screening sanctions and news'],
];
const SUGGEST = ['Adyen', 'Revolut', 'Checkout.com', 'Klarna', 'Spendesk'];

export function render(ctx) {
  const q = ctx.parts[1] ? decodeURIComponent(ctx.parts.slice(1).join('/')) : ctx.qs.get('q');
  if (!q) return renderEmpty(ctx);
  return run(ctx, q);
}

function renderEmpty(ctx, value = '') {
  ctx.app.innerHTML = `<main class="main start" style="padding-top:72px">
    <section class="hero in"><h1>Check one company</h1><p>A sourced risk report from Cala in about 30 seconds: people, owners, events, rivals and sanctions.</p></section>
    <div class="sec in" style="animation-delay:.05s">
      <form class="bigin" id="ckForm" autocomplete="off"><label for="ckIn" class="sr">Company name</label>
        <input id="ckIn" placeholder="Company name, website or LEI" value="${esc(value)}" spellcheck="false"><button class="btn dark lg" type="submit">Run check</button></form>
      <div class="suggest" style="margin-top:6px"><span class="meta" style="align-self:center;margin-right:4px">Try</span>${SUGGEST.map(s => `<button type="button" class="src" data-sg="${esc(s)}">${esc(s)}</button>`).join('')}</div>
    </div></main>`;
  const go = v => v && ctx.go('#/check?q=' + encodeURIComponent(v));
  $('#ckForm').onsubmit = e => { e.preventDefault(); go($('#ckIn').value.trim()); };
  $$('[data-sg]').forEach(b => b.onclick = () => go(b.dataset.sg));
  $('#ckIn').focus();
}

const looksLikeId = q => /^[0-9a-f-]{16,}$/i.test(q) || /^[a-z]+-[a-z0-9-]+$/.test(q);

function stepHTML(key, label, st) {
  const s = st?.status || 'pending';
  const icon = s === 'done' ? '✓' : s === 'error' ? '!' : '';
  return `<div class="step ${s}" data-step="${key}"><span class="ic" aria-hidden="true">${icon}</span><span>${esc(st?.label || label)}${st?.detail ? `<span class="d">${esc(st.detail)}</span>` : ''}</span><span class="sr">${s}</span></div>`;
}

function run(ctx, q) {
  const steps = {};
  const t0 = Date.now();
  const r = {};          // accumulates partial sections, then the final result
  const pend = {};       // sections still being enriched (people notes, investors)
  let shell = false;
  ctx.app.innerHTML = `<main class="main">
    <div class="check-head in"><span class="meta" id="ckMeta">Checking in Cala · <span id="ckT">0 s</span></span><h1>${esc(looksLikeId(q) ? 'Company check' : q)}</h1></div>
    <div class="card in" aria-live="polite"><div class="steps" id="steps">${STEPS.map(([k, l]) => stepHTML(k, l)).join('')}</div></div>
    <div class="sec" aria-hidden="true" style="opacity:.7">
      <div class="card" style="padding:22px;display:flex;flex-direction:column;gap:12px"><div class="sk sk-line" style="width:140px"></div><div class="sk" style="height:16px;width:75%"></div><div class="sk sk-line" style="width:50%"></div></div>
      <div class="card facts">${Array.from({ length: 4 }, () => `<div class="fact"><div class="sk sk-line" style="width:70px"></div><div class="sk" style="height:16px;width:60%;margin-top:6px"></div></div>`).join('')}</div>
    </div></main>`;
  const secs = () => Math.round((Date.now() - t0) / 1000);
  const timer = setInterval(() => {
    const el = $('#ckT'); if (!el) return;
    const s = secs();
    el.textContent = s < 45 ? s + ' s' : `${s} s · Cala is still reading, larger companies take longer`;
  }, 500);
  const drawSteps = () => {
    const el = $('#steps'); if (el) el.innerHTML = STEPS.map(([k, l]) => stepHTML(k, l, steps[k])).join('');
    const lb = $('#liveSteps'); if (lb) lb.innerHTML = liveStepsHTML(steps);
  };
  const close = api.check(q, {
    step(s) { if (!ctx.isCurrent()) return; steps[s.key] = s; drawSteps(); },
    partial(p) {
      if (!ctx.isCurrent()) return;
      if (p.section === 'screen') Object.assign(r, p.data, { screened: true });
      else if (p.section === 'company') r.company = p.data;
      else r[p.section] = p.data;
      if (p.section === 'rivals' && p.late) r.rivals_late = true;
      pend[p.section] = !!p.pending;
      if (!shell) { shell = true; renderReport(ctx, q, r, { live: true, pend }); drawSteps(); return; }
      fillSection(ctx, q, r, p.section === 'company' ? 'head' : p.section, pend);
    },
    result(res) { clearInterval(timer); if (ctx.isCurrent()) { Object.assign(r, res, { screened: true }); renderReport(ctx, q, r, { animate: !shell }); } },
    error(msg) {
      clearInterval(timer);
      if (!ctx.isCurrent()) return;
      const notFound = /not (be )?found|isn.t in cala|no match|no company match|could not match|unknown|type a company/i.test(msg);
      if (shell) {  // partial report already on screen: keep it, flag the gap
        $('#liveBar')?.remove();
        $$('.sk-sec').forEach(x => { x.innerHTML = `<div class="card scard"><span class="cap">Didn’t load</span><span>${esc(msg)}</span></div>`; });
        $('#ckMeta').textContent = 'Check interrupted · partial report';
        $('#ckActs')?.insertAdjacentHTML('afterbegin', `<button type="button" class="btn dark lg" id="retry">Retry</button>`);
        $('#retry').onclick = () => run(ctx, q);
        return;
      }
      const main = $('main');
      main.querySelectorAll('.sec[aria-hidden], .step.pending').forEach(x => x.remove());
      main.insertAdjacentHTML('beforeend', notFound
        ? `<div class="card scard in"><span class="cap">Not found</span><span>“${esc(q)}” isn’t in Cala.</span><button type="button" class="btn" style="align-self:flex-start" id="again">Try another spelling</button></div>`
        : `<div class="card scard in"><span class="cap">Source error</span><span>${esc(msg)}</span><div style="display:flex;gap:8px"><button type="button" class="btn" id="retry">Retry</button><button type="button" class="btn ghost" id="again">Check another company</button></div></div>`);
      $('#ckMeta').textContent = notFound ? 'No match in Cala' : 'Check interrupted';
      $('#again') && ($('#again').onclick = () => renderEmpty(ctx, q));
      $('#retry') && ($('#retry').onclick = () => run(ctx, q));
    },
  });
  ctx.onCleanup(() => { clearInterval(timer); close?.(); });
}

function liveStepsHTML(steps) {
  const done = STEPS.filter(([k]) => steps[k]?.status === 'done').length;
  const running = STEPS.filter(([k]) => steps[k]?.status === 'running').map(([k, l]) => steps[k].label || l);
  return `<span class="spin" aria-hidden="true"></span><span class="grow">${esc(running.join(' · ') || 'Finishing up')}</span><span class="meta">${done} of ${STEPS.length}</span>`;
}

function factBtn(f, i, n) {
  const cls = `fact${i >= n - (n % 2 === 0 ? 2 : 1) ? ' last' : ''}${i === n - 2 && n % 2 === 0 ? ' last2' : ''}`;
  const has = f.sources?.length;
  return `<${has ? `button type="button" data-fact="${i}"` : 'div'} class="${cls}"><span class="k">${esc(f.label)}${has ? '<span class="dot" aria-hidden="true"></span>' : ''}</span><span class="v">${esc((/legal name|also known/i.test(f.label) ? nm(f.value) : /^\d{4}-\d{2}-\d{2}$/.test(f.value) ? fmtDate(f.value, { year: true }) : f.value) || '—')}</span></${has ? 'button' : 'div'}>`;
}

// Skeletons shaped like each section's final rows.
const skRows = (n, w = ['40%', '22%']) => `<div class="card">${Array.from({ length: n }, () => `<div class="row"><span class="grow"><span class="sk sk-line" style="display:block;width:${w[0]}"></span></span><span class="sk sk-line" style="width:${w[1]};display:block"></span></div>`).join('')}</div>`;
const skFind = () => `<div class="card">${[0, 1].map(() => `<div class="find"><div class="lbls"><span class="sk" style="height:22px;width:60px;border-radius:99px"></span><span class="sk" style="height:22px;width:70px;border-radius:99px"></span></div><div class="sk" style="height:16px;width:70%"></div><div class="sk sk-line" style="width:90%"></div></div>`).join('')}</div>`;
const none = text => `<div class="card"><div class="row"><span class="meta">${esc(text)}</span></div></div>`;

const ref = (x, type) => ({ id: x.id, name: x.name, type });
const SECTION = {
  findings(r) {
    if (!r.screened) return { title: 'Findings', body: skFind(), sk: true };
    const fs = r.findings || [];
    return {
      title: 'Findings',
      body: (fs.length ? `<div class="card">${fs.map(f => `<div class="find">
          <div class="lbls">${sevPill(f.severity)}${statusPill(f.status)}<span class="meta">${esc([f.category ? f.category[0].toUpperCase() + f.category.slice(1) : '', f.date ? fmtDate(f.date) : ''].filter(Boolean).join(' · '))}</span></div>
          <span class="t">${esc(f.title)}</span>
          <div class="acts" style="gap:8px">${f.body ? `<span class="muted" style="font-size:13px">${esc(f.body)}</span>` : ''}${srcChips(f.sources, 1)}</div></div>`).join('')}</div>`
        : r.unavailable ? `<div class="card state"><span class="ic">!</span><b>Screening didn’t finish</b><span>Cala’s news screen timed out. Re-run the check in a minute.</span></div>`
        : `<div class="card state"><span class="ic">✓</span><b>No adverse findings</b><span>In Cala and the news, ${esc(r.period || 'last 12 months')}.</span></div>`)
        + (r.sanctions && !r.unavailable ? `<div class="sanc"><span class="tick ${r.sanctions.clear ? '' : 'warn'}">${r.sanctions.clear ? '✓' : '!'}</span><span class="grow">${/^(no )?sanction/i.test(r.sanctions.text || '') ? '' : 'Sanctions: '}${esc(r.sanctions.text || '')}</span>${srcChips(r.sanctions.sources, 1)}</div>` : ''),
    };
  },
  facts(r) {
    const facts = (r.facts || []).filter(f => f.value);
    if (!r.facts) return { title: 'Company', body: `<div class="card facts">${Array.from({ length: 4 }, () => `<div class="fact"><div class="sk sk-line" style="width:70px"></div><div class="sk" style="height:16px;width:60%;margin-top:6px"></div></div>`).join('')}</div>`, sk: true };
    return { title: 'Company', body: facts.length ? `<div class="card facts">${facts.map((f, i) => factBtn(f, i, facts.length)).join('')}</div>` : none('No registry facts in Cala'), note: facts.length ? 'Every field with a dot opens its Cala source and date.' : '' };
  },
  people(r, pend) {
    if (!r.people) return { title: 'People', body: skRows(3), sk: true };
    return {
      title: 'People',
      body: r.people.length ? `<div class="card">${r.people.map(p => `<div class="row" style="flex-wrap:wrap"><span class="grow" style="font-weight:500">${entLink(ref(p, 'Person'))}</span>${p.note ? `<span class="pill soft">${esc(p.note)}</span>` : ''}<span class="meta" style="color:var(--muted)">${esc(p.role || '')}</span></div>`).join('')}</div>` : none('No people listed in Cala'),
      note: pend?.people && r.people.length ? '<span class="spin" style="width:10px;height:10px;vertical-align:-1px;margin-right:6px"></span>Looking up their other roles…' : '',
    };
  },
  ownership(r, pend) {
    if (!r.ownership) return { title: 'Ownership', body: skRows(3), sk: true };
    if (pend?.ownership && !r.ownership.length) return { title: 'Ownership', body: skRows(3), sk: true };
    return {
      title: 'Ownership',
      body: r.ownership.length ? `<div class="card">${r.ownership.map(o => `<div class="row" style="flex-wrap:wrap"><span class="grow" style="font-weight:500">${entLink(ref(o, 'Investor'))}</span>${o.note ? `<span class="pill soft">${esc(o.note)}</span>` : ''}</div>`).join('')}</div>` : none('No owners or investors in Cala'),
      note: pend?.ownership ? '<span class="spin" style="width:10px;height:10px;vertical-align:-1px;margin-right:6px"></span>Reading funding rounds for investors…' : '',
    };
  },
  funding(r) {
    if (!r.funding) return { title: 'Funding and M&A', body: skRows(3, ['50%', '12%']), sk: true };
    return { title: 'Funding and M&A', body: r.funding.length ? `<div class="card">${r.funding.map(f => `<div class="row frow"><span style="width:76px;flex-shrink:0;color:var(--faint)">${esc(fmtMonth(f.date) || '—')}</span><span class="grow">${esc(f.label)}</span>${srcChips(f.sources, 1)}<span style="font-weight:600;${f.amount ? '' : 'color:var(--faint)'}">${esc(f.amount || '—')}</span></div>`).join('')}</div>` : none('No funding rounds or M&A in Cala') };
  },
  rivals(r) {
    if (!r.rivals) return { title: 'Closest rivals', body: skRows(4, ['30%', '30%']), sk: true };
    return { title: 'Closest rivals', body: r.rivals.length ? `<div class="card">${r.rivals.map(x => `<div class="row" style="flex-wrap:wrap"><span class="grow" style="font-weight:500">${entLink(ref(x, 'Company'))}</span>${x.sub ? `<span class="meta rsub" style="color:var(--muted)">${esc(x.sub)}</span>` : ''}${x.in_portfolio ? '<span class="pill soft">Your portfolio</span>' : `<a class="btn ghost" href="#/check/${encodeURIComponent(x.id)}" aria-label="Check ${esc(x.name)}">Check →</a>`}</div>`).join('')}</div>` : none(r.rivals_late ? 'Cala is still finding rivals. Re-run the check shortly.' : 'No close rivals found in Cala') };
  },
};
const ORDER = ['findings', 'facts', 'people', 'ownership', 'funding', 'rivals'];

function sectionInner(name, r, pend) {
  const s = SECTION[name](r, pend);
  return `<h2 class="h">${s.title}</h2>${s.body}${s.note ? `<span class="note">${s.note}</span>` : ''}`;
}

function countsHTML(r) {
  if (!r.screened) return `<div class="card counts" id="cnt">${[0, 1, 2].map(() => `<div><div class="sk" style="height:30px;width:36px"></div><div class="sk sk-line" style="width:50px;margin-top:6px"></div></div><div class="sep"></div>`).join('')}<div class="info"><div class="sk sk-line" style="width:80%"></div><div class="sk sk-line" style="width:55%;margin-top:6px"></div></div></div>`;
  const counts = r.counts || { high: 0, medium: 0, low: 0 };
  return `<div class="card counts" id="cnt">
      <div><span class="n" style="color:${counts.high ? 'var(--accent)' : 'inherit'}">${counts.high || 0}</span><span class="l">High</span></div><div class="sep"></div>
      <div><span class="n">${counts.medium || 0}</span><span class="l">Medium</span></div><div class="sep"></div>
      <div><span class="n">${counts.low || 0}</span><span class="l">Low</span></div><div class="sep last"></div>
      <div class="info">${r.stats ? `${(r.stats.facts ?? 0).toLocaleString()} Cala facts · ${plural(r.stats.entities ?? 0, 'entity', 'entities')} screened<br>` : ''}${esc(r.period || 'Last 12 months')}</div>
    </div>`;
}

function headHTML(r, q, live) {
  const c = r.company || {};
  const checked = r.checked_at ? fmtDate(r.checked_at.slice(0, 10), { year: true }) : 'now';
  return `<span class="meta" id="ckMeta">${live ? `Checking in Cala · <span id="ckT">…</span>` : `Checked ${esc(checked)} · last 12 months · ${r.seconds >= 1 ? Math.round(r.seconds) + ' s' : 'under 1 s'}`}</span>
      <h1>${esc(nm(c.name || q))}</h1>
      <div class="chips" style="align-items:center">${(c.tags || []).filter(Boolean).map(t => `<span class="pill rep">${esc(t)}</span>`).join('')}
        ${c.lei ? `<span class="note" style="margin-left:4px">Matched in Cala by LEI</span>` : c.website ? `<span class="note" style="margin-left:4px">${esc(c.website)}</span>` : ''}</div>
      ${c.description ? `<p class="muted" style="max-width:600px">${esc(c.description)}</p>` : ''}`;
}

function fillSection(ctx, q, r, name, pend) {
  if (name === 'head') { const h = $('#ckHead'); if (h) h.innerHTML = headHTML(r, q, true); return; }
  if (name === 'screen') {
    $('#cnt')?.replaceWith(Object.assign(document.createElement('div'), { innerHTML: countsHTML(r) }).firstElementChild);
    $('#cnt')?.classList.add('in');
    name = 'findings';
  }
  const el = $(`#s-${name}`); if (!el) return;
  const s = SECTION[name](r, pend);
  el.classList.toggle('sk-sec', !!s.sk);
  el.innerHTML = sectionInner(name, r, pend);
  el.classList.remove('in'); void el.offsetWidth; el.classList.add('in');
  wireFacts(r);
}

function wireFacts(r) {
  const facts = (r.facts || []).filter(f => f.value);
  $$('[data-fact]').forEach(b => b.onclick = () => {
    const f = facts[+b.dataset.fact];
    openPopover(b, `<span class="cap">${esc(f.label)}</span><button type="button" class="x" aria-label="Close" data-close>×</button><span class="pop-t">${esc(f.value)}</span><div class="chips">${f.sources.map(srcChip).join('')}</div>`, { label: f.label });
  });
}

function renderReport(ctx, q, r, { live = false, pend = {}, animate = true } = {}) {
  const c = r.company || {};
  const inPf = (ctx.store.portfolio?.companies || []).some(x => x.id === c.id);
  ctx.app.innerHTML = `<main class="main${animate ? ' stagger' : ''}">
    <div class="check-head" id="ckHead">${headHTML(r, q, live)}</div>
    ${live ? `<div class="card livebar" id="liveBar" aria-live="polite"><div id="liveSteps" class="livesteps"></div></div>` : ''}
    ${countsHTML(r)}
    ${ORDER.map(n => { const s = SECTION[n](r, pend); return `<section class="sec${s.sk ? ' sk-sec' : ''}" id="s-${n}">${sectionInner(n, r, pend)}</section>`; }).join('')}
    <div style="display:flex;gap:8px;flex-wrap:wrap" id="ckActs">
      <button type="button" class="btn ${inPf ? '' : 'dark'} lg" id="watch" ${inPf || !c.id ? 'disabled' : ''}>${inPf ? 'In your portfolio ✓' : 'Watch this company'}</button>
      ${live ? '' : `<button type="button" class="btn lg" id="rerun">Re-run</button>`}
      <button type="button" class="btn lg" id="share">Copy link</button>
      <button type="button" class="btn lg" data-ask="${esc(`What are the biggest risks for ${c.name || q} right now?`)}">Ask about ${esc(nm(c.name || q))}</button>
    </div>
  </main>`;

  wireFacts(r);
  $('#rerun') && ($('#rerun').onclick = () => run(ctx, q));
  $('#share').onclick = async () => {
    const url = location.href.split('#')[0] + '#/check/' + encodeURIComponent(c.id || q);
    try { await navigator.clipboard.writeText(url); toast('Link copied'); } catch { toast(url); }
  };
  $('#watch').onclick = async () => {
    const b = $('#watch'); b.disabled = true; b.textContent = 'Adding…';
    try {
      const ids = [...new Set([...(ctx.store.portfolio?.companies || []).map(x => x.id), c.id])].filter(Boolean);
      await api.savePortfolio(ids);
      ctx.store.portfolio = { ...(ctx.store.portfolio || {}), companies: [...(ctx.store.portfolio?.companies || []), { id: c.id, name: c.name }], building: true };
      b.textContent = 'In your portfolio ✓';
      toast(`Watching ${c.name}. Rebuilding your perimeter…`, { label: 'View feed', run: () => ctx.go('#/') });
      refreshPortfolio();
    } catch (err) { b.disabled = false; b.textContent = 'Watch this company'; toast('Couldn’t add: ' + err.message); }
  };
}

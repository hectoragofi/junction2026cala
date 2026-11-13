import { api } from '../api.js';
import { $, $$, esc, srcChips, srcChip, entLink, sevPill, statusPill, fmtDate, fmtMonth, toast, plural, lookup, openPopover } from '../ui.js';
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
  ctx.app.innerHTML = `<main class="main">
    <div class="check-head in"><span class="meta" id="ckMeta">Checking in Cala · <span id="ckT">0 s</span></span><h1>${esc(looksLikeId(q) ? 'Company check' : q)}</h1></div>
    <div class="card in" aria-live="polite"><div class="steps" id="steps">${STEPS.map(([k, l]) => stepHTML(k, l)).join('')}</div></div>
    <div class="sec" aria-hidden="true" style="opacity:.7">
      <div class="card counts"><div class="sk" style="height:56px;flex:1"></div></div>
      <div class="sk" style="height:12px;width:80px"></div>
      <div class="card" style="padding:22px;display:flex;flex-direction:column;gap:12px"><div class="sk sk-line" style="width:140px"></div><div class="sk" style="height:16px;width:75%"></div><div class="sk sk-line" style="width:50%"></div></div>
      <div class="card" style="padding:22px;display:flex;flex-direction:column;gap:12px"><div class="sk sk-line" style="width:120px"></div><div class="sk" style="height:16px;width:65%"></div></div>
    </div></main>`;
  const timer = setInterval(() => { const el = $('#ckT'); if (!el) return; const s = Math.round((Date.now() - t0) / 1000); el.textContent = s < 45 ? s + ' s' : `${s} s · Cala is still reading, larger companies take longer`; }, 500);
  const drawSteps = () => { const el = $('#steps'); if (el) el.innerHTML = STEPS.map(([k, l]) => stepHTML(k, l, steps[k])).join(''); };
  const close = api.check(q, {
    step(s) {
      if (!ctx.isCurrent()) return;
      // a step starting implies earlier running ones are done
      if (s.status === 'running') for (const [k] of STEPS) { if (k === s.key) break; if (steps[k]?.status === 'running') steps[k].status = 'done'; }
      steps[s.key] = s; drawSteps();
    },
    result(r) { clearInterval(timer); if (ctx.isCurrent()) renderReport(ctx, q, r); },
    error(msg) {
      clearInterval(timer);
      if (!ctx.isCurrent()) return;
      const notFound = /not (be )?found|isn.t in cala|no match|no company match|could not match|unknown|type a company/i.test(msg);
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

function factBtn(f, i, n) {
  const cls = `fact${i >= n - (n % 2 === 0 ? 2 : 1) ? ' last' : ''}${i === n - 2 && n % 2 === 0 ? ' last2' : ''}`;
  const has = f.sources?.length;
  return `<${has ? `button type="button" data-fact="${i}"` : 'div'} class="${cls}"><span class="k">${esc(f.label)}${has ? '<span class="dot" aria-hidden="true"></span>' : ''}</span><span class="v">${esc(f.value || '—')}</span></${has ? 'button' : 'div'}>`;
}

function renderReport(ctx, q, r) {
  const c = r.company || {};
  const counts = r.counts || { high: 0, medium: 0, low: 0 };
  const inPf = (ctx.store.portfolio?.companies || []).some(x => x.id === c.id);
  const facts = (r.facts || []).filter(f => f.value);
  const checked = r.checked_at ? fmtDate(r.checked_at.slice(0, 10), { year: true }) : 'now';
  const ref = (x, type) => ({ id: x.id, name: x.name, type });
  const person = p => `<div class="row" style="flex-wrap:wrap"><span class="grow" style="font-weight:500">${entLink(ref(p, 'Person'))}</span>${p.note ? `<span class="pill soft">${esc(p.note)}</span>` : ''}<span class="meta" style="color:var(--muted)">${esc(p.role || '')}</span></div>`;
  const owner = o => `<div class="row" style="flex-wrap:wrap"><span class="grow" style="font-weight:500">${entLink(ref(o, 'Investor'))}</span>${o.note ? `<span class="pill soft">${esc(o.note)}</span>` : ''}</div>`;
  const section = (title, body, note = '') => body ? `<section class="sec"><h2 class="h">${title}</h2>${body}${note ? `<span class="note">${note}</span>` : ''}</section>` : '';

  ctx.app.innerHTML = `<main class="main stagger">
    <div class="check-head">
      <span class="meta">Checked ${esc(checked)} · last 12 months · ${Math.round(r.seconds || 0)} s</span>
      <h1>${esc(c.name || q)}</h1>
      <div class="chips" style="align-items:center">${(c.tags || []).filter(Boolean).map(t => `<span class="pill rep">${esc(t)}</span>`).join('')}
        ${c.lei ? `<span class="note" style="margin-left:4px">Matched in Cala by LEI</span>` : c.website ? `<span class="note" style="margin-left:4px">${esc(c.website)}</span>` : ''}</div>
      ${c.description ? `<p class="muted" style="max-width:600px">${esc(c.description)}</p>` : ''}
    </div>

    <div class="card counts">
      <div><span class="n" style="color:${counts.high ? 'var(--accent)' : 'inherit'}">${counts.high || 0}</span><span class="l">High</span></div><div class="sep"></div>
      <div><span class="n">${counts.medium || 0}</span><span class="l">Medium</span></div><div class="sep"></div>
      <div><span class="n">${counts.low || 0}</span><span class="l">Low</span></div><div class="sep last"></div>
      <div class="info">${(r.stats?.facts ?? 0).toLocaleString()} Cala facts · ${plural(r.stats?.entities ?? 0, 'entity', 'entities')} screened<br>${esc(r.period || '')}</div>
    </div>

    <section class="sec"><h2 class="h">Findings</h2>
      ${(r.findings || []).length ? `<div class="card">${r.findings.map(f => `<div class="find">
          <div class="lbls">${sevPill(f.severity)}${statusPill(f.status)}<span class="meta">${esc(f.category || '')}</span></div>
          <span class="t">${esc(f.title)}</span>
          <div class="acts" style="gap:8px">${f.body ? `<span class="muted" style="font-size:13px">${esc(f.body)}</span>` : ''}${srcChips(f.sources, 1)}</div></div>`).join('')}</div>`
      : `<div class="card state"><span class="ic">✓</span><b>No adverse findings</b><span>In Cala and the news, ${esc(r.period || 'last 12 months')}.</span></div>`}
      ${r.sanctions ? `<div class="sanc"><span class="tick ${r.sanctions.clear ? '' : 'warn'}">${r.sanctions.clear ? '✓' : '!'}</span><span class="grow">Sanctions: ${esc(r.sanctions.text || (r.sanctions.clear ? `no matches across ${r.sanctions.screened} entities.` : 'possible match.'))}</span>${srcChips(r.sanctions.sources, 1)}</div>` : ''}
    </section>

    ${section('Company', facts.length ? `<div class="card facts">${facts.map((f, i) => factBtn(f, i, facts.length)).join('')}</div>` : '', 'Every field with a dot opens its Cala source and date.')}
    ${section('People', (r.people || []).length ? `<div class="card">${r.people.map(person).join('')}</div>` : '')}
    ${section('Ownership', (r.ownership || []).length ? `<div class="card">${r.ownership.map(owner).join('')}</div>` : '')}
    ${section('Funding', (r.funding || []).length ? `<div class="card">${r.funding.map(f => `<div class="row frow"><span style="width:76px;flex-shrink:0;color:var(--faint)">${esc(fmtMonth(f.date))}</span><span class="grow">${esc(f.label)}</span>${srcChips(f.sources, 1)}<span style="font-weight:600;${f.amount ? '' : 'color:var(--faint)'}">${esc(f.amount || '—')}</span></div>`).join('')}</div>` : '')}
    ${section('Closest rivals', (r.rivals || []).length ? `<div class="card">${r.rivals.map(x => `<div class="row" style="flex-wrap:wrap"><span class="grow" style="font-weight:500">${entLink(ref(x, 'Company'))}</span>${x.sub ? `<span class="meta" style="color:var(--muted)">${esc(x.sub)}</span>` : ''}${x.in_portfolio ? '<span class="pill soft">Your portfolio</span>' : `<a class="btn ghost" href="#/check/${encodeURIComponent(x.id)}" aria-label="Check ${esc(x.name)}">Check →</a>`}</div>`).join('')}</div>` : '')}

    <div style="display:flex;gap:8px;flex-wrap:wrap">
      <button type="button" class="btn ${inPf ? '' : 'dark'} lg" id="watch" ${inPf ? 'disabled' : ''}>${inPf ? 'In your portfolio ✓' : 'Watch this company'}</button>
      <button type="button" class="btn lg" id="rerun">Re-run</button>
      <button type="button" class="btn lg" id="share">Copy link</button>
      <button type="button" class="btn lg" data-ask="${esc(`What are the biggest risks for ${c.name || q} right now?`)}">Ask about ${esc(c.name || q)}</button>
    </div>
  </main>`;

  $$('[data-fact]').forEach(b => b.onclick = () => {
    const f = facts[+b.dataset.fact];
    openPopover(b, `<span class="cap">${esc(f.label)}</span><button type="button" class="x" aria-label="Close" data-close>×</button><span class="pop-t">${esc(f.value)}</span><div class="chips">${f.sources.map(srcChip).join('')}</div>`, { label: f.label });
  });
  $('#rerun').onclick = () => run(ctx, q);
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

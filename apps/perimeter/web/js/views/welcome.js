// Onboarding at `/` for new visitors: pick a seat (founder / investor / demo), name the companies, then build.
// Self-contained: talks to the API only through api.saveProfile and the shared confirm UI in start.js.
import { api, setView } from '../api.js';
import { loadMe, hasProfile, switchView, profileLabel } from '../app.js';
import { $, $$, esc } from '../ui.js';
import { resolveRows, mountConfirm, skRows } from './start.js';

const ICON = {
  founder: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 2.8c2.6 1.6 3.9 4.3 3.6 7.6l-1.7 2.4H8.1l-1.7-2.4C6.1 7.1 7.4 4.4 10 2.8Z"/><circle cx="10" cy="7.6" r="1.3"/><path d="M8.1 12.8 7.2 16.5l2.8-1.6 2.8 1.6-.9-3.7"/></svg>',
  investor: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><circle cx="10" cy="10" r="2.2"/><circle cx="4.2" cy="5" r="1.5"/><circle cx="15.8" cy="5" r="1.5"/><circle cx="4.2" cy="15" r="1.5"/><circle cx="15.8" cy="15" r="1.5"/><path d="M8.3 8.6 5.4 6.1M11.7 8.6l2.9-2.5M8.3 11.4l-2.9 2.5M11.7 11.4l2.9 2.5"/></svg>',
  demo: '<svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="10" cy="10" r="2.4"/><circle cx="10" cy="10" r="6.5" stroke-dasharray="2 2.4"/><circle cx="16.5" cy="10" r="1.4" fill="currentColor"/></svg>',
};
const steps = n => `<div class="onb-steps" aria-label="Step ${n} of 3">${[1, 2, 3].map(i => `<i class="${i <= n ? 'on' : ''}"></i>`).join('')}</div>`;

export function render(ctx) {
  const step = ctx.parts[1];
  const draw = step === 'founder' ? founder : step === 'investor' ? investor : seat;
  draw(ctx);
  // Esc steps back (unless a menu or dialog is handling it)
  const onKey = e => {
    if (e.key !== 'Escape' || document.querySelector('.scrim,.menu,.pop,.modal')) return;
    if (step === 'founder' || step === 'investor') ctx.go('#/welcome');
    else if (hasProfile()) ctx.go('#/');
  };
  document.addEventListener('keydown', onKey);
  ctx.onCleanup(() => document.removeEventListener('keydown', onKey));
}

function seat(ctx) {
  const mine = hasProfile();
  ctx.app.innerHTML = `<main class="main start onb">
    ${steps(1)}
    <section class="hero in">
      <h1>Which seat are you in?</h1>
      <p>Perimeter watches everything around a company on Cala’s knowledge graph and tells you, with sources, when something changes.</p>
    </section>
    <div class="seats stagger" role="list">
      <button type="button" class="seat" data-seat="founder" role="listitem">
        <span class="ic">${ICON.founder}</span>
        <span class="tx"><b>I’m raising</b><span>Watch your rivals and the investors around you.</span></span>
        <span class="arr" aria-hidden="true">→</span></button>
      <button type="button" class="seat" data-seat="investor" role="listitem">
        <span class="ic">${ICON.investor}</span>
        <span class="tx"><b>I’m investing</b><span>Watch your portfolio: rivals, shared investors and board overlaps.</span></span>
        <span class="arr" aria-hidden="true">→</span></button>
    </div>
    <div class="sec in" style="animation-delay:.12s">
      <div class="or">or</div>
      <button type="button" class="demo-cta" data-seat="demo">
        <span class="ic">${ICON.demo}</span>
        <span><b>Just explore the demo</b><span>Four real European fintechs, already mapped from Cala.</span></span>
        <span class="arr" aria-hidden="true">→</span></button>
      ${mine ? `<a class="btn ghost onb-back-me" href="#/">Back to ${esc(profileLabel())}</a>` : ''}
    </div>
  </main>`;
  $$('[data-seat]').forEach(b => b.onclick = () => {
    const s = b.dataset.seat;
    if (s === 'demo') { b.disabled = true; switchView('demo'); return; }
    ctx.go('#/welcome/' + s);
  });
}

function topBar(n) {
  return `<div class="onb-top in"><a href="#/welcome" class="btn ghost onb-backbtn" aria-label="Back to choosing a seat">← Back</a>${steps(n)}<span class="onb-sp"></span></div>`;
}

async function finish(ctx, body) {
  await api.saveProfile(body);
  setView('me');
  ctx.store.portfolio = null;
  await loadMe();
  ctx.go('#/');
}

function founder(ctx) {
  const SUGGEST = ['Qonto', 'Mollie', 'Pennylane'];
  ctx.app.innerHTML = `<main class="main start onb">
    ${topBar(2)}
    <section class="hero in"><h1>What are you building?</h1>
      <p>Find your company in Cala. We watch its closest rivals and the investors around it.</p></section>
    <div class="sec in" style="gap:12px;animation-delay:.05s">
      <form class="bigin" id="fForm" autocomplete="off">
        <label for="fIn" class="sr">Your company</label>
        <input id="fIn" placeholder="Your company or its website" spellcheck="false">
        <button type="submit" class="btn dark lg" id="fGo">Find</button>
      </form>
      <div class="suggest" style="justify-content:center"><span class="meta" style="align-self:center;margin-right:4px">Try</span>${SUGGEST.map(s => `<button type="button" class="src" data-sg="${esc(s)}">${esc(s)}</button>`).join('')}</div>
    </div>
    <div id="confirm" aria-live="polite"></div>
  </main>`;
  const input = $('#fIn'), form = $('#fForm');
  input.focus();
  $$('[data-sg]').forEach(b => b.onclick = () => { input.value = b.dataset.sg; form.requestSubmit(); });
  form.onsubmit = async e => {
    e.preventDefault();
    const v = input.value.trim().split(/[\n,;]+/)[0].trim();
    if (!v) { input.focus(); return; }
    const box = $('#confirm');
    box.innerHTML = skRows(1);
    $('#fGo').disabled = true;
    try {
      const rows = (await resolveRows(v)).slice(0, 1);
      if (!rows[0] || !rows[0].candidates.length) {
        box.innerHTML = `<div class="card state in"><b>No match for “${esc(v)}”</b><span>Try the legal name or the website, like qonto.com.</span></div>`;
        return;
      }
      box.innerHTML = `<div id="cList"></div><div class="onb-name in"><div class="field"><label for="fName">Your name <span class="opt">optional</span></label><input id="fName" placeholder="Shown on your profile" maxlength="60"></div></div><div id="cGo"></div>`;
      const go = document.createElement('button');
      go.type = 'button'; go.className = 'btn acc lg onb-go';
      const label = () => `Watch the market around ${rows[0] ? (rows[0].candidates[rows[0].pick]?.name || 'it') : 'it'}`;
      const conf = mountConfirm($('#cList'), rows, { title: () => 'Is this your company?', hideCta: true, onChange: () => { go.textContent = label(); }, onEmpty: () => { box.innerHTML = ''; input.focus(); } });
      go.textContent = label();
      $('#cGo').append(go);
      go.onclick = async () => {
        const id = conf.ids()[0]; if (!id) return;
        go.disabled = true; go.innerHTML = '<span class="spin" aria-hidden="true"></span>Setting up…';
        try { await finish(ctx, { role: 'founder', my_company_id: id, name: $('#fName').value.trim() || null }); }
        catch (err) { go.disabled = false; go.textContent = label(); errorCard(box, err); }
      };
      go.focus();
    } catch (err) { errorCard(box, err, () => form.requestSubmit()); }
    finally { $('#fGo') && ($('#fGo').disabled = false); }
  };
}

function investor(ctx) {
  ctx.app.innerHTML = `<main class="main start onb">
    ${topBar(2)}
    <section class="hero in"><h1>What do you back?</h1>
      <p>Paste your portfolio page or a few company names. We map rivals, co-investors and boards around each one.</p></section>
    <div class="sec in" style="gap:14px;animation-delay:.05s">
      <div class="field"><label for="iFund">Fund name <span class="opt">optional</span></label><input id="iFund" placeholder="e.g. Northzone" maxlength="60"></div>
      <form class="bigin" id="iForm" autocomplete="off">
        <label for="iIn" class="sr">Company names or portfolio page link</label>
        <input id="iIn" placeholder="Mollie, Pennylane" spellcheck="false">
        <button type="submit" class="btn dark lg" id="iGo">Continue</button>
      </form>
      <p class="meta" style="text-align:center">Company names separated by commas, or a link to your portfolio page.</p>
    </div>
    <div id="confirm" aria-live="polite"></div>
  </main>`;
  const input = $('#iIn'), form = $('#iForm');
  $('#iFund').focus();
  $('#iFund').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); input.focus(); } };
  form.onsubmit = async e => {
    e.preventDefault();
    const v = input.value.trim();
    if (!v) { input.focus(); return; }
    const box = $('#confirm');
    box.innerHTML = skRows(v.split(/[\n,;]+/).filter(s => s.trim()).length);
    $('#iGo').disabled = true;
    try {
      const rows = await resolveRows(v);
      mountConfirm(box, rows, {
        cta: n => `Start watching ${n} ${n === 1 ? 'company' : 'companies'}`,
        onGo: ids => finish(ctx, { role: 'investor', fund_or_company_name: $('#iFund').value.trim() || null, portfolio_ids: ids }),
        onEmpty: () => input.focus(),
      });
      box.querySelector('[data-go]')?.focus();
    } catch (err) { errorCard(box, err, () => form.requestSubmit()); }
    finally { $('#iGo') && ($('#iGo').disabled = false); }
  };
}

function errorCard(box, err, retry) {
  box.innerHTML = `<div class="card scard in"><span class="cap">Source error</span><span>Couldn’t reach Cala. ${esc(err.message)}</span>${retry ? '<button type="button" class="btn" style="align-self:flex-start" data-retry>Retry</button>' : ''}</div>`;
  if (retry) box.querySelector('[data-retry]').onclick = retry;
}

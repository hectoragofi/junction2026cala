import { api } from '../api.js';
import { $, $$, esc, openMenu, toast, plural } from '../ui.js';

const BUILD_LINES = [
  'Resolving each company in Cala’s knowledge graph',
  'Finding closest rivals',
  'Mapping investors and cap tables',
  'Linking founders, executives and board members',
  'Looking for overlaps across your companies',
  'Reading corporate events and news',
  'Screening sanctions lists',
];

export function render(ctx) {
  const { app } = ctx;
  let mode = ctx.qs.get('mode') === 'check' ? 'check' : 'watch';
  let rows = []; // {query, best, candidates, pick (index or -1)}
  app.innerHTML = `<main class="main start">
    <section class="hero in">
      <h1>Know first when something<br>changes around your bets.</h1>
      <p>Sourced risk checks and a quiet feed for your portfolio, built on Cala’s knowledge graph.</p>
    </section>
    <div class="sec in" style="gap:12px;animation-delay:.05s">
      <div class="seg" role="tablist" aria-label="Mode" style="align-self:center">
        <button type="button" role="tab" data-mode="watch">Watch a portfolio</button>
        <button type="button" role="tab" data-mode="check">Check one company</button>
      </div>
      <form class="bigin" id="startForm" autocomplete="off">
        <label for="startIn" class="sr" id="startLbl">Company names</label>
        <input id="startIn" name="q" spellcheck="false">
        <button type="submit" class="btn dark lg" id="startGo">Continue</button>
      </form>
      <p class="meta" id="startHint" style="text-align:center"></p>
    </div>
    <div id="confirm"></div>
    <div class="sec in" id="demoBox" style="animation-delay:.1s">
      <div class="or">or</div>
      <button type="button" class="demo-cta" id="demoBtn">
        <span class="ic"><svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="10" cy="10" r="2.4"/><circle cx="10" cy="10" r="6.5" stroke-dasharray="2 2.4"/><circle cx="16.5" cy="10" r="1.4" fill="currentColor"/></svg></span>
        <span><b>Try the demo portfolio</b><span>Four real European fintechs, mapped live from Cala.</span></span>
        <span class="arr" aria-hidden="true">→</span>
      </button>
    </div>
  </main>`;
  const input = $('#startIn'), hint = $('#startHint'), form = $('#startForm');

  function setMode(m) {
    mode = m;
    $$('[data-mode]').forEach(b => { const on = b.dataset.mode === m; b.classList.toggle('on', on); b.setAttribute('aria-selected', on); });
    $('#startLbl').textContent = m === 'watch' ? 'Company names or portfolio page link' : 'Company name';
    input.placeholder = m === 'watch' ? 'Mollie, Qonto, Pennylane, GoCardless' : 'Adyen';
    hint.textContent = m === 'watch' ? 'Paste a portfolio page, or company names separated by commas.' : 'A name, website or LEI. Takes about 30 seconds.';
    $('#startGo').textContent = m === 'watch' ? 'Continue' : 'Run check';
    $('#confirm').innerHTML = ''; rows = [];
    $('#demoBox').style.display = m === 'watch' ? '' : 'none';
  }
  $$('[data-mode]').forEach(b => b.onclick = () => { setMode(b.dataset.mode); input.focus(); });
  setMode(mode);
  input.focus();

  form.onsubmit = async e => {
    e.preventDefault();
    const v = input.value.trim();
    if (!v) { input.focus(); return; }
    if (mode === 'check') { ctx.go('#/check?q=' + encodeURIComponent(v)); return; }
    const box = $('#confirm');
    box.innerHTML = `<div class="sec"><div class="sk sk-line" style="width:180px;height:16px"></div><div class="card">${v.split(/[\n,;]+/).filter(s => s.trim()).map(() => `<div class="row"><div class="sk sk-line grow" style="max-width:220px"></div><div class="sk sk-line" style="width:90px"></div></div>`).join('')}</div></div>`;
    $('#startGo').disabled = true;
    try {
      const r = await api.resolve(v);
      rows = (r.matches || []).map(m => ({ ...m, pick: m.best ? Math.max(0, (m.candidates || []).findIndex(c => c.id === m.best.id)) : -1, candidates: m.candidates?.length ? m.candidates : (m.best ? [m.best] : []) }));
      drawConfirm();
    } catch (err) {
      box.innerHTML = `<div class="card scard"><span class="cap">Source error</span><span>Couldn’t reach Cala to match those names. ${esc(err.message)}</span><button type="button" class="btn" style="align-self:flex-start" id="retryRes">Retry</button></div>`;
      $('#retryRes').onclick = () => form.requestSubmit();
    } finally { $('#startGo').disabled = false; }
  };

  function chosen(r) { return r.pick >= 0 ? r.candidates[r.pick] : null; }
  function drawConfirm() {
    const box = $('#confirm');
    if (!rows.length) { box.innerHTML = ''; return; }
    const found = rows.filter(chosen);
    box.innerHTML = `<section class="sec in" aria-label="Confirm companies">
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px">
        <h2 style="font-size:15px;font-weight:600">We found ${plural(found.length, 'company', 'companies')}</h2>
        <span class="meta">Remove any that are wrong</span>
      </div>
      <div class="card stagger">${rows.map((r, i) => {
        const c = chosen(r);
        if (!c) return `<div class="row"><span class="grow" style="font-weight:500;color:var(--faint)">${esc(r.query)}</span><span class="pill nf">Not found</span><button type="button" class="x" data-rm="${i}" aria-label="Remove ${esc(r.query)}">×</button></div>`;
        const multi = r.candidates.length > 1;
        return `<div class="row"><span class="grow" style="min-width:0;display:flex;flex-direction:column">
            <span style="font-weight:500">${esc(c.name)}</span>
            <span class="meta" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc([c.description, c.hq, c.founded && 'founded ' + c.founded].filter(Boolean).join(' · '))}</span></span>
          ${c.website ? `<span class="meta" style="white-space:nowrap">${esc(c.website.replace(/^https?:\/\//, ''))}</span>` : ''}
          ${multi ? `<button type="button" class="cand" data-cand="${i}" aria-haspopup="menu">${r.pick + 1} of ${r.candidates.length} ▾</button>` : ''}
          <button type="button" class="x" data-rm="${i}" aria-label="Remove ${esc(c.name)}">×</button></div>`;
      }).join('')}</div>
      <button type="button" class="btn acc lg" id="watchGo" style="align-self:flex-end" ${found.length ? '' : 'disabled'}>Start watching ${plural(found.length, 'company', 'companies')}</button>
    </section>`;
    $$('[data-rm]', box).forEach(b => b.onclick = () => { rows.splice(+b.dataset.rm, 1); drawConfirm(); });
    $$('[data-cand]', box).forEach(b => b.onclick = () => {
      const r = rows[+b.dataset.cand];
      openMenu(b, r.candidates.map((c, j) => ({ label: c.name, hint: [c.hq, c.founded].filter(Boolean).join(' · '), on: j === r.pick, j })), it => { r.pick = it.j; drawConfirm(); });
    });
    $('#watchGo').onclick = async () => {
      const ids = rows.map(chosen).filter(Boolean).map(c => c.id);
      $('#watchGo').disabled = true;
      try { await api.savePortfolio(ids); startBuilding(ctx); }
      catch (err) { toast('Couldn’t save the portfolio: ' + err.message); $('#watchGo').disabled = false; }
    };
  }

  $('#demoBtn').onclick = async () => {
    const b = $('#demoBtn'); b.disabled = true; b.querySelector('b').textContent = 'Loading the demo portfolio…';
    try { await api.demo(); startBuilding(ctx); }
    catch (err) { toast('Couldn’t load the demo: ' + err.message); b.disabled = false; b.querySelector('b').textContent = 'Try the demo portfolio'; }
  };
}

function startBuilding(ctx) {
  ctx.store.portfolio = { companies: ctx.store.portfolio?.companies || [], building: true };
  if (location.hash.replace(/^#/, '') === '/' || location.hash === '') ctx.go('#/'); else ctx.go('#/');
}

export function renderBuilding(ctx) {
  const { app } = ctx;
  let line = 0, polls = 0;
  const started = Date.now();
  app.innerHTML = `<main class="main start" style="padding-top:64px">
    <section class="build in" aria-live="polite">
      <div class="rings" aria-hidden="true"><i></i><i></i><i></i><i class="pulse"></i><i class="pulse b"></i><b></b><b class="s2"></b><b class="s3"></b></div>
      <div class="ph" style="align-items:center"><h1>Mapping your perimeter</h1><p id="bLine">${BUILD_LINES[0]}…</p></div>
      <div class="card build-list" id="bList"><div class="row"><div class="sk sk-line grow"></div></div><div class="row"><div class="sk sk-line grow"></div></div></div>
      <span class="meta" id="bTime">Usually under a minute. You can leave this page.</span>
    </section></main>`;
  const lt = setInterval(() => {
    line = (line + 1) % BUILD_LINES.length;
    const el = $('#bLine'); if (!el) return;
    el.style.opacity = 0;
    setTimeout(() => { el.textContent = BUILD_LINES[line] + '…'; el.style.opacity = 1; }, 250);
  }, 2600);
  $('#bLine').style.transition = 'opacity .25s';
  let pt;
  async function poll() {
    polls++;
    try {
      const p = await api.portfolio();
      if (!ctx.isCurrent()) return;
      ctx.store.portfolio = p;
      const list = $('#bList');
      if (list && p.companies?.length) {
        list.innerHTML = p.companies.map(c => `<div class="row"><span class="grow" style="font-weight:500;text-align:left">${esc(c.name)}</span><span class="meta">${esc(c.hq || '')}</span>${p.building ? '<span class="spin" aria-label="Building"></span>' : '<span class="tick">✓</span>'}</div>`).join('');
      }
      const s = Math.round((Date.now() - started) / 1000);
      if ($('#bTime') && s > 8) $('#bTime').textContent = `${s} s · usually under a minute`;
      if (!p.building) {
        clearInterval(lt);
        toast(`Perimeter ready · ${plural(p.companies?.length || 0, 'company', 'companies')}`);
        setTimeout(() => ctx.isCurrent() && ctx.go('#/'), 500);
        return;
      }
    } catch {}
    pt = setTimeout(poll, polls < 5 ? 1500 : 2500);
  }
  poll();
  ctx.onCleanup(() => { clearInterval(lt); clearTimeout(pt); });
}

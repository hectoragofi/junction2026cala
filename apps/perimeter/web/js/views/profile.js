// Profile and settings (#/profile): seat, my company / portfolio, rebuild, demo switch, reset.
import { api, setView, who } from '../api.js';
import { loadMe, hasProfile, myProfile, profileLabel, switchView, renderChrome } from '../app.js';
import { $, $$, esc, initials, plural, toast, openModal, fmtDate } from '../ui.js';
import { resolveRows, mountConfirm, skRows } from './start.js';

export function render(ctx) {
  if (!hasProfile()) return renderDemoOnly(ctx);
  draw(ctx);
}

function renderDemoOnly(ctx) {
  const me = ctx.store.me || {};
  const cos = me.context?.portfolio || [];
  ctx.app.innerHTML = `<main class="main prof">
    <div class="ph in"><h1>Profile</h1><p>You’re exploring the shared demo. Make Perimeter yours in under a minute.</p></div>
    <section class="card prof-cta in">
      <div class="grow"><b>Make it yours</b><span>Tell us your seat and your companies. Your profile lives in this browser, no sign-up.</span></div>
      <a class="btn acc lg" href="#/welcome">Get started</a>
    </section>
    <section class="sec in" style="animation-delay:.05s"><h2 class="h">Demo portfolio${me.demo_locked ? ' · read-only' : ''}</h2>
      <div class="card">${cos.map(c => `<div class="row"><span class="pav">${esc(initials(c.name))}</span><span class="grow" style="font-weight:500">${esc(c.name)}</span></div>`).join('') || '<div class="row"><span class="meta">Not built yet.</span></div>'}</div>
      ${me.demo_locked ? '<span class="note">The shared demo is locked so every visitor sees the same portfolio.</span>' : ''}
    </section>
  </main>`;
}

function draw(ctx) {
  const p = myProfile();
  const founder = p.role === 'founder';
  const demoView = who.view === 'demo';
  let staged = (p.portfolio || []).map(c => ({ id: c.id, name: c.name, description: c.description, hq: c.hq }));
  const savedIds = () => (p.portfolio_ids || []).join();
  const dirty = () => staged.map(c => c.id).join() !== savedIds();
  const built = ctx.store.portfolio?.built_at && !demoView ? ctx.store.portfolio.built_at : null;

  ctx.app.innerHTML = `<main class="main prof">
    <div class="prof-head in">
      <span class="pav lg${founder ? ' f' : ''}">${esc(initials(profileLabel()))}</span>
      <div class="ph"><h1>${esc(profileLabel())}</h1><p>${founder ? `Founder${p.my_company ? ' · ' + esc(p.my_company.name) : ''}` : `Investor${p.fund_or_company_name ? ' · ' + esc(p.fund_or_company_name) : ''} · ${plural(p.portfolio_ids?.length || 0, 'company', 'companies')}`}</p></div>
    </div>
    ${demoView ? `<div class="card buildbar in"><span class="demo-badge">Demo</span><span class="grow">You’re viewing the shared demo. Your own perimeter is one click away.</span><button type="button" class="btn dark" data-act="me">Back to my profile</button></div>` : ''}

    <section class="sec in" style="animation-delay:.03s"><h2 class="h">You</h2>
      <div class="card">
        <div class="row prow"><label for="pName" class="pl">Name</label><input id="pName" class="pin" value="${esc(p.name || '')}" placeholder="Add your name" maxlength="60"></div>
        <div class="row prow"><span class="pl" id="seatLbl">Seat</span><div class="seg" role="radiogroup" aria-labelledby="seatLbl">
          <button type="button" role="radio" data-role="founder" class="${founder ? 'on' : ''}" aria-checked="${founder}">I’m raising</button>
          <button type="button" role="radio" data-role="investor" class="${founder ? '' : 'on'}" aria-checked="${!founder}">I’m investing</button></div></div>
        ${founder ? '' : `<div class="row prow"><label for="pFund" class="pl">Fund</label><input id="pFund" class="pin" value="${esc(p.fund_or_company_name || '')}" placeholder="Add your fund" maxlength="60"></div>`}
      </div>
    </section>

    ${founder ? `<section class="sec in" style="animation-delay:.06s"><h2 class="h">My company</h2>
      <div class="card" id="myCo">${p.my_company ? `<div class="row"><span class="pav">${esc(initials(p.my_company.name))}</span><span class="grow" style="min-width:0;display:flex;flex-direction:column"><span style="font-weight:500">${esc(p.my_company.name)}</span><span class="meta ell">${esc([p.my_company.description, p.my_company.hq].filter(Boolean).join(' · '))}</span></span><button type="button" class="btn" id="chgCo">Change</button></div>` : `<div class="row"><span class="grow meta">No company yet.</span><button type="button" class="btn dark" id="chgCo">Add your company</button></div>`}</div>
      <div id="coSearch"></div>
      ${(p.watch_rivals || []).length ? `<span class="note">Watching ${plural(p.watch_rivals.length, 'rival')}: ${esc(p.watch_rivals.slice(0, 6).map(r => r.name).join(', '))}${p.watch_rivals.length > 6 ? '…' : ''}</span>` : ''}
    </section>` : `<section class="sec in" style="animation-delay:.06s"><div class="prof-sh"><h2 class="h" id="pfH">Portfolio</h2></div>
      <div class="card" id="pfList"></div>
      <form class="bigin sm" id="addForm" autocomplete="off"><label for="addIn" class="sr">Add companies</label><input id="addIn" placeholder="Add a company: name or website" spellcheck="false"><button type="submit" class="btn dark" id="addGo">Find</button></form>
      <div id="addConfirm"></div>
      <div id="saveBar"></div>
    </section>`}

    <section class="sec in" style="animation-delay:.09s"><h2 class="h">Perimeter</h2>
      <div class="card">
        ${demoView ? '' : `<div class="row prow"><span class="grow" style="display:flex;flex-direction:column"><span style="font-weight:500">Rebuild perimeter</span><span class="meta">${built ? `Last built ${esc(fmtDate(built.slice(0, 10)))}. ` : ''}Reads Cala again for fresh rivals, people and news.</span></span><button type="button" class="btn" data-act="rebuild">Rebuild</button></div>`}
        <div class="row prow"><span class="grow" style="display:flex;flex-direction:column"><span style="font-weight:500">${demoView ? 'Back to my profile' : 'Explore the demo'}</span><span class="meta">${demoView ? 'Return to ' + esc(profileLabel()) + '.' : 'Four European fintechs, mapped from Cala. Your profile stays as it is.'}</span></span><button type="button" class="btn" data-act="${demoView ? 'me' : 'demo'}">${demoView ? 'Back' : 'Switch to demo'}</button></div>
      </div>
    </section>

    <section class="sec in" style="animation-delay:.12s"><h2 class="h">Danger zone</h2>
      <div class="card"><div class="row prow"><span class="grow" style="display:flex;flex-direction:column"><span style="font-weight:500">Reset profile</span><span class="meta">Forget your seat and companies in this browser and start over.</span></span><button type="button" class="btn danger" data-act="reset">Reset</button></div></div>
    </section>
  </main>`;

  // ---- text fields save on blur / Enter
  const field = (id, key) => {
    const el = $(id); if (!el) return;
    const save = async () => {
      const v = el.value.trim();
      if (v === (p[key] || '')) return;
      try { await api.saveProfile({ [key]: v }); await loadMe(); renderChrome('profile'); toast('Saved'); }
      catch (e) { toast('Couldn’t save: ' + e.message); }
    };
    el.onblur = save;
    el.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); el.blur(); } if (e.key === 'Escape') { el.value = p[key] || ''; el.blur(); } };
  };
  field('#pName', 'name'); field('#pFund', 'fund_or_company_name');

  // ---- seat switch
  $$('[data-role]').forEach(b => b.onclick = async () => {
    const role = b.dataset.role;
    if (role === p.role) return;
    if (role === 'founder' && (p.portfolio_ids?.length || 0) > 1) {
      const ok = await confirmModal('Switch to founder?', `A founder watches one company. We’ll keep <b>${esc(p.portfolio?.[0]?.name || 'your first company')}</b> as yours; you can change it after.`, 'Switch seat');
      if (!ok) return;
    }
    try {
      await api.saveProfile({ role });
      ctx.store.portfolio = null; await loadMe();
      toast(role === 'founder' ? 'You’re in the founder seat' : 'You’re in the investor seat');
      ctx.go('#/profile');
    } catch (e) { toast('Couldn’t switch: ' + e.message); }
  });

  // ---- founder: change company
  $('#chgCo') && ($('#chgCo').onclick = () => {
    const box = $('#coSearch');
    box.innerHTML = `<form class="bigin sm in" id="coForm" autocomplete="off"><label for="coIn" class="sr">Your company</label><input id="coIn" placeholder="Your company or its website" spellcheck="false"><button type="submit" class="btn dark">Find</button><button type="button" class="x" id="coX" aria-label="Cancel">×</button></form><div id="coConfirm"></div>`;
    $('#coIn').focus();
    $('#coX').onclick = () => { box.innerHTML = ''; $('#chgCo')?.focus(); };
    $('#coIn').onkeydown = e => { if (e.key === 'Escape') { e.stopPropagation(); $('#coX').click(); } };
    $('#coForm').onsubmit = async e => {
      e.preventDefault();
      const v = $('#coIn').value.trim().split(/[\n,;]+/)[0].trim(); if (!v) return;
      const cb = $('#coConfirm'); cb.innerHTML = skRows(1);
      try {
        const rows = (await resolveRows(v)).slice(0, 1);
        if (!rows[0]?.candidates.length) { cb.innerHTML = `<div class="card state"><b>No match for “${esc(v)}”</b><span>Try the legal name or the website.</span></div>`; return; }
        mountConfirm(cb, rows, { title: () => 'Is this your company?', cta: () => 'Use this company', onGo: async ids => {
          await api.saveProfile({ my_company_id: ids[0] });
          setView('me'); ctx.store.portfolio = null; await loadMe();
          toast('Company updated. Mapping its market.'); ctx.go('#/');
        } });
      } catch (err) { cb.innerHTML = `<div class="card scard"><span class="cap">Source error</span><span>${esc(err.message)}</span></div>`; }
    };
  });

  // ---- investor: portfolio list with staged add / remove
  function drawList() {
    const list = $('#pfList'); if (!list) return;
    $('#pfH').textContent = `Portfolio · ${staged.length}`;
    list.innerHTML = staged.length ? staged.map((c, i) => `<div class="row"><span class="pav">${esc(initials(c.name))}</span><span class="grow" style="min-width:0;display:flex;flex-direction:column"><span style="font-weight:500">${esc(c.name)}</span>${c.description || c.hq ? `<span class="meta ell">${esc([c.description, c.hq].filter(Boolean).join(' · '))}</span>` : ''}</span>${p.portfolio_ids?.includes(c.id) ? '' : '<span class="pill soft">New</span>'}<button type="button" class="x" data-rm="${i}" aria-label="Remove ${esc(c.name)}">×</button></div>`).join('')
      : '<div class="row"><span class="meta">No companies. Add the ones you back below.</span></div>';
    $$('[data-rm]', list).forEach(b => b.onclick = () => { const c = staged.splice(+b.dataset.rm, 1)[0]; drawList(); toast(`Removed ${c.name}`, { label: 'Undo', run: () => { staged.splice(+b.dataset.rm, 0, c); drawList(); } }); });
    const bar = $('#saveBar');
    bar.innerHTML = dirty() ? `<div class="card savebar in"><span class="grow">${staged.length ? 'Unsaved changes. Saving rebuilds your perimeter.' : 'Remove every company? Your feed will be empty.'}</span><button type="button" class="btn ghost" id="pfUndo">Discard</button><button type="button" class="btn acc" id="pfSave">Save and rebuild</button></div>` : '';
    if (!dirty()) return;
    $('#pfUndo').onclick = () => { staged = (p.portfolio || []).map(c => ({ ...c })); drawList(); };
    $('#pfSave').onclick = async () => {
      const b = $('#pfSave'); b.disabled = true; b.innerHTML = '<span class="spin" aria-hidden="true"></span>Saving';
      try {
        await api.saveProfile({ portfolio_ids: staged.map(c => c.id) });
        setView('me'); ctx.store.portfolio = null; await loadMe();
        toast(staged.length ? `Watching ${plural(staged.length, 'company', 'companies')}. Rebuilding.` : 'Portfolio cleared');
        ctx.go(staged.length ? '#/' : '#/profile');
      } catch (e) { toast('Couldn’t save: ' + e.message); b.disabled = false; b.textContent = 'Save and rebuild'; }
    };
  }
  drawList();
  $('#addForm') && ($('#addForm').onsubmit = async e => {
    e.preventDefault();
    const v = $('#addIn').value.trim(); if (!v) return;
    const box = $('#addConfirm');
    box.innerHTML = skRows(v.split(/[\n,;]+/).filter(Boolean).length);
    $('#addGo').disabled = true;
    try {
      const rows = await resolveRows(v);
      mountConfirm(box, rows, {
        cta: n => `Add ${plural(n, 'company', 'companies')}`,
        onGo: async (ids, cos) => {
          const have = new Set(staged.map(c => c.id));
          const fresh = cos.filter(c => !have.has(c.id));
          staged.push(...fresh.map(c => ({ id: c.id, name: c.name, description: c.description, hq: c.hq })));
          box.innerHTML = ''; $('#addIn').value = '';
          drawList();
          toast(fresh.length ? `Added ${fresh.map(c => c.name).join(', ')}. Save to rebuild.` : 'Already in your portfolio');
          $('#pfSave')?.focus();
        },
      });
    } catch (err) { box.innerHTML = `<div class="card scard"><span class="cap">Source error</span><span>${esc(err.message)}</span></div>`; }
    finally { $('#addGo') && ($('#addGo').disabled = false); }
  });

  // ---- actions
  $$('[data-act]').forEach(b => b.onclick = async () => {
    const a = b.dataset.act;
    if (a === 'demo') return switchView('demo');
    if (a === 'me') return switchView('me', { to: '#/profile' });
    if (a === 'rebuild') {
      b.disabled = true;
      try { await api.rebuild(); toast('Rebuilding. Your feed stays up while Cala is read again.'); ctx.store.portfolio = null; }
      catch (e) { toast('Couldn’t rebuild: ' + e.message); }
      b.disabled = false; return;
    }
    if (a === 'reset') {
      const ok = await confirmModal('Reset your profile?', 'This forgets your seat, companies and perimeter in this browser. The shared demo is not affected.', 'Reset profile', true);
      if (!ok) return;
      try { await api.resetProfile(); } catch (e) { toast('Couldn’t reset: ' + e.message); return; }
      setView('me'); ctx.store.portfolio = null; await loadMe();
      toast('Profile reset'); ctx.go('#/welcome');
    }
  });
}

function confirmModal(title, html, cta, danger = false) {
  return new Promise(resolve => {
    let done = false;
    const finish = v => { if (done) return; done = true; resolve(v); };
    const m = openModal(`<div class="modal-h"><h2 class="grow" style="font-size:17px;font-weight:600">${esc(title)}</h2><button type="button" class="x" aria-label="Close" data-close>×</button></div>
      <div class="modal-b"><p class="muted" style="font-size:14px">${html}</p></div>
      <div class="modal-f"><button type="button" class="btn" data-close>Cancel</button><button type="button" class="btn ${danger ? 'danger solid' : 'dark'}" data-ok>${esc(cta)}</button></div>`, { label: title, onClose: () => finish(false) });
    const ok = m.box.querySelector('[data-ok]');
    ok.onclick = () => { finish(true); m.close(); };
    ok.focus();
  });
}

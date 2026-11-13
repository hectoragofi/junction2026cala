import { api } from '../api.js';
import { renderChrome, seat, myCompany, viewingDemo } from '../app.js';
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

/** Match pasted names/URLs in Cala. Each row: {query, best, candidates (best first), pick}. */
export async function resolveRows(text) {
  const r = await api.resolve(text);
  // the API returns best separately from the other candidates: best is always option 1
  return (r.matches || []).map(m => ({ ...m, pick: m.best ? 0 : -1, candidates: m.best ? [m.best, ...(m.candidates || []).filter(c => c.id !== m.best.id)] : (m.candidates || []) }));
}
export const chosen = r => r.pick >= 0 ? r.candidates[r.pick] : null;
export const skRows = n => `<div class="sec"><div class="sk sk-line" style="width:180px;height:16px"></div><div class="card">${Array.from({ length: Math.max(1, n) }, () => `<div class="row"><div class="sk sk-line grow" style="max-width:220px"></div><div class="sk sk-line" style="width:90px"></div></div>`).join('')}</div></div>`;

/** The "We found N companies" confirm list. opts: {title?, cta(n), onGo(ids, companies), hideCta?} */
export function mountConfirm(box, rows, opts) {
  function draw() {
    if (!rows.length) { box.innerHTML = ''; opts.onEmpty?.(); return; }
    const found = rows.filter(chosen);
    box.innerHTML = `<section class="sec in" aria-label="Confirm companies">
      <div style="display:flex;align-items:baseline;justify-content:space-between;gap:4px 12px;flex-wrap:wrap">
        <h2 style="font-size:15px;font-weight:600">${opts.title ? esc(opts.title(found.length)) : `We found ${plural(found.length, 'company', 'companies')}`}</h2>
        <span class="meta">${rows.length > 1 ? 'Remove any that are wrong' : 'Not it? Pick another match'}</span>
      </div>
      <div class="card stagger">${rows.map((r, i) => {
        const c = chosen(r);
        if (!c) return `<div class="row"><span class="grow" style="font-weight:500;color:var(--faint)">${esc(r.query)}</span><span class="pill nf">Not found</span><button type="button" class="x" data-rm="${i}" aria-label="Remove ${esc(r.query)}">×</button></div>`;
        const multi = r.candidates.length > 1;
        return `<div class="row"><span class="grow" style="min-width:0;display:flex;flex-direction:column">
            <span style="font-weight:500">${esc(c.name)}</span>
            <span class="meta" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc([c.description, c.hq, c.founded && 'founded ' + c.founded].filter(Boolean).join(' · '))}</span></span>
          ${c.website ? `<span class="meta mhide" style="white-space:nowrap">${esc(c.website.replace(/^https?:\/\//, ''))}</span>` : ''}
          ${multi ? `<button type="button" class="cand" data-cand="${i}" aria-haspopup="menu">${r.pick + 1} of ${r.candidates.length} ▾</button>` : ''}
          <button type="button" class="x" data-rm="${i}" aria-label="Remove ${esc(c.name)}">×</button></div>`;
      }).join('')}</div>
      ${opts.hideCta ? '' : `<button type="button" class="btn acc lg" data-go style="align-self:flex-end" ${found.length ? '' : 'disabled'}>${esc(opts.cta(found.length))}</button>`}
    </section>`;
    $$('[data-rm]', box).forEach(b => b.onclick = () => { rows.splice(+b.dataset.rm, 1); draw(); opts.onChange?.(); });
    $$('[data-cand]', box).forEach(b => b.onclick = () => {
      const r = rows[+b.dataset.cand];
      openMenu(b, r.candidates.map((c, j) => ({ label: c.name, hint: [c.hq, c.founded].filter(Boolean).join(' · '), on: j === r.pick, j })), it => { r.pick = it.j; draw(); opts.onChange?.(); });
    });
    const go = box.querySelector('[data-go]');
    if (go) go.onclick = async () => {
      const cos = rows.map(chosen).filter(Boolean);
      go.disabled = true; const t = go.textContent; go.innerHTML = '<span class="spin" aria-hidden="true"></span>' + esc(t);
      try { await opts.onGo(cos.map(c => c.id), cos); }
      catch (err) { toast(err.message); go.disabled = false; go.textContent = t; }
    };
  }
  draw();
  return { redraw: draw, ids: () => rows.map(chosen).filter(Boolean).map(c => c.id) };
}

export function renderBuilding(ctx) {
  const { app } = ctx;
  let line = 0, polls = 0;
  const started = Date.now();
  const founder = seat() === 'founder';
  const co = myCompany()?.name;
  app.innerHTML = `<main class="main start" style="padding-top:64px">
    <section class="build in" aria-live="polite">
      <div class="rings" aria-hidden="true"><i></i><i></i><i></i><i class="pulse"></i><i class="pulse b"></i><b></b><b class="s2"></b><b class="s3"></b></div>
      <div class="ph" style="align-items:center"><h1>${founder && co ? `Mapping the market around ${esc(co)}` : viewingDemo() ? 'Mapping the demo portfolio' : 'Mapping your perimeter'}</h1><p id="bLine">${BUILD_LINES[0]}…</p></div>
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
      const hadNav = ctx.store.portfolio?.companies?.length;
      ctx.store.portfolio = p;
      if (!hadNav && p.companies?.length) renderChrome('feed');
      const list = $('#bList');
      if (list && p.companies?.length) {
        list.innerHTML = p.companies.map(c => `<div class="row"><span class="grow" style="font-weight:500;text-align:left">${esc(c.name)}</span><span class="meta">${esc(c.hq || '')}</span>${p.building ? '<span class="spin" aria-label="Building"></span>' : '<span class="tick">✓</span>'}</div>`).join('');
      }
      const s = Math.round((Date.now() - started) / 1000);
      if ($('#bTime') && s > 8 && !p.queued) $('#bTime').textContent = s < 60 ? `${s} s · usually under a minute` : `${Math.floor(s / 60)} min ${s % 60} s · a first build reads a lot of the graph. You can leave this page.`;
      // first companies are mapped: show the feed with what exists, it keeps filling in
      if (p.building && (p.status || []).some(x => x.status !== 'mapping')) { clearInterval(lt); ctx.go('#/'); return; }
      if (p.queued && $('#bTime')) $('#bTime').textContent = p.queued > 1 ? `In line: ${p.queued - 1} other ${p.queued - 1 === 1 ? 'map' : 'maps'} ahead of yours. Starts in a moment.` : 'Next in line. Starts in a moment.';
      if (p.progress && $('#bLine')) { clearInterval(lt); $('#bLine').textContent = /^[a-z ]+$/.test(p.progress) ? `Mapping ${p.progress}…` : p.progress; }
      if (!p.building && p.error) {
        clearInterval(lt);
        $('#bLine').textContent = 'Something went wrong while mapping.';
        $('#bTime').innerHTML = `<span style="display:flex;flex-direction:column;gap:10px;align-items:center">${esc(p.error)}<button type="button" class="btn" id="bRetry">Retry</button></span>`;
        $('#bRetry').onclick = async () => { try { await api.rebuild(); renderBuilding(ctx); } catch (e) { toast(e.message); } };
        return;
      }
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

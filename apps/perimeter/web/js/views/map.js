import { api } from '../api.js';
import { $, $$, esc, srcChips, entPill, entLink, fmtNum, plural, nm } from '../ui.js';
import { mountGraph } from './graph.js';

const VIEW_KEY = 'perimeter-map-view';
const HOT_KINDS = /board|shared|overlap|rival in/i;

export async function render(ctx) {
  const { app } = ctx;
  let view = 'graph';
  try { view = localStorage.getItem(VIEW_KEY) || 'graph'; } catch {}
  app.innerHTML = `<main class="main wide">
    <div class="maphead in"><div class="ph"><h1>Your perimeter</h1><p id="mapSub"><span class="sk sk-line" style="display:inline-block;width:420px;max-width:80vw"></span></p></div>
      <div class="seg" role="tablist" aria-label="Map view"><button type="button" role="tab" data-v="graph">Graph</button><button type="button" role="tab" data-v="lanes">Lanes</button></div></div>
    <div class="card stats" id="stats">${Array.from({ length: 6 }, () => `<div class="stat"><div class="sk" style="height:28px;width:56px"></div><div class="sk sk-line" style="width:80px;margin-top:6px"></div></div>`).join('')}</div>
    <section class="sec" id="viewBox"><div class="card sk" style="height:560px"></div></section>
    <section class="sec" id="sigBox"></section>
  </main>`;
  let data;
  try { data = await api.perimeter(); }
  catch (err) {
    if (!ctx.isCurrent()) return;
    $('#viewBox').innerHTML = `<div class="card scard"><span class="cap">Source error</span><span>The perimeter couldn’t load. ${esc(err.message)}</span><button type="button" class="btn" style="align-self:flex-start" id="retry">Retry</button></div>`;
    $('#retry').onclick = () => render(ctx); return;
  }
  if (!ctx.isCurrent()) return;
  const cos = data.companies || [];
  const st = data.stats || {};
  if (!cos.length) {
    $('#mapSub').textContent = 'Nothing mapped yet.';
    $('#stats').remove();
    $('#viewBox').innerHTML = `<div class="card state"><b>No perimeter yet</b><span>${ctx.store.portfolio?.building ? 'Still mapping your companies. Check back in a minute.' : 'Add companies to your portfolio to map who is around them.'}</span><a class="btn" href="#/">Go to start</a></div>`;
    return;
  }
  $('#mapSub').textContent = `Everything around your ${plural(cos.length, 'company', 'companies')}, mapped from Cala. Blue means it touches more than one of them.`;
  const statList = [[st.rivals, 'Rivals'], [st.investors, 'Investors'], [st.people, 'Founders, execs, board'], [st.countries, 'Countries'], [st.entities, 'Entities screened'], [st.facts, 'Cala facts, each sourced']];
  $('#stats').innerHTML = statList.map(([n, l]) => `<div class="stat"><b data-count="${n ?? 0}">0</b><span>${l}</span></div>`).join('');
  countUp($$('[data-count]'));

  let graph = null;
  function setView(v) {
    view = v; try { localStorage.setItem(VIEW_KEY, v); } catch {}
    $$('[data-v]').forEach(b => { const on = b.dataset.v === v; b.classList.toggle('on', on); b.setAttribute('aria-selected', on); });
    graph?.destroy(); graph = null;
    const box = $('#viewBox');
    if (v === 'graph') {
      box.innerHTML = `<h2 class="h">Knowledge graph · ${fmtNum(countNodes(cos))} entities, ${fmtNum(countEdges(cos))} links</h2><div class="card graph-wrap in" id="gw"></div>`;
      graph = mountGraph($('#gw'), cos);
    } else {
      box.innerHTML = `<h2 class="h">Who is around each company</h2><div class="card in">${lanesHTML(cos)}</div>`;
    }
  }
  $$('[data-v]').forEach(b => b.onclick = () => setView(b.dataset.v));
  setView(view);

  const sigs = data.signals || [];
  if (sigs.length) {
    const hot = sigs.filter(s => HOT_KINDS.test(s.kind)), rest = sigs.filter(s => !HOT_KINDS.test(s.kind));
    const sigHTML = s => `<div class="sig"><span class="pill ${HOT_KINDS.test(s.kind) ? 'hot' : 'n'}">${esc(s.kind)}</span><div class="b"><span>${linkify(s.text, s.entities)}</span>${(s.sources || []).length ? `<div class="chips">${srcChips(s.sources, 2)}</div>` : ''}</div></div>`;
    $('#sigBox').innerHTML = `<div class="sigs">
      <section class="sec"><h2 class="h">Signals only a knowledge graph can see</h2><div class="card stagger">${(hot.length ? hot : sigs.slice(0, Math.ceil(sigs.length / 2))).map(sigHTML).join('')}</div></section>
      ${(hot.length ? rest : sigs.slice(Math.ceil(sigs.length / 2))).length ? `<section class="sec"><h2 class="h">Around your companies</h2><div class="card stagger">${(hot.length ? rest : sigs.slice(Math.ceil(sigs.length / 2))).map(sigHTML).join('')}</div></section>` : ''}
    </div>`;
  }
  ctx.onCleanup(() => graph?.destroy());
}

// Turn entity names inside signal text into clickable entity links.
function linkify(text, ents = []) {
  let html = esc(text);
  const sorted = [...ents].filter(e => e?.name && e.id).sort((a, b) => b.name.length - a.name.length);
  const used = new Set();
  for (const e of sorted) {
    const n = esc(e.name);
    const i = html.indexOf(n);
    if (i < 0 || used.has(e.name)) continue;
    // skip if inside an existing tag
    const before = html.slice(0, i);
    if ((before.match(/<button/g) || []).length !== (before.match(/<\/button>/g) || []).length) continue;
    used.add(e.name);
    html = before + entLink(e) + html.slice(i + n.length);
  }
  return html;
}

function lanesHTML(cos) {
  const MAX = 4;
  const pf = new Map(cos.map(c => [c.id, c.name]));
  const chipList = (arr, type, fmt) => {
    if (!arr?.length) return '<span class="meta">None in Cala</span>';
    const sorted = [...arr].sort((a, b) => (b.shared_with?.length ? 1 : 0) - (a.shared_with?.length ? 1 : 0));
    const shown = sorted.slice(0, MAX), more = sorted.length - shown.length;
    return shown.map(e => {
      if (pf.has(e.id)) return entPill({ ...e, type: 'Company' }, e.name + ' · yours', 'hot', `data-tip="${esc(`<b>${esc(e.name)}</b><br><span>Rival, and also in your portfolio</span>`)}"`);
      const hot = e.shared_with?.length;
      const label = fmt ? fmt({ ...e, name: nm(e.name) }) : nm(e.name);
      const tip = hot ? `<b>${esc(e.name)}</b><br><span>Also touches ${esc(e.shared_with.join(', '))}</span>` : `<b>${esc(e.name)}</b>${e.role || e.sub ? `<br><span>${esc(e.role || e.sub)}</span>` : ''}`;
      return entPill({ ...e, type: e.type || type }, label + (hot ? ` · also ${e.shared_with.slice(0, 2).join(', ')}${e.shared_with.length > 2 ? '…' : ''}` : ''), hot ? 'hot' : 'n', `data-tip="${esc(tip)}"`);
    }).join('') + (more > 0 ? `<button type="button" class="pill n" data-more data-tip="${esc(sorted.slice(MAX).map(x => esc(x.name)).join(', '))}">+${more}</button>` : '');
  };
  return `<div class="lane head"><span>Your company</span><span>Rivals</span><span>Investors</span><span>People</span></div>` + cos.map(c => `<div class="lane">
    <div class="co"><span style="font-weight:600">${entLink({ id: c.id, name: c.name, type: 'Company' })}</span><span style="font-size:12px;color:var(--muted)">${esc([c.industry, c.hq].filter(Boolean).join(' · '))}</span></div>
    <div><span class="lbl">Rivals</span><div class="chips">${chipList(c.rivals, 'Company')}</div></div>
    <div><span class="lbl">Investors</span><div class="chips">${chipList(c.investors, 'Investor')}</div></div>
    <div><span class="lbl">People</span><div class="chips">${chipList(c.people, 'Person', p => p.role ? `${p.name} · ${shortRole(p.role)}` : p.name)}</div></div>
  </div>`).join('');
}
const shortRole = r => { const x = String(r).replace(/co-?founder/i, 'founder').replace(/board member/i, 'board').split(',')[0].trim(); return /^[A-Z]{2,4}$/.test(x) ? x : x.toLowerCase(); };

function countNodes(cos) {
  const s = new Set(); cos.forEach(c => { s.add(c.id); ['rivals', 'investors', 'people'].forEach(k => (c[k] || []).forEach(e => s.add(e.id || e.name))); }); return s.size;
}
function countEdges(cos) { return cos.reduce((n, c) => n + (c.rivals?.length || 0) + (c.investors?.length || 0) + (c.people?.length || 0), 0); }

function countUp(els) {
  const t0 = performance.now(), dur = 900;
  const step = t => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    els.forEach(el => { el.textContent = fmtNum(Math.round(+el.dataset.count * e)); });
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

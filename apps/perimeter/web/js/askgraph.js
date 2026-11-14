// The graph behind an Ask conversation: every entity and link the tools read from Cala, kept across
// follow-up questions. It marks what the written answer left out but that connects two or more things,
// and lets the reader grow it by hand. Hand-written force layout on SVG, no dependencies.
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const initials = n => String(n || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase();
  const KIND = { company: 'Company', investor: 'Investor', rival: 'Rival', person: 'Person' };
  const RANK = { company: 0, investor: 1, rival: 2, person: 3 };
  const R = { company: 6.5, investor: 8, rival: 8, person: 5 };
  const list = names => names.length < 2 ? names.join('') : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];

  function create({ load }) {
    const nodes = new Map(), edges = new Map(), byName = new Map(), alias = new Map();
    let said = '';                       // lowercased text of every widget shown so far
    let N = [], E = [];                  // arrays the simulation runs on
    let wrap = null, svg = null, gE, gN, gL, side, tip, finds, count;
    let alpha = 0, raf = 0, vb = { x: -400, y: -240, w: 800, h: 480 }, userCam = false;
    let hovered = null, sel = null, allLabels = false, drag = null, note = '';

    /* ---------- data ---------- */
    function merge(snap, { expand = false } = {}) {
      let added = 0, linked = 0;
      for (const n of snap.nodes || []) {
        const key = (n.kind === 'person' ? 'p:' : 'o:') + String(n.name).toLowerCase();
        const id = nodes.has(n.id) ? n.id : byName.get(key) || n.id;
        alias.set(n.id, id);
        let m = nodes.get(id);
        if (!m) { m = { id, name: n.name, kind: n.kind }; nodes.set(id, m); byName.set(key, id); added++; }
        else if (m.kind !== 'person' && n.kind !== 'person' && RANK[n.kind] > RANK[m.kind]) m.kind = n.kind;
        if (n.sub && !m.sub) m.sub = n.sub;
        if (n.focus && !expand) m.focus = true;
      }
      for (const e of snap.edges || []) {
        const s = alias.get(e.s) || e.s, t = alias.get(e.t) || e.t;
        if (s === t || !nodes.has(s) || !nodes.has(t)) continue;
        const k = `${s}|${t}|${e.rel}`;
        if (!edges.has(k)) linked++;
        edges.set(k, { ...edges.get(k), ...e, s, t });
      }
      refresh(added ? .9 : linked ? .3 : 0);
      return { added, linked };
    }
    function say(text) { said += ' ' + String(text || '').toLowerCase(); refresh(0); }
    function reset() { nodes.clear(); edges.clear(); byName.clear(); alias.clear(); said = ''; sel = hovered = null; userCam = false; N = []; E = []; }

    function derive() {
      N = [...nodes.values()]; E = [...edges.values()];
      N.forEach(n => { n.nb = new Set(); n.said = !!n.focus || (n.name.length > 2 && said.includes(n.name.toLowerCase())); });
      E.forEach(e => { e.a = nodes.get(e.s); e.b = nodes.get(e.t); e.a.nb.add(e.b); e.b.nb.add(e.a); });
      // "new": the answer never named it, yet it ties together two or more entities of this search
      N.forEach(n => { n.hubs = [...n.nb].filter(x => x.focus); n.isNew = !n.said && n.nb.size >= 2; n.r = n.focus ? 18 : R[n.kind] + (n.isNew ? 2 : 0); });
      E.forEach(e => { e.hot = e.a.isNew || e.b.isNew; });
      // place newcomers next to what they connect to, hubs first
      N.filter(n => n.x == null).sort((a, b) => (b.focus ? 1 : 0) - (a.focus ? 1 : 0) || b.nb.size - a.nb.size).forEach(n => {
        const near = [...n.nb].filter(x => x.x != null);
        const cx = near.reduce((s, o) => s + o.x, 0) / (near.length || 1), cy = near.reduce((s, o) => s + o.y, 0) / (near.length || 1);
        const a = Math.random() * Math.PI * 2, d = !near.length ? 160 * Math.random() : near.length > 1 ? 24 : 70 + Math.random() * 50;
        n.x = cx + Math.cos(a) * d; n.y = cy + Math.sin(a) * d; n.vx = n.vy = 0;
      });
    }
    const finds_ = () => N.filter(n => n.isNew).sort((a, b) => b.hubs.length - a.hubs.length || b.nb.size - a.nb.size);
    const around = n => [...n.nb].sort((a, b) => (b.focus ? 1 : 0) - (a.focus ? 1 : 0) || (b.said ? 1 : 0) - (a.said ? 1 : 0) || b.nb.size - a.nb.size);

    /* ---------- layout ---------- */
    function tick() {
      const k = alpha;
      for (let i = 0; i < N.length; i++) {
        const a = N[i];
        for (let j = i + 1; j < N.length; j++) {
          const b = N[j];
          let dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy;
          if (d2 < .01) { dx = Math.random() - .5; dy = Math.random() - .5; d2 = dx * dx + dy * dy; }
          const d = Math.sqrt(d2), f = (a.focus ? 3 : 1) * (b.focus ? 3 : 1) * 2600 / d2;
          const minD = a.r + b.r + 26, coll = d < minD ? (minD - d) / d * .5 : 0;
          const fx = dx / d * f * k + dx * coll, fy = dy / d * f * k + dy * coll;
          a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
        }
      }
      E.forEach(e => {
        const a = e.a, b = e.b, dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
        const L = 84 + 9 * Math.sqrt(Math.max(a.nb.size, b.nb.size)) + (a.nb.size > 1 && b.nb.size > 1 ? 50 : 0);
        const s = (d - L) / d * .05 * k;
        a.vx += dx * s * (a.focus ? .3 : 1); a.vy += dy * s * (a.focus ? .3 : 1);
        b.vx -= dx * s * (b.focus ? .3 : 1); b.vy -= dy * s * (b.focus ? .3 : 1);
      });
      N.forEach(n => {
        n.vx -= n.x * .004 * k; n.vy -= n.y * .006 * k;
        if (n.fx != null) { n.x = n.fx; n.y = n.fy; n.vx = n.vy = 0; return; }
        n.vx *= .6; n.vy *= .6;
        n.x += Math.max(-30, Math.min(30, n.vx)); n.y += Math.max(-30, Math.min(30, n.vy));
      });
      alpha = Math.max(0, alpha * .985 - .0005);
    }

    /* ---------- drawing ---------- */
    function shape(n) {
      const halo = n.isNew ? `<circle class="halo" r="${n.r + 16}" fill="url(#agGlow)"/>` : '';
      if (n.focus) return `${halo}<rect x="${-n.r}" y="${-n.r}" width="${n.r * 2}" height="${n.r * 2}" rx="11" fill="#0A0A0A"/><text text-anchor="middle" dy="4" fill="#fff" font-size="11" font-weight="600">${esc(initials(n.name))}</text>`;
      const ring = n.isNew ? 'stroke="#3D5AFE" stroke-width="2.5"' : null;
      if (n.kind === 'investor') return `${halo}<circle r="${n.r}" fill="#fff" ${ring || 'stroke="#0A0A0A" stroke-width="1.5"'}/>`;
      if (n.kind === 'rival') return `${halo}<circle r="${n.r}" fill="#D93025" ${ring || 'stroke="#fff" stroke-width="2"'}/>`;
      if (n.kind === 'person') return `${halo}<circle r="${n.r}" fill="#8A8A93" ${ring || 'stroke="#fff" stroke-width="1.5"'}/>`;
      return `${halo}<circle r="${n.r}" fill="#C9C9D1" ${ring || 'stroke="#fff" stroke-width="2"'}/>`;
    }
    function build() {
      if (!svg) return;
      gE.textContent = ''; gN.textContent = ''; gL.textContent = '';
      E.forEach(e => {
        e.el = document.createElementNS(NS, 'line');
        e.el.setAttribute('class', `ag-edge ${e.rel}${e.hot ? ' hot' : ''}`);
        gE.appendChild(e.el);
      });
      N.forEach(n => {
        const g = document.createElementNS(NS, 'g');
        g.setAttribute('class', 'ag-node'); g.setAttribute('tabindex', '0'); g.setAttribute('role', 'button');
        g.setAttribute('aria-label', `${n.name}, ${KIND[n.kind]}${n.isNew ? ', not in the answer' : ''}`);
        g.innerHTML = shape(n); g.__n = n; n.el = g; gN.appendChild(g);
        const t = document.createElementNS(NS, 'text');
        t.setAttribute('class', 'ag-label' + (n.focus ? ' hub' : n.isNew ? ' new' : ''));
        t.setAttribute('text-anchor', 'middle'); t.textContent = n.name; n.lab = t; gL.appendChild(t);
      });
      const f = finds_();
      count.textContent = `${N.length} ${N.length === 1 ? 'entity' : 'entities'} · ${E.length} links${f.length ? ` · ${f.length} not in the answer` : ''}`;
      svg.setAttribute('aria-label', `Graph of this search: ${N.length} entities and ${E.length} links read from Cala`);
      finds.innerHTML = f.length ? `<div class="ag-finds-t">Not in the answer, but connected</div>${f.slice(0, 6).map(n => {
        const names = around(n).slice(0, 3).map(x => x.name);
        return `<button type="button" class="ag-find" data-node="${esc(n.id)}"><b>${esc(n.name)}</b><span>${esc(KIND[n.kind])} linked to ${esc(n.nb.size > 3 ? names.join(', ') + ` and ${n.nb.size - 3} more` : list(names))}</span></button>`;
      }).join('')}` : `<div class="ag-finds-t">${N.length ? 'Nothing here goes beyond the answer yet. Click an entity and expand it, or ask a follow-up: the graph keeps growing.' : ''}</div>`;
      paint(); pos();
      if (sel && !side.hidden) panel(sel);
    }
    const labelOn = n => allLabels || n.focus || n.isNew || (n.said && N.length < 90) || N.length < 26;
    function paint() {
      if (!svg) return;
      const n = hovered || sel, on = n ? new Set([n, ...n.nb]) : null;
      svg.classList.toggle('dim', !!n);
      N.forEach(x => { const o = !on || on.has(x); x.el.classList.toggle('fade', !o); x.el.classList.toggle('sel', x === sel); x.lab.classList.toggle('fade', !o); x.lab.style.opacity = on ? (o ? 1 : 0) : labelOn(x) ? 1 : 0; });
      E.forEach(e => { const o = !!n && (e.a === n || e.b === n); e.el.classList.toggle('lit', o); e.el.classList.toggle('fade', !!n && !o); });
    }
    function pos() {
      E.forEach(e => { e.el.setAttribute('x1', e.a.x.toFixed(1)); e.el.setAttribute('y1', e.a.y.toFixed(1)); e.el.setAttribute('x2', e.b.x.toFixed(1)); e.el.setAttribute('y2', e.b.y.toFixed(1)); });
      N.forEach(n => { n.el.setAttribute('transform', `translate(${n.x.toFixed(1)},${n.y.toFixed(1)})`); n.lab.setAttribute('x', n.x.toFixed(1)); n.lab.setAttribute('y', (n.y + n.r + 13).toFixed(1)); });
    }
    function fitBox() {
      if (!N.length) return vb;
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      N.forEach(n => { x0 = Math.min(x0, n.x - n.r - 46); y0 = Math.min(y0, n.y - n.r - 16); x1 = Math.max(x1, n.x + n.r + 46); y1 = Math.max(y1, n.y + n.r + 30); });
      const asp = (svg.clientWidth || 800) / (svg.clientHeight || 480);
      let w = Math.max(x1 - x0, 320), h = Math.max(y1 - y0, 200);
      const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
      if (w / h > asp) h = w / asp; else w = h * asp;
      return { x: cx - w * .52, y: cy - h * .52, w: w * 1.04, h: h * 1.04 };
    }
    const setVB = () => svg && svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
    function loop() {
      raf = 0;
      if (!svg || !svg.isConnected) return;
      if (alpha > .004) { tick(); tick(); raf = requestAnimationFrame(loop); }
      if (!userCam) { const f = fitBox(), k = raf ? .18 : 1; vb = { x: vb.x + (f.x - vb.x) * k, y: vb.y + (f.y - vb.y) * k, w: vb.w + (f.w - vb.w) * k, h: vb.h + (f.h - vb.h) * k }; setVB(); }
      pos();
    }
    const reheat = a => { alpha = Math.max(alpha, a); if (!raf && svg) raf = requestAnimationFrame(loop); };
    function refresh(heat) {
      const fresh = N.length === 0;
      derive();
      if (heat) { alpha = Math.max(alpha, heat); const pre = fresh ? 140 : N.length > 250 ? 10 : 40; for (let i = 0; i < pre; i++) tick(); }
      if (!svg) return;
      build();
      if (fresh && !userCam) { vb = fitBox(); setVB(); }
      reheat(heat || .02);
    }

    /* ---------- detail panel ---------- */
    function phrase(n, e) {
      const from = e.a === n, year = e.date ? e.date.slice(0, 4) : '';
      const what = e.rel === 'invested' ? (from ? 'Invested in' : 'Investor') : e.rel === 'rival' ? 'Rival'
        : e.rel === 'acquired' ? (from ? 'Acquired' : 'Acquired by') : e.rel === 'parent' ? (from ? 'Parent of' : 'Owned by') : (e.label || (from ? 'Works at' : 'Team'));
      return [what, e.rel === 'invested' || e.rel === 'acquired' ? e.label : '', year].filter(Boolean).join(' · ');
    }
    function panel(n) {
      const rows = E.filter(e => e.a === n || e.b === n).map(e => ({ e, o: e.a === n ? e.b : e.a }))
        .sort((x, y) => (y.o.focus ? 1 : 0) - (x.o.focus ? 1 : 0) || (y.e.date || '').localeCompare(x.e.date || '') || y.o.nb.size - x.o.nb.size);
      const hubs = around(n).slice(0, 2).map(x => x.name);
      const q = n.isNew && hubs.length > 1 ? `How is ${n.name} connected to ${hubs[0]} and ${hubs[1]}?` : `Tell me about ${n.name}`;
      side.innerHTML = `<button type="button" class="ag-x" data-g="close" aria-label="Close">×</button>
        <div class="ag-kind">${esc(KIND[n.kind])}${n.sub ? ' · ' + esc(n.sub) : ''}</div><h3>${esc(n.name)}</h3>
        ${n.isNew ? '<span class="ag-badge">Not in the answer</span>' : ''}
        <div class="ag-acts"><button type="button" class="ag-btn dark" data-ask="${esc(q)}">Ask about this</button>${n.kind === 'person' && !load ? '' : `<button type="button" class="ag-btn" data-g="expand" ${n.expanded ? 'disabled' : ''}>${n.expanded ? 'Expanded' : 'Expand from Cala'}</button>`}</div>
        ${note ? `<div class="ag-note">${esc(note)}</div>` : ''}
        <div class="ag-rows-t">${rows.length} ${rows.length === 1 ? 'link' : 'links'} in this search</div>
        <div class="ag-rows">${rows.slice(0, 40).map(({ e, o }) => `<div class="ag-row"><button type="button" data-node="${esc(o.id)}"><b>${esc(o.name)}</b><span>${esc(phrase(n, e))}</span></button>${e.src ? `<a href="${esc(e.src.url)}" target="_blank" rel="noopener" title="${esc(e.src.name)}" aria-label="Source: ${esc(e.src.name)}">↗</a>` : ''}</div>`).join('')}${rows.length > 40 ? `<div class="ag-note">and ${rows.length - 40} more</div>` : ''}</div>`;
      side.hidden = false;
    }
    function select(n, pan) {
      sel = n; note = ''; hovered = null; hideTip();
      if (!n) { side.hidden = true; paint(); return; }
      panel(n); paint();
      if (pan) { userCam = true; vb = { ...vb, x: n.x - vb.w / 2, y: n.y - vb.h / 2 }; setVB(); }
    }
    async function expand(n) {
      const b = side.querySelector('[data-g="expand"]'); if (b) { b.disabled = true; b.textContent = 'Reading Cala…'; }
      try {
        const { added, linked } = merge(await load(n.id), { expand: true });
        n.expanded = true;
        note = added ? `${added} more ${added === 1 ? 'entity' : 'entities'} from Cala.` : linked ? `${linked} more ${linked === 1 ? 'link' : 'links'} to entities already here.` : 'Cala has nothing more around this one.';
      } catch { note = 'Could not read Cala for this one. Try again.'; }
      if (sel === n && svg) panel(n);
    }

    /* ---------- tooltip ---------- */
    function showTip(n, x, y) {
      const r = wrap.getBoundingClientRect(), names = around(n).slice(0, 3).map(o => o.name);
      tip.innerHTML = `<b>${esc(n.name)}</b><span>${esc(KIND[n.kind])}${n.sub ? ' · ' + esc(n.sub) : ''}</span>${names.length ? `<span>Linked to ${esc(list(names))}${n.nb.size > 3 ? ` +${n.nb.size - 3}` : ''}</span>` : ''}${n.isNew ? '<span class="n">Not in the answer</span>' : ''}`;
      tip.hidden = false;
      tip.style.left = Math.min(x - r.left + 14, r.width - tip.offsetWidth - 8) + 'px'; tip.style.top = Math.max(8, y - r.top - tip.offsetHeight - 10) + 'px';
    }
    const hideTip = () => { if (tip) tip.hidden = true; };

    /* ---------- mount ---------- */
    function mount(el) {
      wrap = el; wrap.classList.add('ag');
      wrap.innerHTML = `<div class="ag-top"><div><div class="ttl">Everything this search read from Cala</div><div class="ag-count"></div></div>
          <div class="ag-tools"><button type="button" class="ag-btn" data-g="labels" aria-pressed="false">All labels</button><button type="button" class="ag-btn" data-g="fit">Fit</button><button type="button" class="ag-btn" data-g="full" aria-pressed="false">Full screen</button></div></div>
        <div class="ag-stage"><div class="ag-legend"><span><i class="hub"></i>Asked about</span><span><i class="inv"></i>Investor</span><span><i class="co"></i>Company</span><span><i class="riv"></i>Rival</span><span><i class="per"></i>Person</span><span><i class="new"></i>Not in the answer, links 2+</span></div>
          <aside class="ag-side" hidden></aside><div class="ag-tip" hidden></div></div>
        <div class="ag-finds"></div>`;
      const stage = wrap.querySelector('.ag-stage');
      svg = document.createElementNS(NS, 'svg'); svg.setAttribute('role', 'img');
      svg.innerHTML = '<defs><radialGradient id="agGlow"><stop offset="0" stop-color="#3D5AFE" stop-opacity=".3"/><stop offset="1" stop-color="#3D5AFE" stop-opacity="0"/></radialGradient></defs><g class="ge"></g><g class="gn"></g><g class="gl"></g>';
      stage.prepend(svg);
      gE = svg.querySelector('.ge'); gN = svg.querySelector('.gn'); gL = svg.querySelector('.gl');
      side = wrap.querySelector('.ag-side'); tip = wrap.querySelector('.ag-tip'); finds = wrap.querySelector('.ag-finds'); count = wrap.querySelector('.ag-count');
      sel = hovered = null; userCam = false;

      const toSvg = (cx, cy) => { const p = svg.createSVGPoint(); p.x = cx; p.y = cy; return p.matrixTransform(svg.getScreenCTM().inverse()); };
      const nodeFrom = t => { const g = t.closest && t.closest('.ag-node'); return g ? g.__n : null; };
      svg.addEventListener('pointerdown', ev => {
        const n = nodeFrom(ev.target); svg.setPointerCapture(ev.pointerId);
        drag = n ? { node: n, sx: ev.clientX, sy: ev.clientY } : { sx: ev.clientX, sy: ev.clientY, vb: { ...vb } };
        if (n) { n.fx = n.x; n.fy = n.y; } else svg.classList.add('drag');
      });
      svg.addEventListener('pointermove', ev => {
        if (!drag) { const n = nodeFrom(ev.target); if (n !== hovered) { hovered = n; paint(); } if (n) showTip(n, ev.clientX, ev.clientY); else hideTip(); return; }
        if (Math.abs(ev.clientX - drag.sx) + Math.abs(ev.clientY - drag.sy) > 4) drag.moved = true;
        if (!drag.moved) return;
        hideTip(); userCam = true;
        if (drag.node) { const p = toSvg(ev.clientX, ev.clientY); drag.node.fx = p.x; drag.node.fy = p.y; reheat(.25); }
        else { const sc = vb.w / svg.clientWidth; vb = { ...drag.vb, x: drag.vb.x - (ev.clientX - drag.sx) * sc, y: drag.vb.y - (ev.clientY - drag.sy) * sc }; setVB(); }
      });
      const end = () => {
        if (!drag) return;
        const d = drag; drag = null; svg.classList.remove('drag');
        if (d.node) { d.node.fx = d.node.fy = null; if (d.moved) reheat(.15); else select(d.node); }
        else if (!d.moved) select(null);
      };
      svg.addEventListener('pointerup', end); svg.addEventListener('pointercancel', end);
      svg.addEventListener('pointerleave', () => { if (!drag && hovered) { hovered = null; paint(); hideTip(); } });
      svg.addEventListener('wheel', ev => {
        ev.preventDefault(); userCam = true;
        const p = toSvg(ev.clientX, ev.clientY), nw = Math.min(Math.max(vb.w * Math.exp(ev.deltaY * .0012), 220), 6000), s = nw / vb.w;
        vb = { x: p.x - (p.x - vb.x) * s, y: p.y - (p.y - vb.y) * s, w: nw, h: vb.h * s }; setVB();
      }, { passive: false });
      svg.addEventListener('keydown', ev => { const n = nodeFrom(ev.target); if (n && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); select(n); } });
      wrap.addEventListener('keydown', ev => { if (ev.key === 'Escape') { if (sel) select(null); else if (wrap.classList.contains('ag-full')) full(false); } });
      const full = on => { wrap.classList.toggle('ag-full', on); const b = wrap.querySelector('[data-g="full"]'); b.setAttribute('aria-pressed', on); b.textContent = on ? 'Exit full screen' : 'Full screen'; document.documentElement.classList.toggle('ag-lock', on); userCam = false; requestAnimationFrame(() => { vb = fitBox(); setVB(); }); };
      wrap.addEventListener('click', ev => {
        const node = ev.target.closest('[data-node]'), g = ev.target.closest('[data-g]');
        if (node) { const n = nodes.get(node.dataset.node); if (n) select(n, true); return; }
        if (ev.target.closest('[data-ask]')) { document.documentElement.classList.remove('ag-lock'); return; }  // the page asks it
        if (!g) return;
        const what = g.dataset.g;
        if (what === 'fit') { userCam = false; vb = fitBox(); setVB(); }
        else if (what === 'labels') { allLabels = !allLabels; g.setAttribute('aria-pressed', allLabels); g.classList.toggle('dark', allLabels); paint(); }
        else if (what === 'full') full(!wrap.classList.contains('ag-full'));
        else if (what === 'close') select(null);
        else if (what === 'expand' && sel) expand(sel);
      });
      new ResizeObserver(() => { if (svg && svg.isConnected && !userCam) { vb = fitBox(); setVB(); } }).observe(stage);
      derive(); build(); vb = fitBox(); setVB(); reheat(.3);
    }

    return { merge, say, reset, mount, get size() { return nodes.size; }, get mounted() { return !!(svg && svg.isConnected); } };
  }

  window.AskGraph = { create };
})();

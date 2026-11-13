// Hand-written force-directed perimeter graph (SVG). No dependencies.
import { esc, initials, openEntity, floatTip, hideTip } from '../ui.js';

const NS = 'http://www.w3.org/2000/svg';
const KIND_R = { co: 24, rival: 8, inv: 9, person: 6 };
const KIND_LABEL = { co: 'Your company', rival: 'Rival', inv: 'Investor', person: 'Person' };

function build(cos) {
  const nodes = new Map(); const edges = []; const eset = new Set();
  const pid = new Set(cos.map(c => c.id));
  const key = e => e.id || 'n:' + e.name;
  cos.forEach(c => nodes.set(c.id, { id: c.id, name: c.name, type: 'Company', kind: 'co', sub: [c.industry, c.hq].filter(Boolean).join(' · '), owners: new Set([c.name]), shared: new Set() }));
  const add = (c, e, kind, type) => {
    const k = key(e);
    let n = nodes.get(k);
    if (!n) { n = { id: e.id, name: e.name, type: e.type || type, kind, sub: e.role || e.sub || '', owners: new Set(), shared: new Set() }; nodes.set(k, n); }
    if (n.kind !== 'co') n.owners.add(c.name);
    (e.shared_with || []).forEach(s => n.shared.add(s));
    const ek = [c.id, k].sort().join('|');
    if (k === c.id || eset.has(ek)) return;
    eset.add(ek);
    edges.push({ s: c.id, t: k, kind: pid.has(k) ? 'coco' : kind });
  };
  cos.forEach(c => {
    (c.rivals || []).forEach(e => add(c, e, 'rival', 'Company'));
    (c.investors || []).forEach(e => add(c, e, 'inv', 'Investor'));
    (c.people || []).forEach(e => add(c, e, 'person', 'Person'));
  });
  for (const n of nodes.values()) n.hot = n.kind !== 'co' && (n.shared.size > 0 || n.owners.size > 1);
  for (const n of nodes.values()) if (n.kind === 'co') n.hot = edges.some(e => e.kind === 'coco' && (e.s === n.id || e.t === n.id));
  edges.forEach(e => { e.hot = e.kind === 'coco' || nodes.get(e.t).hot; });
  return { nodes: [...nodes.values()], edges, byKey: nodes };
}

export function mountGraph(wrap, cos) {
  const { nodes, edges, byKey } = build(cos);
  const W = 1000, H = 640;
  // initial positions: portfolio on a ring, satellites around their first owner
  const cosN = nodes.filter(n => n.kind === 'co');
  const R0 = cosN.length > 1 ? 210 : 0;
  cosN.forEach((n, i) => { const a = (i / cosN.length) * Math.PI * 2 - Math.PI / 2; n.x = W / 2 + Math.cos(a) * R0 * 1.25; n.y = H / 2 + Math.sin(a) * R0 * .8; });
  const nb = new Map(nodes.map(n => [n, new Set()]));
  edges.forEach(e => { e.a = byKey.get(e.s); e.b = byKey.get(e.t); nb.get(e.a).add(e.b); nb.get(e.b).add(e.a); });
  nodes.forEach(n => {
    if (n.kind === 'co') return;
    const owners = [...nb.get(n)].filter(x => x.kind === 'co');
    const cx = owners.reduce((s, o) => s + o.x, 0) / (owners.length || 1) || W / 2;
    const cy = owners.reduce((s, o) => s + o.y, 0) / (owners.length || 1) || H / 2;
    const a = Math.random() * Math.PI * 2, d = owners.length > 1 ? 10 : 70 + Math.random() * 60;
    n.x = cx + Math.cos(a) * d; n.y = cy + Math.sin(a) * d;
  });
  nodes.forEach(n => { n.vx = 0; n.vy = 0; n.r = KIND_R[n.kind] + (n.hot && n.kind !== 'co' ? 3 : 0); });

  let alpha = 1;
  function tick() {
    const k = alpha;
    // repulsion
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y; let d2 = dx * dx + dy * dy;
        if (d2 < 0.01) { dx = Math.random() - .5; dy = Math.random() - .5; d2 = dx * dx + dy * dy; }
        const d = Math.sqrt(d2);
        const strength = (a.kind === 'co' && b.kind === 'co' ? 9000 : a.kind === 'co' || b.kind === 'co' ? 2600 : 900) / d2;
        const minD = a.r + b.r + 14;
        const coll = d < minD ? (minD - d) / d * .5 : 0;
        const fx = dx / d * strength * k + dx * coll, fy = dy / d * strength * k + dy * coll;
        a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
      }
    }
    // springs
    edges.forEach(e => {
      const a = e.a, b = e.b;
      const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 1;
      const L = e.kind === 'coco' ? 230 : e.b.hot ? 150 : e.kind === 'person' ? 62 : 92;
      const s = (d - L) / d * (e.kind === 'coco' ? .02 : .06) * k;
      a.vx += dx * s * (a.kind === 'co' ? .25 : 1); a.vy += dy * s * (a.kind === 'co' ? .25 : 1);
      b.vx -= dx * s * (b.kind === 'co' ? .25 : 1); b.vy -= dy * s * (b.kind === 'co' ? .25 : 1);
    });
    // gravity + integrate
    nodes.forEach(n => {
      n.vx += (W / 2 - n.x) * .004 * k; n.vy += (H / 2 - n.y) * .006 * k;
      if (n.fx != null) { n.x = n.fx; n.y = n.fy; n.vx = n.vy = 0; return; }
      n.vx *= .6; n.vy *= .6;
      n.x += Math.max(-30, Math.min(30, n.vx)); n.y += Math.max(-30, Math.min(30, n.vy));
    });
    alpha = Math.max(0, alpha * .985 - .0005);
  }
  for (let i = 0; i < 160; i++) tick();

  // ---------- DOM ----------
  wrap.innerHTML = `<span class="ghint">Drag to move · scroll to zoom · click for details</span>
    <div class="gtools"><button type="button" class="btn" data-g="labels" aria-pressed="false">All labels</button><button type="button" class="btn" data-g="fit">Fit</button></div>
    <div class="legend" aria-hidden="true"><span><i style="background:var(--ink);border-radius:4px"></i>Your companies</span><span><i style="background:#D3D3DA"></i>Rivals</span><span><i style="background:#fff;box-shadow:inset 0 0 0 1.5px var(--ink)"></i>Investors</span><span><i style="background:#8A8A93;width:7px;height:7px"></i>People</span><span><i style="background:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)"></i>Touches 2+ of yours</span></div>`;
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `Perimeter graph: ${nodes.length} entities and ${edges.length} links around ${cosN.length} portfolio companies`);
  svg.innerHTML = `<defs><radialGradient id="hotGlow"><stop offset="0" stop-color="#3D5AFE" stop-opacity=".28"/><stop offset="1" stop-color="#3D5AFE" stop-opacity="0"/></radialGradient></defs><g class="ge"></g><g class="gn"></g><g class="gl"></g>`;
  wrap.prepend(svg);
  const gE = svg.querySelector('.ge'), gN = svg.querySelector('.gn'), gL = svg.querySelector('.gl');
  edges.forEach(e => {
    e.el = document.createElementNS(NS, 'line');
    e.el.setAttribute('class', 'g-edge' + (e.hot ? ' hot' : ''));
    if (e.kind === 'coco') { e.el.setAttribute('stroke-dasharray', '5 5'); e.el.style.strokeWidth = 1.5; }
    gE.appendChild(e.el);
  });
  nodes.forEach((n, i) => {
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'g-node'); g.setAttribute('tabindex', '0'); g.setAttribute('role', 'button');
    g.setAttribute('aria-label', `${n.name}, ${KIND_LABEL[n.kind]}${n.hot ? ', shared' : ''}`);
    let inner = '';
    if (n.hot) inner += `<circle r="${n.r + 18}" fill="url(#hotGlow)"/>`;
    if (n.kind === 'co') {
      inner += `<rect x="${-n.r}" y="${-n.r}" width="${n.r * 2}" height="${n.r * 2}" rx="14" fill="#0A0A0A" ${n.hot ? 'stroke="#3D5AFE" stroke-width="3"' : ''}/><text text-anchor="middle" dy="4.5" fill="#fff" font-size="13" font-weight="600" style="pointer-events:none">${esc(initials(n.name))}</text>`;
    } else if (n.kind === 'rival') {
      inner += `<circle r="${n.r}" fill="${n.hot ? '#3D5AFE' : '#D3D3DA'}" stroke="#fff" stroke-width="2"/>`;
    } else if (n.kind === 'inv') {
      inner += `<circle r="${n.r}" fill="${n.hot ? '#3D5AFE' : '#fff'}" stroke="${n.hot ? '#EEF1FF' : '#0A0A0A'}" stroke-width="${n.hot ? 3 : 1.5}"/>`;
    } else {
      inner += `<circle r="${n.r}" fill="${n.hot ? '#3D5AFE' : '#8A8A93'}" stroke="#fff" stroke-width="1.5"/>`;
    }
    g.innerHTML = inner;
    g.style.animation = `fade .5s ${(n.kind === 'co' ? 0 : 0.15 + i * 0.006).toFixed(3)}s both`;
    n.el = g; gN.appendChild(g);
    const t = document.createElementNS(NS, 'text');
    t.setAttribute('class', 'g-label' + (n.kind === 'co' ? ' co' : '') + (n.hot ? ' hot' : ''));
    t.setAttribute('text-anchor', 'middle');
    t.textContent = n.name;
    n.lab = t; gL.appendChild(t);
  });
  let allLabels = false;
  const baseLabel = n => n.kind === 'co' || n.hot || allLabels;
  const applyLabels = () => nodes.forEach(n => { n.lab.style.opacity = baseLabel(n) ? 1 : 0; });
  applyLabels();

  // ---------- viewBox / camera ----------
  let vb = { x: 0, y: 0, w: W, h: H };
  let userCam = false;
  function fitBox() {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    nodes.forEach(n => { x0 = Math.min(x0, n.x - n.r - 40); y0 = Math.min(y0, n.y - n.r - 20); x1 = Math.max(x1, n.x + n.r + 40); y1 = Math.max(y1, n.y + n.r + 30); });
    const rw = wrap.clientWidth || W, rh = wrap.clientHeight || H;
    let w = x1 - x0, h = y1 - y0; const asp = rw / rh;
    if (w / h > asp) { const nh = w / asp; y0 -= (nh - h) / 2; h = nh; } else { const nw = h * asp; x0 -= (nw - w) / 2; w = nw; }
    const pad = 1.08;
    return { x: x0 - w * (pad - 1) / 2, y: y0 - h * (pad - 1) / 2, w: w * pad, h: h * pad };
  }
  const setVB = () => svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
  vb = fitBox(); setVB();

  function draw() {
    edges.forEach(e => { e.el.setAttribute('x1', e.a.x); e.el.setAttribute('y1', e.a.y); e.el.setAttribute('x2', e.b.x); e.el.setAttribute('y2', e.b.y); });
    nodes.forEach(n => {
      n.el.setAttribute('transform', `translate(${n.x.toFixed(1)},${n.y.toFixed(1)})`);
      n.lab.setAttribute('x', n.x.toFixed(1)); n.lab.setAttribute('y', (n.y + n.r + (n.kind === 'co' ? 17 : 14)).toFixed(1));
    });
  }
  let raf = 0, dead = false;
  function loop() {
    if (dead) return;
    if (alpha > 0.004) {
      tick(); tick();
      if (!userCam) { const f = fitBox(); vb = { x: vb.x + (f.x - vb.x) * .15, y: vb.y + (f.y - vb.y) * .15, w: vb.w + (f.w - vb.w) * .15, h: vb.h + (f.h - vb.h) * .15 }; setVB(); }
      draw(); raf = requestAnimationFrame(loop);
  setTimeout(() => nodes.forEach(n => { n.el.style.animation = ''; }), 1600);
    } else { draw(); raf = 0; }
  }
  const reheat = (a = .3) => { alpha = Math.max(alpha, a); if (!raf) raf = requestAnimationFrame(loop); };
  draw(); raf = requestAnimationFrame(loop);

  // ---------- hover highlight ----------
  let hovered = null;
  function highlight(n, ev) {
    hovered = n;
    if (!n) { svg.classList.remove('dim'); nodes.forEach(x => { x.el.classList.remove('fade'); x.lab.classList.remove('fade', 'lit'); }); edges.forEach(e => e.el.classList.remove('fade', 'lit')); applyLabels(); hideTip(); return; }
    const near = nb.get(n);
    svg.classList.add('dim');
    nodes.forEach(x => { const on = x === n || near.has(x); x.el.classList.toggle('fade', !on); x.lab.classList.toggle('fade', !on); x.lab.classList.toggle('lit', on); x.lab.style.opacity = on ? 1 : 0; });
    edges.forEach(e => { const on = e.a === n || e.b === n; e.el.classList.toggle('lit', on); e.el.classList.toggle('fade', !on); });
    n.el.parentNode.appendChild(n.el);
    if (ev) tipFor(n, ev.clientX, ev.clientY);
  }
  function tipFor(n, x, y) {
    const owners = [...nb.get(n)].filter(o => o.kind === 'co').map(o => o.name);
    const shared = [...n.shared].filter(s => !owners.includes(s));
    let html = `<b>${esc(n.name)}</b><br><span>${esc(KIND_LABEL[n.kind])}${n.sub ? ' · ' + esc(n.sub) : ''}</span>`;
    if (n.kind !== 'co' && owners.length) html += `<br><span>Linked to ${esc(owners.join(', '))}</span>`;
    if (shared.length) html += `<br><span style="color:#9DB0FF">Also touches ${esc(shared.join(', '))}</span>`;
    if (n.kind === 'co') html += `<br><span>${nb.get(n).size} links in the perimeter</span>`;
    floatTip(html, x, y);
  }

  // ---------- pointer: drag nodes, pan, zoom ----------
  const toSvg = (cx, cy) => { const p = svg.createSVGPoint(); p.x = cx; p.y = cy; return p.matrixTransform(svg.getScreenCTM().inverse()); };
  let drag = null; // {node, moved, sx, sy} or {pan, sx, sy, vb}
  const nodeFrom = el => { const g = el.closest?.('.g-node'); return g ? nodes.find(n => n.el === g) : null; };
  svg.addEventListener('pointerdown', ev => {
    const n = nodeFrom(ev.target);
    svg.setPointerCapture(ev.pointerId);
    if (n) { drag = { node: n, moved: false, sx: ev.clientX, sy: ev.clientY }; n.fx = n.x; n.fy = n.y; }
    else { drag = { pan: true, sx: ev.clientX, sy: ev.clientY, vb: { ...vb }, moved: false }; svg.classList.add('drag'); }
  });
  svg.addEventListener('pointermove', ev => {
    if (!drag) { const n = nodeFrom(ev.target); if (n !== hovered) highlight(n, ev); else if (n) tipFor(n, ev.clientX, ev.clientY); return; }
    if (Math.abs(ev.clientX - drag.sx) + Math.abs(ev.clientY - drag.sy) > 4) drag.moved = true;
    if (drag.node && drag.moved) {
      const p = toSvg(ev.clientX, ev.clientY); drag.node.fx = p.x; drag.node.fy = p.y; userCam = true; reheat(.25); hideTip();
    } else if (drag.pan && drag.moved) {
      const sc = vb.w / svg.clientWidth; userCam = true;
      vb = { ...drag.vb, x: drag.vb.x - (ev.clientX - drag.sx) * sc, y: drag.vb.y - (ev.clientY - drag.sy) * sc }; setVB();
    }
  });
  const end = ev => {
    if (!drag) return;
    const d = drag; drag = null; svg.classList.remove('drag');
    if (d.node) {
      if (!d.moved) { d.node.fx = d.node.fy = null; if (d.node.id) { hideTip(); openEntity({ id: d.node.id, name: d.node.name, type: d.node.type, sub: d.node.sub }); } }
      else { d.node.fx = d.node.fy = null; reheat(.15); }
    }
  };
  svg.addEventListener('pointerup', end);
  svg.addEventListener('pointercancel', end);
  svg.addEventListener('pointerleave', () => { if (!drag) highlight(null); });
  svg.addEventListener('wheel', ev => {
    ev.preventDefault(); userCam = true;
    const p = toSvg(ev.clientX, ev.clientY);
    const f = Math.exp(ev.deltaY * 0.0012);
    const nw = Math.min(Math.max(vb.w * f, 250), 4000), s = nw / vb.w;
    vb = { x: p.x - (p.x - vb.x) * s, y: p.y - (p.y - vb.y) * s, w: nw, h: vb.h * s }; setVB();
  }, { passive: false });
  svg.addEventListener('keydown', ev => {
    const n = nodeFrom(ev.target);
    if (n && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); if (n.id) openEntity({ id: n.id, name: n.name, type: n.type, sub: n.sub }); }
  });
  svg.addEventListener('focusin', ev => { const n = nodeFrom(ev.target); if (n) { const r = n.el.getBoundingClientRect(); highlight(n); tipFor(n, r.right, r.top); } });
  svg.addEventListener('focusout', () => highlight(null));
  wrap.querySelector('[data-g="fit"]').onclick = () => { userCam = false; vb = fitBox(); setVB(); };
  const lb = wrap.querySelector('[data-g="labels"]');
  lb.onclick = () => { allLabels = !allLabels; lb.setAttribute('aria-pressed', allLabels); lb.classList.toggle('dark', allLabels); applyLabels(); };
  const ro = new ResizeObserver(() => { if (!userCam) { vb = fitBox(); setVB(); } });
  ro.observe(wrap);

  return { destroy() { dead = true; cancelAnimationFrame(raf); ro.disconnect(); hideTip(); } };
}

// Overlap explainer: the chain of Cala edges behind an overlap (portfolio ← investor → rival ⟷ portfolio),
// inline as a chip chain and in a detail sheet with per-edge sources and rounds.
import { esc, keep, lookup, nm, srcChips, fmtDate, openPopover, openPanel, closeSheet, plural } from './ui.js';

const ROLE_TAG = { portfolio: 'Yours', shared: 'In common', rival: 'Rival' };

function roundLine(r) {
  return [r.round, r.amount, r.date ? fmtDate(r.date, { year: true }) : ''].filter(Boolean).join(' · ');
}

function nodeChip(n) {
  const e = n.entity || {};
  return `<button type="button" class="pnode ${esc(e.role || '')}" data-ent="${keep({ id: e.id, name: e.name, type: e.type })}">${esc(nm(e.name))}</button>`;
}
function edgeChip(edge) {
  const n = (edge.sources || []).length;
  return `<button type="button" class="pedge" data-pedge="${keep(edge)}" aria-haspopup="dialog" aria-label="${esc(edge.label)}: ${plural(n, 'source')}"><span>${esc(edge.label)}</span><i aria-hidden="true"></i></button>`;
}

// Inline chain for cards and signal rows.
export function pathHTML(path) {
  if (!path?.length) return '';
  return `<div class="path" role="group" aria-label="How this overlap connects">${path.map(n => nodeChip(n) + (n.edge_to_next ? edgeChip(n.edge_to_next) : '')).join('')}</div>`;
}

function edgePopHTML(edge, from, to) {
  const rounds = edge.rounds || [];
  return `<span class="cap">Cala link</span><button type="button" class="x" aria-label="Close" data-close>×</button>
    <span class="pop-t">${esc(nm(from?.name || ''))} <span style="color:var(--accent-ink)">${esc(edge.label)}</span> ${esc(nm(to?.name || ''))}</span>
    ${edge.note ? `<span class="meta" style="color:var(--muted)">${esc(edge.note)}</span>` : ''}
    ${rounds.length ? `<div class="rounds">${rounds.map(r => `<span>${esc(roundLine(r))}</span>`).join('')}</div>` : ''}
    ${(edge.sources || []).length ? `<div class="chips">${srcChips(edge.sources, 4)}</div>` : '<span class="meta">No public source for this link.</span>'}`;
}

// Popovers for edge chips (delegated once).
let installed = false;
export function installPathHandlers() {
  if (installed) return; installed = true;
  document.addEventListener('click', e => {
    const b = e.target.closest('[data-pedge]');
    if (!b) return;
    e.preventDefault(); e.stopPropagation();
    const edge = lookup(b.dataset.pedge);
    const from = b.previousElementSibling, to = b.nextElementSibling;
    const ref = el => el?.dataset.ent ? lookup(el.dataset.ent) : null;
    openPopover(b, edgePopHTML(edge, ref(from), ref(to)), { label: 'Link sources' });
  }, true);
}

// Detail sheet.
export function openOverlap(item, { onDraft } = {}) {
  const path = item.path || [];
  if (!path.length) return;
  const steps = path.map((n, i) => {
    const e = n.entity || {}; const edge = n.edge_to_next;
    const nodeRow = `<div class="pstep"><span class="pdot ${esc(e.role || '')}" aria-hidden="true"></span>
      <button type="button" class="ent pname" data-ent="${keep({ id: e.id, name: e.name, type: e.type })}">${esc(nm(e.name))}</button>
      <span class="ptag ${esc(e.role || '')}">${esc(ROLE_TAG[e.role] || '')}</span></div>`;
    if (!edge) return nodeRow;
    const rounds = edge.rounds || [];
    return nodeRow + `<div class="plink"><span class="pline" aria-hidden="true"></span><div class="pbody">
      <b>${esc(edge.label)}</b>
      ${edge.note ? `<span class="meta" style="color:var(--muted)">${esc(edge.note)}</span>` : ''}
      ${rounds.length ? `<div class="rounds">${rounds.map(r => `<span>${esc(roundLine(r))}</span>`).join('')}</div>` : ''}
      ${(edge.sources || []).length ? `<div class="chips">${srcChips(edge.sources, 3)}</div>` : `<span class="meta">Cala record, no public link</span>`}
    </div></div>`;
  }).join('');
  const rival = path.find(n => n.entity?.role === 'rival')?.entity;
  const ids = [...new Set(path.map(n => n.entity?.id).filter(Boolean))];
  const shared = path.find(n => n.entity?.role === 'shared')?.entity;
  const mapHref = `#/map?focus=${encodeURIComponent(shared?.id || ids[0] || '')}&with=${encodeURIComponent(ids.join(','))}`;
  const kind = { overlap_investor: 'Investor overlap', overlap_board: 'Board overlap', hiring: 'People overlap' }[item.kind] || item.kind || 'Overlap';
  const el = openPanel({
    cap: kind, title: item.title || item.text || 'Overlap', label: 'Overlap details',
    body: `<section class="sec"><h3 class="h">How they connect</h3><div class="psteps">${steps}</div></section>
      ${item.body ? `<p class="muted">${esc(item.body)}</p>` : ''}
      <div class="pacts">
        ${onDraft ? `<button type="button" class="btn dark lg" data-odraft>Draft note to founder</button>` : ''}
        ${rival?.id ? `<a class="btn lg" href="#/check/${encodeURIComponent(rival.id)}" data-close-sheet>Run check on ${esc(nm(rival.name))}</a>` : ''}
        <a class="btn lg" href="${mapHref}" data-close-sheet>Show on map</a>
      </div>`,
  });
  el.querySelector('[data-odraft]')?.addEventListener('click', () => { closeSheet(); onDraft(item); });
}

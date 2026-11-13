// API client. Real backend by default; `?mock=1` or a failing /api/health switches to fixtures in mock.js.
let mock = null; // module when in mock mode
export const state = { mock: false, reason: '' };

// Per-browser profile. `pid` is this browser's own profile id (localStorage + a `pid` cookie for plain links);
// `view` is 'demo' while exploring the shared demo, else 'me'. Every request carries both.
const PID_KEY = 'perimeter-pid', VIEW_KEY = 'perimeter-view';
const ls = { get: k => { try { return localStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch {} } };
function newPid() {
  const a = new Uint8Array(12); crypto.getRandomValues(a);
  return 'p' + [...a].map(b => b.toString(16).padStart(2, '0')).join('');
}
export const who = {
  pid: ls.get(PID_KEY) || '',
  view: ls.get(VIEW_KEY) === 'demo' ? 'demo' : 'me',
};
if (!/^[A-Za-z0-9_-]{8,64}$/.test(who.pid)) { who.pid = newPid(); ls.set(PID_KEY, who.pid); }
document.cookie = `pid=${who.pid}; path=/; max-age=31536000; SameSite=Lax`;
export function setView(v) { who.view = v === 'demo' ? 'demo' : 'me'; ls.set(VIEW_KEY, who.view === 'demo' ? 'demo' : null); }
export function newIdentity() { who.pid = newPid(); ls.set(PID_KEY, who.pid); document.cookie = `pid=${who.pid}; path=/; max-age=31536000; SameSite=Lax`; }
const idHeaders = () => ({ 'X-Profile': who.pid, ...(who.view === 'demo' ? { 'X-View': 'demo' } : {}) });

async function timeoutFetch(url, opts = {}, ms = 4000) {
  const c = new AbortController();
  const t = setTimeout(() => c.abort(), ms);
  try { return await fetch(url, { ...opts, signal: c.signal }); } finally { clearTimeout(t); }
}

export async function initApi() {
  const qs = new URLSearchParams(location.search);
  let want = qs.get('mock') === '1';
  if (qs.get('mock') === '0') want = false;
  else if (!want) {
    try {
      const r = await timeoutFetch('/api/health', {}, 3500);
      const j = r.ok ? await r.json() : null;
      if (!j || !j.ok) { want = true; state.reason = 'Backend unavailable'; }
    } catch { want = true; state.reason = 'Backend unavailable'; }
  } else state.reason = 'Mock mode';
  if (want) { mock = await import('./mock.js'); state.mock = true; }
}

async function req(method, path, body) {
  if (mock) return mock.handle(method, path, body);
  const r = await fetch(path, {
    method,
    headers: { ...idHeaders(), ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { const j = await r.json(); msg = j.detail || j.message || msg; if (typeof msg !== 'string') msg = JSON.stringify(msg); } catch {}
    const e = new Error(msg); e.status = r.status; throw e;
  }
  return r.json();
}

export const api = {
  health: () => req('GET', '/api/health'),
  resolve: text => req('POST', '/api/resolve', { text }),
  portfolio: () => req('GET', '/api/portfolio'),
  savePortfolio: ids => req('POST', '/api/portfolio', { ids }),
  demo: () => req('POST', '/api/portfolio/demo'),
  rebuild: () => req('POST', '/api/rebuild'),
  profile: () => mock ? Promise.resolve({ pid: who.pid, exists: false, viewing: 'demo', demo_locked: false, profile: null, context: {} }) : req('GET', '/api/profile'),
  saveProfile: body => req('PUT', '/api/profile', body),
  resetProfile: () => req('POST', '/api/profile/reset'),
  perimeter: () => req('GET', '/api/perimeter'),
  feed: () => req('GET', '/api/feed'),
  ask: q => req('POST', '/api/ask', { q }),
  draft: item_id => req('POST', '/api/draft', { item_id }),
  entity: id => req('GET', `/api/entity/${encodeURIComponent(id)}`),
  // SSE check stream. handlers: {step, partial, result, error}. Returns a close() fn.
  check(q, h) {
    if (mock) return mock.checkStream(q, h);
    const es = new EventSource(`/api/check/stream?q=${encodeURIComponent(q)}&pid=${encodeURIComponent(who.pid)}${who.view === 'demo' ? '&view=demo' : ''}`);
    let finished = false;
    const parse = ev => { try { return JSON.parse(ev.data); } catch { return {}; } };
    es.addEventListener('step', ev => h.step?.(parse(ev)));
    es.addEventListener('partial', ev => h.partial?.(parse(ev)));
    es.addEventListener('result', ev => { finished = true; es.close(); h.result?.(parse(ev)); });
    es.addEventListener('error', ev => {
      if (finished) return;
      finished = true; es.close();
      const d = ev.data ? parse(ev) : {};
      h.error?.(d.message || 'The check stream was interrupted.');
    });
    return () => { finished = true; es.close(); };
  },
};

// API client. Real backend by default; `?mock=1` or a failing /api/health switches to fixtures in mock.js.
let mock = null; // module when in mock mode
export const state = { mock: false, reason: '' };

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
    headers: body ? { 'Content-Type': 'application/json' } : {},
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
  perimeter: () => req('GET', '/api/perimeter'),
  feed: () => req('GET', '/api/feed'),
  ask: q => req('POST', '/api/ask', { q }),
  draft: item_id => req('POST', '/api/draft', { item_id }),
  entity: id => req('GET', `/api/entity/${encodeURIComponent(id)}`),
  // SSE check stream. handlers: {step, result, error}. Returns a close() fn.
  check(q, h) {
    if (mock) return mock.checkStream(q, h);
    const es = new EventSource(`/api/check/stream?q=${encodeURIComponent(q)}`);
    let finished = false;
    const parse = ev => { try { return JSON.parse(ev.data); } catch { return {}; } };
    es.addEventListener('step', ev => h.step?.(parse(ev)));
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

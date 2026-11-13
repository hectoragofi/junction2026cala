// Fixtures shaped exactly like CONTRACT.md. Used with ?mock=1 or when /api/health fails.
const today = new Date();
const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const ago = n => { const d = new Date(today); d.setDate(d.getDate() - n); return iso(d); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const cala = (what, date) => ({ name: `Cala · ${what}`, url: null, date: date ?? null });
const web = (name, url, date) => ({ name, url, date });

// ---------- entity catalog ----------
const C = (id, name, description, website, hq, founded, industry) => ({ id, name, type: 'Company', description, website, hq, founded, industry });
const I = (id, name, sub) => ({ id, name, type: 'Investor', sub });
const P = (id, name, role) => ({ id, name, type: 'Person', role });

const co = {
  mollie: C('co-mollie', 'Mollie', 'Payment service provider for European SMBs and enterprises.', 'mollie.com', 'Amsterdam', '2004', 'Payments'),
  qonto: C('co-qonto', 'Qonto', 'Business current account and finance tools for SMEs and freelancers.', 'qonto.com', 'Paris', '2016', 'Business banking'),
  pennylane: C('co-pennylane', 'Pennylane', 'Accounting and financial management software for SMEs and their accountants.', 'pennylane.com', 'Paris', '2020', 'Accounting software'),
  gocardless: C('co-gocardless', 'GoCardless', 'Bank payment network for recurring and one-off payments.', 'gocardless.com', 'London', '2011', 'Bank payments'),
  adyen: C('co-adyen', 'Adyen', 'Global payments platform for enterprise merchants.', 'adyen.com', 'Amsterdam', '2006', 'Payments'),
  stripe: C('co-stripe', 'Stripe', 'Financial infrastructure and payments APIs for internet businesses.', 'stripe.com', 'San Francisco', '2010', 'Payments'),
  checkout: C('co-checkout', 'Checkout.com', 'Enterprise payment processing platform.', 'checkout.com', 'London', '2012', 'Payments'),
  worldline: C('co-worldline', 'Worldline', 'Listed European payment services group.', 'worldline.com', 'Paris', '1974', 'Payments'),
  revolut: C('co-revolut-business', 'Revolut Business', 'Business accounts within the Revolut group.', 'revolut.com', 'London', '2015', 'Business banking'),
  shine: C('co-shine', 'Shine', 'Online business account for freelancers, part of Ageas group.', 'shine.fr', 'Paris', '2017', 'Business banking'),
  memo: C('co-memo-bank', 'Memo Bank', 'Independent French bank for mid-sized companies.', 'memo.bank', 'Paris', '2017', 'Business banking'),
  finom: C('co-finom', 'Finom', 'Business banking and invoicing for European SMEs.', 'finom.co', 'Amsterdam', '2019', 'Business banking'),
  sage: C('co-sage', 'Sage', 'Listed accounting and payroll software group.', 'sage.com', 'Newcastle', '1981', 'Accounting software'),
  tiime: C('co-tiime', 'Tiime', 'Accounting software for French accountants and SMEs.', 'tiime.fr', 'Paris', '2015', 'Accounting software'),
  agicap: C('co-agicap', 'Agicap', 'Cash-flow management software for SMEs.', 'agicap.com', 'Lyon', '2016', 'Finance software'),
  spendesk: C('co-spendesk', 'Spendesk', 'Spend management platform for finance teams.', 'spendesk.com', 'Paris', '2016', 'Finance software'),
  truelayer: C('co-truelayer', 'TrueLayer', 'Open banking payments network.', 'truelayer.com', 'London', '2016', 'Open banking'),
  tink: C('co-tink', 'Tink', 'Open banking platform, owned by Visa.', 'tink.com', 'Stockholm', '2012', 'Open banking'),
};
const inv = {
  tcv: I('inv-tcv', 'TCV', 'Growth equity'),
  ga: I('inv-general-atlantic', 'General Atlantic', 'Growth equity'),
  bx: I('inv-blackstone-growth', 'Blackstone Growth', 'Growth equity'),
  alkeon: I('inv-alkeon', 'Alkeon Capital', 'Crossover fund'),
  tencent: I('inv-tencent', 'Tencent', 'Strategic'),
  dst: I('inv-dst', 'DST Global', 'Growth'),
  tiger: I('inv-tiger', 'Tiger Global', 'Crossover fund'),
  alven: I('inv-alven', 'Alven', 'Early-stage VC'),
  valar: I('inv-valar', 'Valar Ventures', 'Early-stage VC'),
  sequoia: I('inv-sequoia', 'Sequoia Capital', 'Venture capital'),
  partech: I('inv-partech', 'Partech', 'Venture capital'),
  gc: I('inv-general-catalyst', 'General Catalyst', 'Venture capital'),
  accel: I('inv-accel', 'Accel', 'Venture capital'),
  balderton: I('inv-balderton', 'Balderton Capital', 'Venture capital'),
  permira: I('inv-permira', 'Permira', 'Private equity'),
  bcv: I('inv-bain-capital-ventures', 'Bain Capital Ventures', 'Venture capital'),
};
const ppl = {
  mol: P('p-adriaan-mol', 'Adriaan Mol', 'Founder'),
  happach: P('p-shane-happach', 'Shane Happach', 'CEO'),
  prot: P('p-alexandre-prot', 'Alexandre Prot', 'Co-founder, CEO'),
  anavi: P('p-steve-anavi', 'Steve Anavi', 'Co-founder'),
  waller: P('p-arthur-waller', 'Arthur Waller', 'Co-founder, CEO'),
  letourneur: P('p-charles-letourneur', 'Charles Letourneur', 'Board member'),
  takeuchi: P('p-hiroki-takeuchi', 'Hiroki Takeuchi', 'Co-founder, CEO'),
  robinson: P('p-matt-robinson', 'Matt Robinson', 'Co-founder'),
  blomfield: P('p-tom-blomfield', 'Tom Blomfield', 'Co-founder'),
};
const ref = (x, sub) => ({ id: x.id, name: x.name, type: x.type, ...(sub || x.sub ? { sub: sub || x.sub } : {}) });

const PERIM = {
  mollie: { rivals: ['adyen', 'stripe', 'checkout', 'worldline', 'gocardless'], investors: [['tcv'], ['ga'], ['bx'], ['alkeon', ['GoCardless']]], people: [['mol'], ['happach']] },
  qonto: { rivals: ['revolut', 'shine', 'memo', 'finom'], investors: [['tencent'], ['dst', ['Pennylane']], ['tiger', ['GoCardless', 'Checkout.com']], ['alven', ['Pennylane']], ['valar']], people: [['prot'], ['anavi'], ['letourneur', ['Pennylane']]] },
  pennylane: { rivals: ['sage', 'tiime', 'agicap', 'spendesk'], investors: [['sequoia'], ['dst', ['Qonto']], ['alven', ['Qonto']], ['partech'], ['gc']], people: [['waller'], ['letourneur', ['Qonto']]] },
  gocardless: { rivals: ['stripe', 'adyen', 'mollie', 'truelayer', 'tink'], investors: [['accel'], ['balderton'], ['permira'], ['bcv'], ['alkeon', ['Mollie']], ['tiger', ['Qonto', 'Checkout.com']]], people: [['takeuchi'], ['robinson'], ['blomfield']] },
};
const PORTFOLIO_KEYS = ['mollie', 'qonto', 'pennylane', 'gocardless'];
const allEntities = new Map();
[...Object.values(co), ...Object.values(inv), ...Object.values(ppl)].forEach(e => allEntities.set(e.id, e));
const keyOf = id => Object.keys(co).find(k => co[k].id === id);

// ---------- portfolio state (persisted so reloads keep it) ----------
const LS = 'perimeter-mock-portfolio';
function load() { try { return JSON.parse(localStorage.getItem(LS)) || { ids: [], buildUntil: 0, built_at: null }; } catch { return { ids: [], buildUntil: 0, built_at: null }; } }
function save(s) { try { localStorage.setItem(LS, JSON.stringify(s)); } catch {} }
let pf = load();
const companyPublic = c => ({ id: c.id, name: c.name, description: c.description, website: c.website, hq: c.hq, founded: c.founded });
function startBuild(ids) { pf = { ids, buildUntil: Date.now() + 7000, built_at: null }; save(pf); }
function portfolioCompanies() {
  return pf.ids.map(id => allEntities.get(id)).filter(Boolean).map(companyPublic);
}

// ---------- endpoints ----------
function perimeter() {
  const keys = pf.ids.map(keyOf).filter(k => PERIM[k]);
  const names = new Set(keys.map(k => co[k].name));
  const companies = keys.map(k => {
    const p = PERIM[k];
    const filt = arr => (arr || []).filter(n => names.has(n) || !PORTFOLIO_KEYS.some(pk => co[pk].name === n));
    return {
      ...companyPublic(co[k]), industry: co[k].industry,
      rivals: p.rivals.map(r => ref(co[r], co[r].hq)),
      investors: p.investors.map(([i, sw]) => ({ ...ref(inv[i]), ...(filt(sw).length ? { shared_with: filt(sw) } : {}) })),
      people: p.people.map(([x, sw]) => ({ ...ref(ppl[x]), role: ppl[x].role, ...(filt(sw).length ? { shared_with: filt(sw) } : {}) })),
    };
  });
  const uniq = f => new Set(companies.flatMap(f).map(e => e.id)).size;
  const S = (k) => keys.includes(k);
  const signals = [
    S('qonto') && S('pennylane') && { kind: 'Board seat', text: 'Charles Letourneur (Alven) sits on the boards of both Qonto and Pennylane.', entities: [ref(ppl.letourneur), ref(co.qonto), ref(co.pennylane)], sources: [cala('board member', ago(30))] },
    S('qonto') && S('pennylane') && { kind: 'Shared investor', text: 'DST Global and Alven back both Qonto and Pennylane, two companies selling into the same French SME finance stack.', entities: [ref(inv.dst), ref(inv.alven)], sources: [cala('funding round', '2024-06-20'), cala('funding round', '2022-01-10')] },
    S('mollie') && S('gocardless') && { kind: 'Shared investor', text: 'Alkeon Capital holds stakes in Mollie and GoCardless, and Cala lists them as direct rivals.', entities: [ref(inv.alkeon), ref(co.mollie), ref(co.gocardless)], sources: [cala('investment', '2021-06-17'), cala('competitor')] },
    S('mollie') && S('gocardless') && { kind: 'Rival in portfolio', text: 'GoCardless and Mollie compete for European recurring payments. Both are yours.', entities: [ref(co.gocardless), ref(co.mollie)], sources: [cala('competitor')] },
    S('gocardless') && { kind: 'Talent', text: 'GoCardless co-founder Tom Blomfield later founded Monzo; two GoCardless alumni now run product at TrueLayer.', entities: [ref(ppl.blomfield), ref(co.truelayer)], sources: [cala('employment history')] },
    S('mollie') && { kind: 'M&A', text: 'Mollie acquired Klearly in 2024 to add in-person payments, moving closer to Adyen’s unified commerce.', entities: [ref(co.mollie)], sources: [web('Mollie newsroom', 'https://www.mollie.com/news', '2024-11-12')] },
    S('qonto') && { kind: 'Funding', text: 'Finom, a Qonto rival, raised €92M Series C led by General Catalyst and AVP.', entities: [ref(co.finom), ref(inv.gc)], sources: [cala('funding round', ago(9))] },
  ].filter(Boolean);
  return {
    companies,
    stats: { rivals: uniq(c => c.rivals), investors: uniq(c => c.investors), people: uniq(c => c.people), countries: 5, entities: 64, facts: 3412 },
    signals,
  };
}

function feed() {
  const keys = pf.ids.map(keyOf);
  const has = k => keys.includes(k);
  const items = [
    has('qonto') && has('pennylane') && { id: 'f1', kind: 'overlap_board', category: 'Overlaps', severity: 'medium', status: 'confirmed', title: 'Charles Letourneur sits on both Qonto’s and Pennylane’s boards', body: 'Pennylane just launched business accounts, putting it head to head with Qonto for the same SMEs.', date: ago(0), company: ref(co.pennylane), subject: { ...ref(ppl.letourneur), relation: 'board member at Qonto' }, sources: [cala('board member', ago(2)), web('Les Echos', 'https://www.lesechos.fr/tech-medias/hightech', ago(0))], actions: ['draft_note'] },
    has('mollie') && { id: 'f2', kind: 'regulatory', category: 'Risk', severity: 'high', status: 'confirmed', title: 'Adyen fined by the Dutch central bank over AML controls', body: 'De Nederlandsche Bank published the penalty decision. Adyen is Mollie’s closest rival in the Netherlands.', date: ago(0), company: ref(co.mollie), subject: { ...ref(co.adyen), relation: 'rival of Mollie' }, sources: [web('DNB register', 'https://www.dnb.nl/en/sector-information/', ago(1)), cala('regulatory event', ago(1))], actions: ['draft_note'] },
    has('gocardless') && { id: 'f3', kind: 'overlap_investor', category: 'Overlaps', severity: 'medium', status: 'confirmed', title: 'Tiger Global backs GoCardless and Qonto, and led a rival’s new round', body: 'Tiger Global took part in TrueLayer’s extension, a direct rival of GoCardless in open-banking payments.', date: ago(1), company: ref(co.gocardless), subject: { ...ref(inv.tiger), relation: 'investor in GoCardless' }, sources: [cala('funding round', ago(1))], actions: ['draft_note'] },
    has('qonto') && { id: 'f4', kind: 'legal', category: 'Risk', severity: 'medium', status: 'possible', confidence: 0.72, title: '“Qonto SAS” named in a dispute with a payment-card processor', body: 'Is this Qonto? Le Monde Informatique reported a commercial claim against an entity with the same name.', date: ago(2), company: ref(co.qonto), sources: [web('Le Monde Informatique', 'https://www.lemondeinformatique.fr/', ago(2))], actions: [] },
    has('qonto') && { id: 'f5', kind: 'funding', category: 'Funding', severity: 'low', status: 'confirmed', title: 'Finom raised €92M, led by General Catalyst and AVP', date: ago(4), company: ref(co.qonto), subject: { ...ref(co.finom), relation: 'rival of Qonto' }, sources: [cala('funding round', ago(4))], actions: [] },
    has('pennylane') && { id: 'f6', kind: 'hiring', category: 'Other', severity: 'info', status: 'reported', title: 'Agicap’s headcount grew from 380 to 455 in a year', date: ago(5), company: ref(co.pennylane), subject: { ...ref(co.agicap), relation: 'rival of Pennylane' }, sources: [cala('employees', ago(5))], actions: [] },
    has('gocardless') && { id: 'f7', kind: 'mna', category: 'Other', severity: 'low', status: 'confirmed', title: 'Tink, a GoCardless rival, folded into Visa’s open-banking unit', date: ago(6), company: ref(co.gocardless), subject: { ...ref(co.tink), relation: 'rival of GoCardless' }, sources: [cala('corporate event', ago(6))], actions: [] },
    has('mollie') && { id: 'f8', kind: 'regulatory', category: 'Risk', severity: 'low', status: 'confirmed', title: 'New EU instant-payments rules apply to Mollie and 4 of its rivals', date: ago(11), company: ref(co.mollie), sources: [cala('law', ago(11)), web('EUR-Lex', 'https://eur-lex.europa.eu/', '2024-03-19')], actions: [] },
    has('pennylane') && { id: 'f9', kind: 'funding', category: 'Funding', severity: 'medium', status: 'confirmed', title: 'Spendesk raised a €30M extension from existing investors', body: 'Spendesk now overlaps with Pennylane on SME spend management. The round was flat to its last valuation.', date: ago(18), company: ref(co.pennylane), subject: { ...ref(co.spendesk), relation: 'rival of Pennylane' }, sources: [cala('funding round', ago(18)), web('Maddyness', 'https://www.maddyness.com/', ago(17))], actions: ['draft_note'] },
    has('mollie') && { id: 'f10', kind: 'news', category: 'Other', severity: 'info', status: 'reported', title: 'Stripe expanded local acquiring in Belgium and Austria', date: ago(26), company: ref(co.mollie), subject: { ...ref(co.stripe), relation: 'rival of Mollie' }, sources: [web('Stripe blog', 'https://stripe.com/blog', ago(26))], actions: [] },
    has('qonto') && { id: 'f11', kind: 'news', category: 'Other', severity: 'info', status: 'reported', title: 'Shine passed 150,000 business customers', date: ago(41), company: ref(co.qonto), subject: { ...ref(co.shine), relation: 'rival of Qonto' }, sources: [cala('news', ago(41))], actions: [] },
  ].filter(Boolean);
  const n = items.filter(i => i.severity === 'high' || i.severity === 'medium').length;
  return { summary: items.length ? `${n} things need a look across your ${keys.length} companies. Everything else is quiet.` : `Watching ${keys.length} companies. Nothing has changed yet.`, items };
}

function entity(id) {
  const e = allEntities.get(id);
  if (!e) {
    const name = decodeURIComponent(id).replace(/^[a-z]+-/, '').replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    return { id, name, type: 'Company', description: '', facts: [], relations: {} };
  }
  if (e.type === 'Company') {
    const k = keyOf(id); const p = PERIM[k];
    const relations = {};
    if (p) {
      relations.rivals = p.rivals.map(r => ref(co[r]));
      relations.investors = p.investors.map(([i]) => ref(inv[i]));
      relations.people = p.people.map(([x]) => ref(ppl[x], ppl[x].role));
    } else {
      const rivalOf = Object.entries(PERIM).filter(([, v]) => v.rivals.includes(k)).map(([pk]) => ref(co[pk]));
      relations.rivals = rivalOf;
    }
    return { id, name: e.name, type: 'Company', description: e.description, relations, facts: [
      { label: 'Headquarters', value: e.hq, sources: [cala('company profile')] },
      { label: 'Founded', value: e.founded, sources: [cala('company profile')] },
      { label: 'Industry', value: e.industry, sources: [cala('industry')] },
      { label: 'Website', value: e.website, sources: [web(e.website, 'https://' + e.website, null)] },
    ] };
  }
  if (e.type === 'Investor') {
    const portfolio = Object.entries(PERIM).filter(([, v]) => v.investors.some(([i]) => inv[i].id === id)).map(([k]) => ref(co[k]));
    return { id, name: e.name, type: 'Investor', description: `${e.sub} investor.`, facts: [{ label: 'Type', value: e.sub, sources: [cala('investor profile')] }, { label: 'Your companies', value: String(portfolio.filter(c => pf.ids.includes(c.id)).length), sources: [cala('investment')] }], relations: { portfolio } };
  }
  const companies = Object.entries(PERIM).filter(([, v]) => v.people.some(([x]) => ppl[x].id === id)).map(([k]) => ref(co[k]));
  return { id, name: e.name, type: 'Person', description: `${e.role}${companies[0] ? ' at ' + companies.map(c => c.name).join(' and ') : ''}.`, facts: [{ label: 'Role', value: e.role, sources: [cala('person', ago(30))] }], relations: { companies } };
}

function resolve(text) {
  const parts = String(text || '').split(/[\n,;]+/).map(s => s.trim()).filter(Boolean);
  const companies = Object.values(co);
  return {
    matches: parts.map(q => {
      const ql = q.toLowerCase().replace(/^https?:\/\/(www\.)?/, '').replace(/\/.*$/, '');
      if (/revolut/.test(ql)) {
        const a = { id: 'co-revolut', name: 'Revolut', description: 'Retail neobank and financial super-app.', website: 'revolut.com', hq: 'London', founded: '2015' };
        return { query: q, best: a, candidates: [a, companyPublic(co.revolut), { id: 'co-revolut-bank-uab', name: 'Revolut Bank UAB', description: 'Lithuanian-licensed banking entity of Revolut.', hq: 'Vilnius', founded: '2018' }] };
      }
      const hits = companies.filter(c => c.name.toLowerCase().includes(ql) || ql.includes(c.name.toLowerCase()) || (c.website && ql.includes(c.website)));
      return { query: q, best: hits[0] ? companyPublic(hits[0]) : null, candidates: hits.map(companyPublic) };
    }),
  };
}

function askAnswer(q) {
  return {
    answer_md: `**Short answer:** across your portfolio, the investors with the most exposure to direct rivals are **Tiger Global** and **Alkeon Capital**.\n\n- **Tiger Global** backs Qonto and GoCardless, and also holds Checkout.com, a rival of Mollie.\n- **Alkeon Capital** is in both Mollie and GoCardless, which Cala lists as direct competitors in European recurring payments.\n- **DST Global** and **Alven** back Qonto and Pennylane. Those two now overlap on SME business accounts.\n\n### Why it matters\nShared investors see board materials from both sides. Worth a note to founders before the next board meeting.\n\n_Based on ${'`'}funding round${'`'} and ${'`'}investment${'`'} records in Cala._`,
    sources: [cala('funding round', '2021-06-17'), cala('investment', '2022-01-10'), cala('competitor'), web('Crunchbase News', 'https://news.crunchbase.com/', '2022-01-10')],
    entities: [ref(inv.tiger), ref(inv.alkeon), ref(inv.dst), ref(inv.alven), ref(co.mollie), ref(co.gocardless)],
    seconds: 23.4,
  };
}

function draft(itemId) {
  const it = feed().items.find(i => i.id === itemId) || feed().items[0];
  const founder = { [co.mollie.id]: 'Shane', [co.qonto.id]: 'Alexandre', [co.pennylane.id]: 'Arthur', [co.gocardless.id]: 'Hiroki' }[it?.company?.id] || 'there';
  return {
    subject: `Heads-up: ${it?.title || 'something in your perimeter'}`,
    body: `Hi ${founder},\n\nQuick heads-up from our side. ${it?.title || ''}.\n\n${it?.body || ''}\n\nSources:\n${(it?.sources || []).map(s => `- ${s.name}${s.date ? ' (' + s.date + ')' : ''}${s.url ? ': ' + s.url : ''}`).join('\n')}\n\nNo action needed. Happy to talk it through if useful.\n\nBest,\n`,
  };
}

// ---------- check (SSE simulation) ----------
const STEPS = [
  ['match', 'Matching the company', q => `Matched “${q}” in Cala by name and website`],
  ['profile', 'Reading Cala profile', () => '38 facts'],
  ['people', 'Mapping people and owners', () => '6 people, 4 owners'],
  ['events', 'Reading corporate events', () => '12 events in the last 12 months'],
  ['rivals', 'Finding closest rivals', () => '5 rivals'],
  ['screen', 'Screening sanctions and news', () => '11 entities screened, 27 articles'],
];
function checkResult(q) {
  const k = keyOf(q) || Object.keys(co).find(x => co[x].name.toLowerCase() === String(q).toLowerCase()) || Object.keys(co).find(x => co[x].name.toLowerCase().includes(String(q).toLowerCase()));
  const c = k ? co[k] : C('co-' + String(q).toLowerCase().replace(/\W+/g, '-'), String(q).replace(/\b\w/g, m => m.toUpperCase()), 'Company profile from Cala.', null, 'Berlin', '2019', 'Software');
  const isAdyen = k === 'adyen';
  const rivalKeys = PERIM[k]?.rivals || Object.entries(PERIM).filter(([, v]) => v.rivals.includes(k)).map(([pk]) => pk).concat(['stripe', 'checkout']).filter(x => x !== k).slice(0, 4);
  const now = new Date();
  const lastYear = new Date(now); lastYear.setFullYear(now.getFullYear() - 1);
  const fmt = d => `${d.getDate()} ${d.toLocaleString('en-GB', { month: 'short' })} ${d.getFullYear()}`;
  return {
    company: { ...companyPublic(c), legal_name: isAdyen ? 'Adyen N.V.' : `${c.name} ${c.hq === 'Paris' ? 'SAS' : c.hq === 'London' ? 'Ltd' : 'B.V.'}`, lei: isAdyen ? '724500973ODKK3IFQ447' : null, industry: c.industry, tags: [c.industry, c.hq, `Founded ${c.founded}`].filter(Boolean) },
    checked_at: now.toISOString(), seconds: 38, period: `${fmt(lastYear)} – ${fmt(now)}`,
    counts: isAdyen ? { high: 1, medium: 1, low: 1 } : { high: 0, medium: 1, low: 1 },
    stats: { facts: 142, entities: 11 },
    findings: [
      isAdyen && { severity: 'high', status: 'confirmed', category: 'Regulatory event', title: 'Penalty from De Nederlandsche Bank over AML controls', body: 'Per the DNB public register. Adyen has said it is remediating.', sources: [web('DNB register', 'https://www.dnb.nl/en/sector-information/', ago(1)), cala('regulatory event', ago(1))] },
      { severity: 'medium', status: 'reported', category: 'Legal', title: 'Former merchant partner filed a claim over settlement delays', body: 'Per Financial Times. No outcome reported.', sources: [web('Financial Times', 'https://www.ft.com/', ago(40)), cala('news', ago(40)), cala('legal event', ago(39))] },
      { severity: 'low', status: 'reported', category: 'Regulatory', title: 'Licence application in a second market reported as delayed', body: 'Per Sifted.', sources: [web('Sifted', 'https://sifted.eu/', ago(80))] },
    ].filter(Boolean),
    sanctions: { clear: true, screened: 11, text: 'No matches for the company, its parent, 4 owners and 6 officers.', sources: [cala('sanctions')] },
    facts: [
      { label: 'Legal name', value: isAdyen ? 'Adyen N.V.' : `${c.name} ${c.hq === 'Paris' ? 'SAS' : 'Ltd'}`, sources: [cala('legal entity')] },
      { label: 'Registered in', value: { Amsterdam: 'Netherlands', Paris: 'France', London: 'United Kingdom', 'San Francisco': 'United States' }[c.hq] || 'Germany', sources: [cala('legal entity')] },
      { label: 'Headquarters', value: c.hq, sources: [cala('company profile')] },
      { label: 'Industry', value: c.industry, sources: [cala('industry')] },
      { label: 'Founded', value: c.founded, sources: [cala('company profile')] },
      { label: 'LEI', value: isAdyen ? '724500973ODKK3IFQ447' : '—', sources: isAdyen ? [web('GLEIF', 'https://search.gleif.org/', null)] : [] },
      { label: 'Website', value: c.website || '—', sources: c.website ? [web(c.website, 'https://' + c.website, null)] : [] },
    ],
    people: isAdyen
      ? [{ id: 'p-pieter-van-der-does', name: 'Pieter van der Does', role: 'Co-founder, Co-CEO' }, { id: 'p-ingo-uytdehaage', name: 'Ingo Uytdehaage', role: 'Co-CEO' }, { id: 'p-arnout-schuijff', name: 'Arnout Schuijff', role: 'Co-founder', note: 'Also an angel in 3 fintechs' }]
      : (PERIM[k]?.people || [['takeuchi']]).map(([x, sw]) => ({ id: ppl[x].id, name: ppl[x].name, role: ppl[x].role, ...(sw ? { note: `Also on ${sw.join(', ')}’s board` } : {}) })),
    ownership: isAdyen
      ? [{ id: 'inv-index', name: 'Index Ventures', note: 'Early investor' }, { id: 'inv-general-atlantic', name: 'General Atlantic', note: 'Also backs Mollie' }, { id: 'inv-iconiq', name: 'ICONIQ Growth' }]
      : (PERIM[k]?.investors || [['accel']]).map(([i, sw]) => ({ id: inv[i].id, name: inv[i].name, ...(sw ? { note: `Also backs ${sw.join(', ')}` } : {}) })),
    funding: isAdyen
      ? [{ date: '2018-06', label: 'IPO · Euronext Amsterdam', amount: '€947M', sources: [cala('IPO')] }, { date: '2014-12', label: 'Series C · General Atlantic', amount: '$250M', sources: [cala('funding round')] }, { date: '2011', label: 'Series A · Index Ventures', amount: '$16M', sources: [cala('funding round')] }]
      : [{ date: ago(200).slice(0, 7), label: 'Series C', amount: '€92M', sources: [cala('funding round')] }, { date: '2023', label: 'Series B', amount: '€50M', sources: [cala('funding round')] }, { date: '2021', label: 'Seed', amount: null, sources: [] }],
    rivals: rivalKeys.map(r => ({ id: co[r].id, name: co[r].name, sub: `${co[r].hq} · ${co[r].industry}`, in_portfolio: pf.ids.includes(co[r].id) })),
  };
}
export function checkStream(q, h) {
  let dead = false;
  (async () => {
    await sleep(300);
    if (/pebble|zzz|notfound/i.test(q)) {
      h.step?.({ key: 'match', label: 'Matching the company', status: 'running' });
      await sleep(1200); if (dead) return;
      h.step?.({ key: 'match', label: 'Matching the company', status: 'error', detail: 'No match' });
      h.error?.(`“${q}” isn’t in Cala.`); return;
    }
    const name = allEntities.get(q)?.name || q;
    for (const [key, label, det] of STEPS) {
      if (dead) return;
      h.step?.({ key, label, status: 'running' });
      await sleep(700 + Math.random() * 900);
      if (dead) return;
      h.step?.({ key, label, status: 'done', detail: det(name) });
    }
    await sleep(250);
    if (!dead) h.result?.(checkResult(q));
  })();
  return () => { dead = true; };
}

export async function handle(method, path, body) {
  await sleep(150 + Math.random() * 250);
  const p = path.replace(/\?.*$/, '');
  if (p === '/api/health') return { ok: true, cala: true };
  if (p === '/api/resolve') { await sleep(600); return resolve(body?.text); }
  if (p === '/api/portfolio' && method === 'GET') {
    const building = pf.buildUntil > Date.now();
    if (!building && pf.ids.length && !pf.built_at) { pf.built_at = new Date().toISOString(); save(pf); }
    return { companies: portfolioCompanies(), building, built_at: pf.built_at };
  }
  if (p === '/api/portfolio' && method === 'POST') { startBuild(body.ids || []); return { ok: true }; }
  if (p === '/api/rebuild') { startBuild(pf.ids); return { ok: true }; }
  if (p === '/api/portfolio/demo') { startBuild(PORTFOLIO_KEYS.map(k => co[k].id)); return { ok: true }; }
  if (p === '/api/perimeter') return perimeter();
  if (p === '/api/feed') return feed();
  if (p === '/api/ask') { await sleep(9000); return askAnswer(body?.q); }
  if (p === '/api/draft') { await sleep(1400); return draft(body?.item_id); }
  if (p.startsWith('/api/entity/')) { await sleep(300); return entity(decodeURIComponent(p.slice(12))); }
  const e = new Error('Not found'); e.status = 404; throw e;
}

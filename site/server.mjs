// Plumb demo control server: the deck's only backend. Bound to 127.0.0.1; it runs a fixed list of actions, never a shell.
//
// GET  /api/health            which local services answer (Plumb API, AP4M merchant and gateway)
// POST /api/services/start    start the Plumb API and the AP4M merchant if they are down
// POST /api/bazaar            {need}: the Coinbase Bazaar's live XRPL ranking, with vet402's purchase record per host
// POST /api/recommend         {need, max_price?, assets?, principal?, k?}: Plumb's router directly (no payment)
// POST /api/ledger/account    {address}: live XRPL state through Quicknode -> the assets the account can pay with
// POST /api/agent/run         {per_purchase, cap, needs[]}: the AP4M buyer agent on testnet (one run at a time)
// GET  /api/agent/stream      ?run=: the run's control trail as server-sent events
// GET  /api/trail             ?run=|latest: a finished trail (the fallback replay)
//
// Secrets stay here: the Quicknode URL (env/ledger.env) is used server-side only; agent keys stay in the agent process.
import { spawn } from 'node:child_process';
import { existsSync, openSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { parse as toml } from 'smol-toml';

const ROOT = new URL('../', import.meta.url).pathname;
const CFG = toml(readFileSync(`${ROOT}config/plumb.toml`, 'utf8'));
const PORT = 8410;
const PLUMB_API = 'http://127.0.0.1:8402/v1/shortlist';
const MERCHANT = 'http://127.0.0.1:8403/resource';
const GATEWAY = 'http://127.0.0.1:8404/shortlist';
const TRAILS = `${ROOT}out/ap4m-agent/`;
const AMOUNT = /^\d{1,6}(\.\d{1,18})?$/;
const XRPL_ADDR = /^r[1-9A-HJ-NP-Za-km-z]{24,34}$/;
const RUN_ID = /^[a-z0-9-]{1,40}$/;

const log = (event, data = {}) => console.log(JSON.stringify({ at: new Date().toISOString(), event, ...data }));
const quicknode = (() => {
  const file = `${ROOT}env/ledger.env`;
  const line = existsSync(file) && readFileSync(file, 'utf8').split('\n').find((l) => l.startsWith('QUICKNODE_HTTP_URL='));
  return line ? line.slice(line.indexOf('=') + 1).trim().replace(/^"|"$/g, '') : null;
})();

// vet402's public XRPL purchase record, per host: how often a paid attempt actually settled (EVIDENCE E2).
const vet402 = (() => {
  const [head, ...rows] = readFileSync(`${ROOT}data/vet402_xrpl.csv`, 'utf8').trim().split('\n');
  const cols = head.split(','), key = cols.indexOf('resource_key'), status = cols.indexOf('status');
  const out = {};
  for (const r of rows) {
    const c = r.split(','), host = c[key].split('/')[0];
    out[host] ??= { attempts: 0, settled: 0 };
    out[host].attempts += 1;
    out[host].settled += c[status] === 'settled' ? 1 : 0;
  }
  return out;
})();

class BadRequest extends Error {}

function send(res, code, body) {
  const s = JSON.stringify(body);
  res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(s) });
  res.end(s);
}

async function readJson(req) {
  let body = '';
  for await (const chunk of req) { body += chunk; if (body.length > 16384) throw new BadRequest('body too large'); }
  try { return body ? JSON.parse(body) : {}; } catch { throw new BadRequest('invalid JSON'); }
}

function need(v) {
  const s = String(v ?? '').trim();
  if (!s || s.length > 300) throw new BadRequest('need is required (at most 300 characters)');
  return s;
}

function amount(v, name) {
  const s = String(v ?? '');
  if (!AMOUNT.test(s)) throw new BadRequest(`${name} must be a decimal RLUSD amount`);
  return s;
}

async function up(url, init) {
  try { await fetch(url, { ...init, signal: AbortSignal.timeout(1500) }); return true; } catch { return false; }
}

async function health() {
  const [plumb, merchant, gateway] = await Promise.all([
    up(PLUMB_API, { method: 'POST', body: '{}' }), up(MERCHANT), up(GATEWAY, { method: 'POST', body: '{}' })]);
  return { plumb_api: plumb, ap4m_merchant: merchant, ap4m_gateway: gateway, quicknode: Boolean(quicknode), agent_running: Boolean(run) };
}

const children = {};
function startOnce(name, cmd, args, cwd) {
  if (children[name] && children[name].exitCode === null) return false;
  const out = openSync(`${ROOT}out/${name}.log`, 'a');
  children[name] = spawn(cmd, args, { cwd, stdio: ['ignore', out, out] });
  log('started', { name, pid: children[name].pid });
  return true;
}

async function startServices() {
  const h = await health();
  if (!h.plumb_api) startOnce('plumb-api', 'uv', ['run', 'python', '-m', 'plumb.api'], ROOT);
  if (!h.ap4m_merchant) startOnce('ap4m-merchant', 'node', ['merchant.mjs'], `${ROOT}ap4m`);
  for (let i = 0; i < 40; i++) {
    const now = await health();
    if (now.plumb_api && now.ap4m_merchant && now.ap4m_gateway) return now;
    await new Promise((r) => setTimeout(r, 1000));
  }
  return health();
}

async function bazaar(body) {
  const url = new URL(`${CFG.bazaar.base}/search`);
  url.search = new URLSearchParams({ query: need(body.need), network: CFG.xrpl.network, limit: '5' }).toString();
  const r = await fetch(url, { signal: AbortSignal.timeout(20000) });
  if (!r.ok) throw new Error(`Bazaar search failed (HTTP ${r.status})`);
  const items = (await r.json()).resources ?? [];
  return items.map((x, i) => {
    const host = String(x.resource).replace(/^https?:\/\//, '').split('/')[0];
    const opt = (x.accepts ?? []).find((a) => a.network === CFG.xrpl.network) ?? {};
    return { rank: i + 1, url: x.resource, host, service: String(x.serviceName ?? '').slice(0, 80), pay_to: opt.payTo,
             asset: opt.asset === 'XRP' ? 'XRP' : 'RLUSD', amount: opt.amount, calls_30d: x.quality?.l30DaysTotalCalls ?? null,
             vet402: vet402[host] ?? null };
  });
}

async function recommend(body) {
  const constraints = {};
  if (body.max_price !== undefined && body.max_price !== '') constraints.max_price = amount(body.max_price, 'max_price');
  if (body.assets !== undefined) {
    if (!Array.isArray(body.assets) || !body.assets.every((a) => a === 'XRP' || a === 'RLUSD')) throw new BadRequest('assets must be XRP and/or RLUSD');
    constraints.assets = body.assets;
  }
  if (body.principal !== undefined && body.principal !== '' && !XRPL_ADDR.test(body.principal)) throw new BadRequest('principal must be an XRPL address');
  const k = Math.max(1, Math.min(Number(body.k) || 3, 5));
  const r = await fetch(PLUMB_API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(60000),
    body: JSON.stringify({ need: need(body.need), k, principal: body.principal || undefined, constraints }) });
  return r.json();
}

async function xrpl(method, params) {
  if (!quicknode) throw new Error('no Quicknode URL in env/ledger.env');
  const r = await fetch(quicknode, { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: AbortSignal.timeout(15000),
    body: JSON.stringify({ method, params: [{ ...params, ledger_index: 'validated' }] }) });
  return (await r.json()).result;
}

async function account(body) {
  const address = String(body.address ?? '');
  if (!XRPL_ADDR.test(address)) throw new BadRequest('address must be an XRPL classic address');
  const t0 = performance.now();
  const [info, lines] = await Promise.all([xrpl('account_info', { account: address }), xrpl('account_lines', { account: address })]);
  if (info?.error) throw new BadRequest(`ledger: ${info.error}`);
  const rl = (lines?.lines ?? []).find((l) => l.currency === CFG.xrpl.rlusd_currency && l.account === CFG.xrpl.rlusd_issuer);
  return {
    address, ledger_index: info.ledger_index, ms: Math.round(performance.now() - t0), source: 'Quicknode (full-history XRPL)',
    xrp: (Number(info.account_data.Balance) / 1e6).toFixed(6), rlusd_trust_line: Boolean(rl), rlusd_balance: rl?.balance ?? null,
    assets: rl ? ['RLUSD', 'XRP'] : ['XRP'],
  };
}

let run = null;  // the one agent run allowed at a time
function agentRun(body) {
  if (run) throw new BadRequest(`agent run ${run.id} is still going`);
  const perPurchase = amount(body.per_purchase ?? '0.05', 'per_purchase');
  const cap = amount(body.cap ?? '0.005', 'cap');
  const needs = (Array.isArray(body.needs) ? body.needs : []).slice(0, 4).map(need);
  if (!needs.length) throw new BadRequest('needs must list 1-4 needs');
  const id = `run-${Date.now().toString(36)}`;
  const child = spawn('node', ['agent.mjs', ...needs], {
    cwd: `${ROOT}ap4m`, stdio: ['ignore', 'ignore', 'pipe'],
    env: { ...process.env, PLUMB_NEW_CHANNEL: '1', PLUMB_CHANNEL_CAP: cap, PLUMB_MAX_PER_PURCHASE: perPurchase, PLUMB_RUN_ID: id },
  });
  let err = '';
  child.stderr.on('data', (d) => { err = (err + d).slice(-2000); });
  run = { id, child };
  child.on('exit', (code) => {
    log('agent_exit', { id, code });
    const message = err.split('\n').find((l) => /Error|error:/.test(l)) ?? err.split('\n').filter(Boolean).slice(-1)[0];
    if (code) appendTrail(id, { event: 'error', reason: (message || `exit ${code}`).trim().slice(0, 400) });
    run = null;
  });
  log('agent_start', { id, perPurchase, cap, needs: needs.length });
  return { run: id };
}

function appendTrail(id, ev) {
  import('node:fs').then(({ appendFileSync }) => appendFileSync(`${TRAILS}trail-${id}.jsonl`, JSON.stringify({ at: new Date().toISOString(), run: id, ...ev }) + '\n'));
}

function trailPath(id) {
  if (id === 'latest') {
    const files = existsSync(TRAILS) ? readdirSync(TRAILS).filter((f) => f.startsWith('trail-')) : [];
    const f = files.sort((a, b) => statSync(TRAILS + b).mtimeMs - statSync(TRAILS + a).mtimeMs)[0];
    return f ? TRAILS + f : null;
  }
  if (!RUN_ID.test(id)) throw new BadRequest('bad run id');
  return `${TRAILS}trail-${id}.jsonl`;
}

const readTrail = (path) => (path && existsSync(path) ? readFileSync(path, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l)) : []);

function stream(req, res, id) {
  const path = trailPath(id);
  res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
  let sent = 0;
  const tick = setInterval(() => {
    const events = readTrail(path);
    for (; sent < events.length; sent++) res.write(`data: ${JSON.stringify(events[sent])}\n\n`);
    const last = events[events.length - 1];
    if (last && (last.event === 'done' || last.event === 'error') && !(run && run.id === id)) {
      res.write('event: end\ndata: {}\n\n');
      clearInterval(tick);
      res.end();
    }
  }, 500);
  req.on('close', () => clearInterval(tick));
}

const routes = {
  'GET /api/health': () => health(),
  'POST /api/services/start': () => startServices(),
  'POST /api/bazaar': (b) => bazaar(b),
  'POST /api/recommend': (b) => recommend(b),
  'POST /api/ledger/account': (b) => account(b),
  'POST /api/agent/run': (b) => agentRun(b),
};

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  try {
    if (req.method === 'GET' && url.pathname === '/api/agent/stream') return stream(req, res, url.searchParams.get('run') ?? '');
    if (req.method === 'GET' && url.pathname === '/api/trail') {
      const path = trailPath(url.searchParams.get('run') ?? 'latest');
      return send(res, 200, { run: path?.match(/trail-(.+)\.jsonl$/)?.[1] ?? null, events: readTrail(path) });
    }
    const handler = routes[`${req.method} ${url.pathname}`];
    if (!handler) return send(res, 404, { error: 'not_found' });
    const body = req.method === 'POST' ? await readJson(req) : {};
    send(res, 200, await handler(body));
  } catch (e) {
    const bad = e instanceof BadRequest;
    log('error', { path: url.pathname, message: e.message });
    send(res, bad ? 400 : 502, { error: e.message });
  }
}).listen(PORT, '127.0.0.1', () => log('listening', { url: `http://127.0.0.1:${PORT}` }));

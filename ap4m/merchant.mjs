// Plumb's AP4M merchant (SPEC §5b): sells one "shortlist credit" per x402 payment, then redeems it once for a shortlist.
//
// AP4M's createX402Merchant serves a single fixed-price resource at GET /resource, so the paid resource is a credit,
// and POST /shortlist (gateway) answers a need only for a payment this merchant redeemed on-chain itself:
// it looks the redemption tx up in the merchant's own store, marks it consumed, and forwards to Plumb's local API.
import { createServer } from 'node:http';
import { DatabaseSync } from 'node:sqlite';
import { ethers } from 'ethers';
import { createX402Merchant, loadX402Context } from './ap4m-x402.mjs';
import { AP4M, env } from './env.mjs';

const state = new URL('../out/ap4m-merchant/', import.meta.url).pathname;
const provider = new ethers.JsonRpcProvider(AP4M.rpc);
const submitter = new ethers.Wallet(env.MERCHANT_SUBMITTER_KEY, provider);
const context = await loadX402Context(AP4M.api);
const resourceUrl = `http://localhost:${AP4M.merchantPort}/resource`;

const merchant = createX402Merchant({
  context, provider, submitter, stateDirectory: state, resourceUrl,
  merchantParticipantId: env.MERCHANT_ID,
  payout: env.MERCHANT_PAYOUT_ADDRESS,
  amount: ethers.parseUnits(AP4M.feeRlusd, 18).toString(),
  content: { product: 'plumb.shortlist-credit', redeem: `POST http://localhost:${AP4M.gatewayPort}/shortlist`, price_rlusd: AP4M.feeRlusd },
});
merchant.server.listen(AP4M.merchantPort, '127.0.0.1');

const store = new DatabaseSync(`${state}merchant.sqlite`, { readOnly: true });
const used = new DatabaseSync(`${state}../ap4m-gateway.sqlite`);
used.exec('CREATE TABLE IF NOT EXISTS consumed (tx TEXT PRIMARY KEY, at TEXT NOT NULL) STRICT');

function send(res, code, body) {
  const s = JSON.stringify(body);
  res.writeHead(code, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(s) });
  res.end(s);
}

createServer(async (req, res) => {
  if (req.method !== 'POST' || req.url !== '/shortlist') return send(res, 404, { error: 'not_found' });
  let body = '';
  for await (const chunk of req) { body += chunk; if (body.length > 16384) return send(res, 413, { error: 'too_large' }); }
  let q;
  try { q = JSON.parse(body); } catch { return send(res, 400, { error: 'invalid_json' }); }
  const tx = String(q.paid_tx || '');
  if (!/^0x[0-9a-f]{64}$/.test(tx)) return send(res, 402, { error: 'payment_required', pay: resourceUrl });
  const paid = store.prepare('SELECT value FROM payments WHERE complete = 1').all()
    .some((r) => JSON.parse(String(r.value)).transactionHash === tx);
  if (!paid) return send(res, 402, { error: 'unknown_or_unconfirmed_payment' });
  const first = used.prepare('INSERT OR IGNORE INTO consumed VALUES (?, ?)').run(tx, new Date().toISOString()).changes === 1;
  // A replayed credit is forwarded too: Plumb's API returns the stored shortlist for a known paid_tx, never a new one.
  const r = await fetch(AP4M.plumbApi, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ need: q.need, k: q.k, principal: q.principal, constraints: q.constraints, paid_tx: tx }) });
  send(res, r.status, { ...(await r.json()), credit_first_use: first });
}).listen(AP4M.gatewayPort, '127.0.0.1');

console.log(JSON.stringify({ merchant: resourceUrl, gateway: `http://localhost:${AP4M.gatewayPort}/shortlist`, fee_rlusd: AP4M.feeRlusd }));

// A customer's agent paying Plumb through Mastercard AP4M (SPEC §5b): open a capped channel, buy a shortlist credit
// per need over x402, redeem it for Plumb's top-3, then show an over-cap purchase being refused and settle.
//
// Usage: node agent.mjs "<need>" ["<need>" ...]   (default: three frozen needs; the channel cap allows two)
import sdk from './ap4m-hackathon-sdk.cjs';
import { ethers } from 'ethers';
import { buyResource, loadX402Context } from './ap4m-x402.mjs';
import { AP4M, env } from './env.mjs';

const CAP_RLUSD = process.env.PLUMB_CHANNEL_CAP ?? '0.005';   // two 0.002 shortlists fit; the third must be refused
const needs = process.argv.slice(2).length ? process.argv.slice(2) : [
  'Current XRP price in USD',
  'Current BTC perpetual futures funding rate on major exchanges',
  'Current weather and 3-day forecast for New York City',
];
const log = (event, data = {}) => console.log(JSON.stringify({ at: new Date().toISOString(), event, ...data }));

const provider = new ethers.JsonRpcProvider(AP4M.rpc);
const wallet = new ethers.Wallet(env.AGENT_SIGNING_KEY || env.FUNDING_PRIVATE_KEY, provider); // portal registered the funding wallet as Agent
const session = await sdk.signIn(AP4M.api, AP4M.team, wallet);
log('signed_in', { team: session.team.team_name, agent: wallet.address, budget_rlusd: session.team.rlusd_allocation });

let channel = (await sdk.listChannels(AP4M.api, session.token)).find((c) => c.channel_status === 'open');
if (!channel) {
  channel = await sdk.requestChannel(AP4M.api, session.token, wallet, { capRlusd: CAP_RLUSD });
}
log('channel_open', { channel_id: channel.channel_id, cap_rlusd: ethers.formatUnits(channel.cap_wei, 18), merchant: channel.merchant_id });

const context = await loadX402Context(AP4M.api);
const resourceUrl = `http://localhost:${AP4M.merchantPort}/resource`;
const runId = Date.now().toString(36);
const fee = ethers.parseUnits(AP4M.feeRlusd, 18);
// Start from what the channel has already redeemed on-chain, so a reused channel is judged correctly.
let spent = (await sdk.getChannelState(provider, context.participantRequest.ledger, channel.channel_id)).redeemed;
for (const [i, need] of needs.entries()) {
  // The agent's own pay/no-pay decision: never sign a voucher that would push the channel past its cap.
  if (spent + fee > BigInt(channel.cap_wei)) {
    log('refused_over_cap', { need, spent_rlusd: ethers.formatUnits(spent, 18), fee_rlusd: AP4M.feeRlusd, cap_rlusd: ethers.formatUnits(channel.cap_wei, 18) });
    continue;
  }
  try {
    const bought = await buyResource({
      context, provider, wallet, stateDirectory: new URL(`../out/ap4m-agent/`, import.meta.url).pathname,
      resourceUrl, channelId: channel.channel_id, maximumAmount: ethers.parseUnits(AP4M.feeRlusd, 18).toString(),
      operation: `shortlist-${runId}-${i}`,
    });
    spent += fee;
    log('paid', { need, voucher_redeemed_tx: bought.transactionHash, claim_id: bought.claimId });
    const r = await fetch(`http://localhost:${AP4M.gatewayPort}/shortlist`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ need, paid_tx: bought.transactionHash, principal: process.env.PLUMB_PRINCIPAL }) });
    const out = await r.json();
    log('shortlist', { need, status: r.status, top: (out.results ?? []).map((x) => `${x.rank}. ${x.url} (${x.price.asset} ${x.price.amount_rlusd})`) });
  } catch (error) {
    log('refused', { need, reason: error.message }); // the over-cap purchase lands here: the signed voucher would exceed the channel cap
  }
}

const settled = await sdk.settle(AP4M.api, session.token, channel.channel_id);
log('settled', { receipt_url: settled.receipt_url, claim_paid_tx: settled.claim_paid_tx, settlement_recorded_tx: settled.settlement_recorded_tx });

// Shared settings for the AP4M shim and agent. Keys come only from ../env/ap4m.env (never printed or sent anywhere).
import { readFileSync } from 'node:fs';

const file = new URL('../env/ap4m.env', import.meta.url);
export const env = Object.fromEntries(readFileSync(file, 'utf8').split('\n')
  .filter((l) => l.includes('=') && !l.trimStart().startsWith('#'))
  .map((l) => [l.slice(0, l.indexOf('=')).trim(), l.slice(l.indexOf('=') + 1).trim().replace(/^"|"$/g, '')]));

// Protocol settings (config, not secrets). Mirrors SPEC §5b / AGENTS.md rule 9.
export const AP4M = {
  api: env.AP4M_API_URL || 'https://hackathon.ap4m.build',
  rpc: 'https://rpc.testnet.xrplevm.org',
  team: 'Plumb',
  feeRlusd: '0.002',        // Plumb's price per shortlist
  merchantPort: 8403,       // x402 merchant: GET /resource sells one shortlist credit
  gatewayPort: 8404,        // POST /shortlist: answers once per credit the merchant itself redeemed
  plumbApi: 'http://127.0.0.1:8402/v1/shortlist',
  explorer: 'https://explorer.testnet.xrplevm.org',   // AP4M receipts (XRPL EVM testnet)
  xrplExplorer: 'https://livenet.xrpl.org/transactions', // merchants' ledger evidence (XRPL mainnet)
};

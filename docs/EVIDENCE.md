# Evidence behind Plumb (measured and sourced, 2026-10-24)

**Tags:**
- **[measured]**: we ran it ourselves. The scripts are in `research/`.
- **[verified]**: read on the source page.
- **[unverified]**: comes from a single secondary source.

## The market and the gap
| # | Finding | Number | Tag / source |
|---|---|---|---|
| E1 | The Bazaar's "quality" score (the main x402 catalog) measures probing, not buying | For the same XRPL `payTo` over 30 days, Bazaar `l30DaysTotalCalls` against x402 payments that actually settled on-ledger: `rDxNZ…` **2,398 vs 8**, `rEac5…` **2,270 vs 12**, `rMnHeu…` **1,170 vs 130**, `r9xmB…` **94 vs 20**. Every endpoint of the large merchants shows calls, with at most 7–10 unique payers | [measured] Bazaar `/discovery/merchant` + ledger scan (`research/s1/p2_collect.py`) |
| E2 | XRPL purchases often deliver nothing usable | **64 of 202** attempts (32%) gave a 2xx response matching the advertised schema. `pay.edge-agents.ai` went **0 for 88** (never settled), and `api.vextorium.com` went **7 for 7**. Of the **3.91 RLUSD** spent on settled purchases, **2.18 RLUSD (56%)** bought unusable results, ≈0.034 RLUSD wasted per usable answer. Median price is 0.01 RLUSD; the mean is 0.031 | [measured] `research/vet402/xrpl_outcomes.py` (amounts assume 6-decimal units) |
| E3 | The same holds across chains | **55%** of 11,554 paid-call attempts were usable. Per seller: median 58%, bottom tenth 16% or less, top tenth 91% or more | [measured] vet402 export |
| E4 | XRPL "agent payment" volume is inflated by a bot farm | In 150 ledgers (~10 min), **46 x402 payments from 46 senders**, all created between **2026-08-25 05:12 and 05:16 UTC**, each with ≥1,196 x402 payments of about 0.003 RLUSD | [measured] `research/s1/p4_ledgerscan.py`, `p5_parents.py` |
| E5 | The live rate is far below the published claims | About **6.8k a day (~0.2M per 30 days)** against a claimed **8M per 30 days** (Oct 8). The sample is short | [measured]; claim from [KuCoin](https://www.kucoin.com/news/flash/xrp-ledger-processes-8m-x402-payments-in-30-days-as-ai-activity-grows) |
| E6 | Funding parents alone don't reveal owners | Every farm sender was funded directly from Binance hot wallets. **Creation-time batching** is the signal that survives | [measured] `p6_roots.py` |
| E7 | The market is concentrated | About **2,500 listings** sit under 4 `payTo` accounts (1,078 + 946 + 451 + 18), from roughly 10 independent operators. One operator runs about 45 "pulse" hosts | [measured] Bazaar merchant API, vet402 hosts |
| E8 | Average ticket size is tiny | x402 overall: about **$0.14–0.22** per payment (Visa/Artemis-adjusted). XRPL: about **0.003 RLUSD** | [verified, secondary] [Defiant](https://thedefiant.io/news/infrastructure/visa-s-sheffield-pegs-adjusted-x402-volume-at-19m); [measured] |

## Incumbents and why they leave the gap open
- **Bazaar search:** returns at most 20 results, ranked by relevance blended with "quality", meaning call volume, unique payers and metadata completeness. The quality signal is inflated (E1). [verified, CDP docs]
- **vet402:** runs paid test purchases and gives verdicts on endpoints through an API, SDK and MCP tool. It added XRPL in Sep 2026. It *observes*; it doesn't rank for a specific query or route purchases. [verified, x402 #3527]
- **Agent402:** a router that ranks by **volume settled** (gameable) and charges $0.55 for each external call. [self-reported]
- **AWS AgentCore tool search:** narrows tools semantically, but its ranking can't be customised. [verified, Strands docs]

## Protocol facts we rely on
- **How to spot an x402 payment on XRPL:** every t54-settled payment is a `Payment` with **SourceTag `804681468`** and `InvoiceID = SHA-256(invoiceId)`, with no memos. [measured, 90/90]
- **The t54 facilitator:**
  - URLs: mainnet `https://xrpl-facilitator-mainnet.t54.ai`, testnet `https://xrpl-facilitator-testnet.t54.ai`.
  - Endpoints: `/supported`, `/verify`, `/settle`.
  - Its payload needs `{signedTxBlob, invoiceId}`.
  - It accepts **multisig payers** at `/verify`. [measured]
- **The ledger names the merchant account, not the endpoint.** A payment carries `payTo`, so endpoint-level quality has to come from purchases, not from the ledger. [inferred from the payment shape]
- **RLUSD:** currency `524C555344000000000000000000000000000000`, issuer `rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De` (domain ripple.com, clawback enabled). [measured]

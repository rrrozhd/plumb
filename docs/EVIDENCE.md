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
| E9 | Realistic needs reach several XRPL operators, so ranking across operators is possible | All **20 of 20** frozen eval needs have **2–6** distinct XRPL `payTo` in the Bazaar's top 20 (median **4**) | [measured] `research/u0/p2_diversity.py` (U0) |
| E10 | Without the XRPL filter, the Bazaar's search buries XRPL listings | Only **0–6 of the top 20** are XRPL, across 8 generic queries and the 20 eval needs. With `network=xrpl:0`, every result is XRPL | [measured] `research/u0/p1_bazaar.py`, `p2_diversity.py` (U0) |
| E11 | A fifth of the XRPL catalogue sits outside t54's SourceTag | **3,207 XRPL listings under 15 `payTo`**. **637 (20%)** offer no option with SourceTag `804681468`, including all **587** of `pay.edge-agents.ai`'s (tag `402402402`) | [measured] `research/u0/p1_bazaar.py` (U0) |
| E12 | The storefront that went 0 for 88 has never been paid on-ledger | `pay.edge-agents.ai`'s `payTo` received **20 payments** (2026-03-02 to 10-03), **none** with an InvoiceID or SourceTag, so no x402 sale. It is still the Bazaar's **#1** XRPL result for one eval need and in the top 20 for **7** | [measured] `research/u0/p1b_payto_tags.py`, `p2_diversity.py` (U0); backs up E2 |
| E13 | The live tagged flow on XRPL doesn't reach the Bazaar's merchants | In two 10-minute captures of the live stream, **0 of 100** t54-tagged payments went to a Bazaar-listed `payTo`. **64** came from E4's farm senders and **94** went to the farm's receivers | [measured] `research/u0/p3_feed.py`, `p3b_xref.py` (U0) |
| E14 | The Bazaar's top XRPL pick often sits outside t54's tag or RLUSD | For **10 of 20** eval needs, the #1 XRPL result advertises a non-t54 SourceTag or none. For **6**, it accepts XRP only | [measured] `research/u0/p2_diversity.py` (U0) |

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
- **The InvoiceID hash, with public preimages:** `InvoiceID = SHA-256(UTF-8 invoiceId)`, in uppercase hex. [measured, U0 `research/u0/xb_invoice_preimage.py`]
  - fizzl.eu uses static invoiceIds of the form `"<host> <METHOD> <path>"`. 8 of them match the InvoiceID of **18** validated payments. For a seller like this, the InvoiceID names the endpoint on-ledger.
  - 5 other operators issue a fresh invoiceId on every 402 challenge.
  - vet402's export carries no invoiceId.
- **The live `transactions` stream** on a public server delivers tagged payments a median **2.8–4.3 s** (p95 **≤ 7 s**) after ledger close, all validated. Each 10-minute capture **dropped once**, losing 2 of 54 and 3 of 51 tagged payments; a ledger rescan recovered them. [measured, U0 `research/u0/p3_feed.py`]
- **An account's starting `Sequence` is the index of the ledger that created it** (5 of 5 farm senders). `account_info` returns the start plus every transaction sent since, which overshoots the farm senders by about **110k ledgers (~5 days)**. [measured, U0 `research/u0/xa_account_dates.py`]
- **The Bazaar API:** [measured, U0 `research/u0/p1_bazaar.py`]
  - `GET …/discovery/search?query=&network=xrpl:0&limit=` filters by network on the server and returns at most 20 results;
  - the list endpoint `…/discovery/resources` ignores `network`;
  - in `accepts[]`, an RLUSD `amount` is a decimal string and an XRP `amount` is integer drops.

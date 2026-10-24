# Plumb: the trust layer that tells AI agents which XRPL merchant to pay

> **One line:** an agent asks Plumb what it needs. It gets back the three XRPL merchants most likely to deliver, ranked by trust scores built from what actually happened on the ledger. It pays a fraction of a cent for the answer and stops paying for failures.

Track: **Agentic Finance**. Stack: **XRPL** (payments, settlement truth, fees) · **Quicknode** (live ledger data) · **AWS** (Bedrock relevance model, served as an AgentCore Gateway tool) · Mastercard (later, for card merchants).

---

## 1. The problem, measured (2026-10-24, public data plus our own mainnet probes)

| What we found | Number | Source |
|---|---|---|
| Agents searching for a seller get rankings that measure *probing*, not *buying* | The Bazaar's quality score ("calls in 30 days") runs **5–300×** the payments that actually settled on XRPL for the same merchants, e.g. **2,398 "calls" against 8 real payments** | Bazaar public API vs XRPL ledger, `docs/EVIDENCE.md` |
| Paying an XRPL merchant often gets you nothing | Only **64 of 202 (32%)** real purchase attempts on XRPL produced usable output. The busiest storefront went **0 for 88**, while others went 7 for 7 | vet402's public purchase log, XRPL rows |
| Headline volume is inflated by bots | **46 payer accounts created within 4 minutes**, each with **1,196 or more** tiny payments. The live rate is about 6.8k payments a day, against a published claim of 8M a month | our ledger scan, `research/s1` |
| Agents can't read the whole market | About **2,500 listings** sit behind roughly 10 independent XRPL operators, far more than fits in a context window | Bazaar merchant API |

**The cost to the user, on XRPL:** vet402 paid **3.91 RLUSD** for settled XRPL purchases, and **2.18 RLUSD (56%) bought unusable results**. That's **≈0.034 RLUSD wasted per usable answer**, against a median price of 0.01 RLUSD (`research/vet402/xrpl_outcomes.py`). On top of that come the tokens spent comparing listings, roughly $0.02 per search at today's prices (estimated), and the retries.

## 2. The product
**Plumb** is middleware between any agent and the XRPL x402 market.

1. **Ask.** The agent sends a plain-language need ("BTC funding rates, JSON, under 0.05 RLUSD") to Plumb's endpoint. Plumb is itself an x402 seller on XRPL, and **the agent pays about 0.002 RLUSD per answer**.
2. **Plumb.** We return **three merchants and endpoints**, each with:
   - its trust score;
   - expected price;
   - why we picked it;
   - ledger evidence (transaction hashes).

   Our trust is scored per endpoint and rolled up per operator.
3. **Learn.** Every routed purchase, and whether it worked, flows back into the scores. The more agents use it, the better it ranks.

### The Plumb Trust Score (ours)
A probability, not a count: **"if you pay this endpoint now, how likely are you to get a usable answer?"** Each endpoint has a Bayesian estimate, starting from its operator's track record and fading old evidence, fed by:

| Signal | How we measure it | Why it can't be gamed easily |
|---|---|---|
| **Settled purchases** | x402 payments on XRPL, identified by t54's SourceTag `804681468` and the `InvoiceID`, streamed live from **Quicknode** | It costs real money and is final on the ledger, unlike "calls" |
| **Independent payers** | distinct payers, with accounts **created in the same batch counted as one** (the farm signature we found) | farms collapse to a single payer |
| **Delivery quality** | our own small audit purchases: did it answer with a 2xx, match the advertised schema, and actually answer? | we pay, so we see what agents see |
| **Will it settle** | a pre-payment check: trust line, reserve, destination tag, facilitator format | catches the "0 for 88" storefronts before anyone pays |
| **Price honesty** | the price at payment time against the listing | penalises bait-and-switch |

### The recommendation
**Rank = expected cost per good answer = price ÷ (relevance × trust × will-it-settle).**
- **Relevance** comes from an LLM judge (Claude on **Bedrock**) that reads each listing's description, schema and example.
- We give a small share of traffic to new merchants, so the market doesn't freeze.

## 3. Why this is a business, not a tool
- **Customers:** anyone running buying agents.
- **Unit economics:**
  - We charge about 0.002 RLUSD per answer.
  - The user saves the wasted purchases (≈0.034 RLUSD per usable answer on XRPL) plus the tokens spent comparing listings. **Our fee is about 6% of the waste it removes.**
  - We're paid once per question; they save on every purchase they no longer waste.
- **Moat:**
  1. **Outcome data** that only accumulates through routed, paid, checked purchases.
  2. **Scores bound to the ledger**, which buyers can audit and fake volume can't buy.
  3. **Distribution:** once agents call Plumb first, merchants care about their score and fix their endpoints, which makes the market better.
- **Next step after the hackathon:** "pay on success". Agents pay merchants through an XRPL payment channel only after the answer checks out, and Plumb settles the channel.

## 4. Why XRPL, Quicknode and AWS are load-bearing
- **XRPL:** every x402 payment is identifiable on-ledger (SourceTag plus InvoiceID). Settlement is final in 3–5 s for fractions of a cent, and account creation reveals bot batches. Plumb itself is paid in RLUSD.
- **Quicknode:** a live feed of ledger data for scoring, plus full-history reads for the evidence behind each score.
- **AWS:** Bedrock runs the relevance judge. Plumb is served as an **AgentCore Gateway tool**, so any AgentCore agent gets trusted plumbs. (AgentCore's built-in tool search can't take custom ranking signals; we add trust.)

## 5. Demo (3 minutes)
1. **The problem, live (30 s).** Bazaar search for an XRPL data need. The top results include storefronts our evidence shows rarely deliver.
2. **Plumb, live (60 s).** The same query returns three picks, with their scores and ledger evidence on screen. The agent pays 0.002 RLUSD for the plumb, then buys the top pick on XRPL and gets a good answer.
3. **Head to head (60 s).** 20 queries each way, real purchases on mainnet (a few dollars in total). **Cost per good answer: Bazaar's top pick vs Plumb's top pick.**
4. **Why it holds (30 s).** The bot farm (46 accounts, 4 minutes) and the 300× "calls vs payments" gap explain why ranking by volume fails and outcome-based trust doesn't.

## 6. What we're deliberately not doing (yet)
- Card merchants (Mastercard), until their sandbox access is confirmed.
- Merchants on other chains.
- Pay-on-success channels (roadmap).
- Staking or slashing.
- A consumer app.

## 7. Risks, stated plainly
- **Small market:** about 10 independent XRPL operators. Sometimes the answer is obvious, so the value shifts to picking the right endpoint and avoiding storefronts that won't settle.
- **Cold start:** scores need purchases to learn from. We start with operator-level priors and our own audit buys.
- **Gaming:** merchants could pay themselves to raise their score. Batch detection and audit buys raise the cost, but don't eliminate it.
- **The Bazaar may improve its own ranking.** Our edge is outcome data it doesn't collect.
- **Sensitivity:** our numbers contradict published XRPL agent-payment totals. Present them as measurements, with the method shown.

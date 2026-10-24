# Plumb: build spec (v0.1, 2026-10-24)

Plumb sits between an AI agent and the XRPL x402 marketplace. Given a need, it returns the **three endpoints most likely to deliver a usable answer at the lowest cost**, each with its trust score and on-ledger evidence. Plumb is itself an x402 seller on XRPL (~0.002 RLUSD per answer).
- Why it matters: `docs/PITCH.md`.
- The evidence behind every number: `docs/EVIDENCE.md`.

Track: Agentic Finance. Scope: **XRPL merchants only**. Stack: XRPL · Quicknode · AWS (Bedrock, AgentCore Gateway).

---

## 1. Components and load
| Component | Kind | Load (demo / v1) | Notes |
|---|---|---|---|
| `catalog` | cron worker, every 15 min | ~2.5k XRPL listings | syncs Bazaar listings where an `accepts[]` entry is on `xrpl:0` |
| `ledger` | long-running daemon | ~7k x402 payments a day (E5) | Quicknode WebSocket `subscribe` to transactions, keeping those with `SourceTag == 804681468`. Backfills through `account_tx` on each `payTo` |
| `auditor` | cron worker plus CLI | ≤ N purchases a day, under a hard cap | buys sampled endpoints with **real RLUSD**, then labels the outcome |
| `scorer` | runs inside `catalog` and `auditor`, and on demand | thousands of endpoints | Bayesian trust per endpoint (§3) |
| `ranker` | inside `api` | ≤ 5 req/s demo | relevance from a judge, combined with trust (§4) |
| `api` | FastAPI, sync endpoints | ≤ 5 req/s demo | an x402-paid `POST /v1/shortlist`, plus free endpoints for reporting outcomes and reading scores |
| `mcp` | thin wrapper | — | the same contract as an MCP tool, registered as an AgentCore Gateway target |
| `eval` | CLI | 20 fixed queries | head to head, Bazaar vs Plumb. Dry-run by default; `--live` spends RLUSD |

Storage is one SQLite file (WAL). The money types are `Decimal` for RLUSD and `int` drops for XRP, never floats.

## 2. Data model and invariants
```
operator(payto PK, first_seen, label)                      -- one XRPL account = one operator (E7)
endpoint(id PK = sha256(url+method), url, method, payto FK, asset, price DECIMAL, description, input_schema, output_schema,
         example, bazaar_calls_30d, bazaar_payers_30d, listed_at, last_seen, delisted_at)
payment(tx_hash PK, ledger_index, close_time, payer, payto, asset, amount DECIMAL, invoice_id, source_tag)   -- validated only
account(addr PK, created_at, funded_by, created_ledger)    -- for payer-independence clustering
payer_cluster(addr PK, cluster_id)                         -- batch-created accounts collapse to one cluster
audit(id PK, endpoint FK, need_id, at, preflight JSON, http_status, schema_ok, judge_ok, settled_tx UNIQUE NULL,
      spent DECIMAL, verdict ENUM(good,bad,unsettled,refused))
outcome_report(payment_tx PK, shortlist_id FK, endpoint FK, reporter_payer, verdict ENUM(good,bad), at, weight REAL)
shortlist(id PK, need_hash, need_text, at, paid_tx UNIQUE, results JSON, mode ENUM(demo,live))
score(endpoint PK, alpha REAL, beta REAL, mean REAL, lower80 REAL, n_audits, n_reports, settle_ok BOOL, price_honest BOOL, updated_at)
principal(addr PK, label, profile JSON, source ENUM(ledger,simulated))      -- the paying XRPL account = the customer's agent
principal_outcome(id PK, principal FK, endpoint FK, verdict ENUM(good,bad), latency_ms, at, source ENUM(report,simulated))
fit(need_key, endpoint FK, p_fit REAL, reason, provider, at, PK(need_key, endpoint))   -- computed offline (§4)
```
**Invariants:**
- `payment` holds only validated transactions with result `tesSUCCESS`.
- `outcome_report.payment_tx` is UNIQUE and must be a validated payment from `reporter_payer` to that endpoint's `payto`, made **after** `shortlist.at` and within 24 h.
- `audit.settled_tx` is UNIQUE.
- `shortlist.paid_tx` is UNIQUE: one paid answer per payment.
- RLUSD amounts are positive `Decimal`s, and no float ever touches money.
- A score always carries its counts, so a reader can see how much evidence stands behind it.

## 3. The trust score (invented by us)
**It's a probability, not a count:** the probability that paying this endpoint now gets a usable answer.

**Where evidence comes from, and at what grain.** The ledger only names the merchant account (`payTo`), never the endpoint (EVIDENCE: protocol facts).
- **Operator level (prior):** from the ledger. The share of x402 payments that settled, independent payers, and recency.
- **Endpoint level (likelihood):** from our **audits**, plus **routed-outcome reports** tied to a real payment.

**Model:**
1. **Prior.** Beta per endpoint, with prior `(α₀, β₀) = m·(μ_op, 1−μ_op)`.
   - `μ_op` is the operator's audited good rate, shrunk toward the global XRPL rate (32%, E2).
   - Prior strength is `m = 4`.
2. **Updates.** `α += Σ wᵢ·goodᵢ` and `β += Σ wᵢ·badᵢ`, with weight `wᵢ = recency(Δt; τ=7d) × independence(payer)`.
   - Our own audits have independence 1.
   - A reported outcome has independence `1/|cluster|`, so a merchant paying itself to report "good" gains almost nothing, and a whole farm cluster counts as one payer.
3. **Gates and penalties.**
   - **`settle_ok`:** a preflight check, under 1 s and free. Does the `payTo` exist, does it have an RLUSD trust line, does it need a destination tag or deposit authorization? Then a facilitator `/verify` of a signed but unsubmitted blob, which moves no money. If any check fails, `P(settle) = 0`.
   - **`price_honest`:** the price in the 402 challenge must equal the listing. If not, multiply by 0.5 and flag it.
4. **Outputs.** The `mean`, the 80% lower bound (`lower80`), and the counts.

5. **Per-principal posterior (personalisation).** The global posterior is the *average* customer. Each principal gets its own Beta whose prior is the global mean at strength `κ` (config, default 8):
   `α_p = κ·mean_g + Σ wᵢ·goodᵢ`, `β_p = κ·(1−mean_g) + Σ wᵢ·badᵢ`, over that principal's own outcomes only.
   - A new principal ranks exactly like the global score; each of its outcomes moves its ranking away from the average.
   - Personalisation is on **constraints and outcomes, not taste**: a principal's `profile` holds hard constraints (`max_price`, accepted `assets`, `max_latency_ms`, `require_output_schema`), and its outcomes carry what "usable" meant for it.
   - The principal is the paying XRPL account, so there is no signup. Its past x402 payments can seed `principal_outcome` (`source=report` once confirmed).

**Payer clusters** come from account creation: accounts created within a 10-minute window from the same funder (exchange hot wallets included, E6) form one cluster.

## 4. Ranking
**No LLM call on the request path.** Time to a usable answer is a product benefit, so the judge runs offline and the request path is lookup plus arithmetic (target p95 < 100 ms).
1. **Candidates.** Up to 40 endpoints: the top 20 from the Bazaar's XRPL search, plus our own lexical (BM25) search over the listings (description, URL path). Embeddings are a later swap behind the same function.
2. **Relevance, offline.** An LLM judge reads a need plus each candidate's listing and returns `P(fit) ∈ [0,1]` with a one-line reason, as structured output, stored in `fit`.
   - **Provider is a config value:** Claude on **Bedrock** by default, the Anthropic API as fallback.
   - The judge runs over known needs ahead of time. A request is matched to the nearest known need (lexical similarity ≥ a configured threshold) and reuses its `fit` rows. Below the threshold, `P(fit)` is the normalised BM25 score and the result is labelled `relevance=lexical`.
   - Listing text is **untrusted data** and goes into the judge as quoted data.
3. **Rank.** Drop candidates that break the principal's profile constraints, then rank by **expected cost per good answer** = `price / (P(fit) × lower80_p × P(settle))`, where `lower80_p` is the principal's posterior (§3.5), with ties broken by latency. Return the top `k` (default 3, maximum 5).
4. **Exploration.** In `live` mode, 10% of slots are Thompson-sampled from endpoints with little evidence. In `demo` mode it's **off**, with fixed seeds, so runs reproduce.
5. **Each result carries:** `trust{mean, lower80, n_audits, n_reports, settle_ok, price_honest}`, `price`, `why`, and `evidence[]` (audit tx hashes and sample payment tx hashes).

## 5. API (x402 seller on XRPL)
- **`POST /v1/shortlist`** with body `{need: str ≤ 1000, max_price?: Decimal, k?: 1..5, principal?: r-address}`. `principal` defaults to the paying account.
  - With no payment, it returns `402` with `PAYMENT-REQUIRED` (`exact`, `xrpl:0`, RLUSD, the fee, `payTo` = Plumb's account, `extra.invoiceId` = a fresh UUID, `extra.sourceTag` = configured).
  - With a payment, it verifies and settles through the facilitator. Then `200 {shortlist_id, results[]}`.
  - A replayed `paid_tx` returns the stored result.
- **`POST /v1/outcomes`** (free) with `{shortlist_id, endpoint_id, payment_tx, verdict}`.
  - It's accepted only if the invariants in §2 hold on the ledger: `400` if malformed, `409` if the `payment_tx` was already used, `422` if it doesn't qualify.
- **`GET /v1/endpoints/{id}/score`** (free, rate-limited): the score with its evidence.
- **Errors** share one body `{error:{code, message}}`. The codes are a closed list.
- The MCP tools `recommend(need, k?, principal?, max_price?)` and `report_outcome(principal, endpoint_id, verdict)` call the same service. The AgentCore Gateway target uses the OpenAPI spec.

### 5b. Payment rails
- **AP4M on XRPL EVM Testnet** (Mastercard's kit, chain 1449000, RLUSD with 18 decimals) is **the demo rail and the Mastercard prize path**.
  - Plumb's team **merchant** is a thin Node service (`merchant-ap4m/`, built on `createX402Merchant` from `ap4m-x402.mjs`). It issues the 402, checks the agent's EIP-712 voucher, and forwards to the Python API, which releases the shortlist.
  - Our **buyer agent** (`agent-ap4m/`, `buyResource`) opens a channel with a cap and pays Plumb per shortlist.
  - Constraint: a channel can only pay **our own team's merchant** unless the organizers enable cross-team payments. So in AP4M, Plumb is the merchant being paid.
- **t54 x402 on XRPL mainnet** is the rail of the real merchants Plumb ranks (EVIDENCE). Plumb's own fee could use it later, but it's off the demo path.
- **Mastercard's "strong demo" checklist, mapped to Plumb:**

  | Group | Their requirement | How Plumb shows it |
  |---|---|---|
  | Control | PSP-attested identities | agent and merchant onboarded in the AP4M portal |
  | Control | funded channel cap | `requestChannel` with a cap |
  | Control | over-cap attempt rejected | the agent asks for one more shortlist than the cap allows and is refused |
  | Payment | HTTP 402 requirements | Plumb's 402 |
  | Payment | agent-signed voucher | the buyer agent decides it's worth paying (expected cost per good answer) and signs |
  | Payment | immediate resource release | the shortlist is returned |
  | Proof | `VoucherRedeemed` | event on the XRPL EVM explorer |
  | Proof | `ClaimPaid` + `SettlementRecorded` | settled on-chain |
  | Proof | receipt | the `receipt_url` |

## 6. Failure modes
| Failure | Handling |
|---|---|
| The Quicknode WebSocket drops | reconnect with backoff, then backfill the gap through `account_tx` per `payTo` from the last stored ledger |
| A ledger read fails during `/verify` | `503`. No shortlist is served without payment |
| The facilitator `/settle` result is unknown (timeout) | store the payment as pending, look it up by tx hash, serve once it's validated, and never charge twice |
| The judge provider is down | fall back to the other provider. If both are down, rank by embedding similarity × trust, and label the result `relevance=embedding_only` |
| An audit purchase fails mid-way | record the verdict `unsettled` or `bad`, and count what was spent against the caps |
| Listing or response text is malicious | it's data only, never instructions, and is capped in length before reaching the judge |

## 7. Authorization and money
- **Plumb's seller account** receives fees and never sends, apart from sweeps.
- **The auditor wallet** is a separate account. Its seed lives only in `env/auditor.env`.
  - Caps live in config, not code: `audit.max_per_purchase`, `audit.max_per_day`, `audit.max_total`.
  - It's **dry-run by default**. Spending real money needs `--live` plus the caps, and **the user's go-ahead before the first live run**.
- **The `eval` CLI** follows the same rule, with its own caps.
- **Secrets:** seeds, the Quicknode URL (it embeds a token) and AWS credentials are each loaded only by the process that needs them. They're never logged or returned.
- **Abuse:** outcome reports are free, but each one needs a real, independent, post-shortlist payment (§2), so faking a report costs money and gains a fraction of a payer.

## 8. Idempotency and concurrency
- Each audit settles at most once (`audit.settled_tx` is UNIQUE).
- Paying again with the same `paid_tx` replays the stored shortlist.
- Score updates are append-only events, folded per endpoint in one SQLite transaction.
- `ledger` is a single writer. Readers use WAL.

## 9. Observability
- **Logs:** one JSON line per shortlist (`need_hash`, candidates, scores, latency, mode, provider), per audit and per ledger gap.
- **Metrics:**
  - shortlists served;
  - p95 latency;
  - judge cache hit rate;
  - audit spend against caps;
  - ledger lag (last validated ledger vs now);
  - catalog freshness.
- **`/healthz`:** returns 200 only if ledger lag is under 60 s, the catalog synced within the last hour, and the database answers.

## 10. Not in v1
- Mastercard **card** merchants. Mastercard's AP4M rail on XRPL EVM *is* in scope (§5b);
- merchants on other chains;
- pay-on-success payment channels (roadmap);
- staking or slashing;
- a consumer UI beyond a one-page leaderboard view;
- learned ranking models.

## 10b. The demo mock (2026-10-24)
The first build is a **realistic mock**: real market data, simulated customers, clearly labelled.
| Input | Real or simulated | Source |
|---|---|---|
| Listings, prices, operators | real | Bazaar XRPL search for the 20 frozen needs, snapshotted |
| Endpoint evidence (settled, HTTP, schema, latency) | real | vet402's public XRPL purchases (E2) |
| `P(fit)` | real judge output when Bedrock is reachable, else lexical (labelled) | offline judge (§4) |
| Customers (principals) and their outcomes | **simulated** | personas in `config/personas.toml`; outcomes drawn from the real endpoint evidence plus each persona's constraints |

**Caveat, said on stage:** a simulated evaluation of personalisation is circular, because the simulator encodes the preferences the ranker then learns. It shows the mechanism, not real-world lift.
Not in the mock: the x402-paid API (U6), live ledger ingest (U2), live audits (U3), payer clustering.

## 11. Open questions (answered in BUILD_PLAN U0)
U0 ran on 2026-10-24 from a cloud session with no secrets: no Quicknode URL, no AWS credentials, no seeds. Public rippled servers on port 443 (`s1`/`s2.ripple.com`) stood in for Quicknode. Nothing was signed, submitted or paid. The scripts and snapshots are in `research/u0/`.

1. **Does the Bazaar's XRPL search return at least two operators for realistic needs?** If not, the demo reranks endpoints within an operator and removes storefronts that won't settle.
   **`ANSWERED`: yes. The fallback demo isn't needed.**
   - **All 20 needs qualify.** All 20 needs in `eval/queries.yaml` (written before any count was taken) have 2–6 distinct XRPL `payTo` in the top 20: median 4, and 11 needs have exactly 4. A repeat query returned identical results for every need (`p2.json`).
   - **Caveat: this counts operators in the result list, not operators with a relevant endpoint.** Going by URL paths alone:
     - q13 (verify an XRPL tx) has one plausibly relevant operator;
     - q18 (XRP news) has one, plus `pay.edge-agents.ai` at ranks 2 and 3.
   - **The Bazaar's own #1 XRPL pick:**
     - it's `pay.edge-agents.ai` for q02;
     - it's XRP-only for 6 needs (all `api.stablecoingateways.com`);
     - it advertises a non-t54 SourceTag, or none, for 10 needs.

     So the U7 eval wallet needs XRP as well as RLUSD. `eval/rubric.md` §1 covers XRP-only picks.
2. **Does Quicknode's XRPL WebSocket `subscribe` stream every transaction, including the tagged payments? Can Streams' "Ledger" dataset stand in for it?**
   **`BLOCKED_EXTERNAL` for Quicknode** (no endpoint in this environment). **`ANSWERED` for the same `subscribe` API on public rippled. The Streams dataset is `NOT_RUN`.**
   - **Real time, yes.** Two 10-minute captures on `wss://s1.ripple.com` (`p3_run1.json`, `p3_run2.json`), 151 ledgers each:
     - the ledgers held 54 and 51 t54-tagged Payments, about 7.6k and 7.1k a day, in line with E5;
     - every streamed one (52 and 48) was validated with `tesSUCCESS` and carried an InvoiceID;
     - each arrived a median 2.8 s and 4.3 s (p95 7.0 s and 6.6 s) after its ledger's close time, and about 0.25 s after that ledger's own `ledgerClosed` message.
   - **Complete only with backfill.** The public connection dropped once in each run (a keepalive timeout, then an abrupt close).
     - Run 1 missed 2 of 54 tagged payments and 135 of 6,122 Payments overall.
     - Run 2 lost 5 consecutive ledgers: 3 of 51 tagged payments and 39 of 4,665 Payments.
     - A JSON-RPC rescan of the same ledgers found every missing one.

     The gap backfill in §6 is therefore required, not optional.
   - **The tagged flow isn't the Bazaar's merchants.** None of the 100 streamed tagged payments went to a Bazaar-listed `payTo`. 64 came from the E4 farm senders, and 94 went to the farm's receivers (`p3b.json`).
3. **What is the exact path of the Bazaar search endpoint, and does it filter by `network`?**
   **`ANSWERED`.**
   - **The path** is `GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/search?query=<text>&network=xrpl:0&limit=<n>`. Both `/resources/search` and `/search/resources` return 404.
   - **On `/search`, `network=xrpl:0` does filter**, server-side. This corrects the earlier evidence that it was ignored.
     - Only XRPL listings come back.
     - `network=xrpl`, `xrpl:1` and a made-up value return 0 results.
     - `limit` is honoured (5 returns 5).
     - Results stop at 20 and often fewer: 5–20 for our 8 probe words.
   - **Without the filter, XRPL listings are crowded out:** 0–6 of the top 20, both for the probe words and for the eval needs.
   - **The list endpoint `/resources` ignores `network`.** It returns the same total (42,241) with no XRPL rows on page 1, raises a `limit` below 20 to 20, and returns `items`, not `resources`. That's the likely source of the "ignored" finding.
   - **Keep the client-side check** (`accepts[].network == "xrpl:0"`), because a listing can name several networks.
   - **Listing shapes, for U2's parser** (`p1.json`, `catalog.json.gz`):
     - RLUSD `amount` is a decimal string (`"0.003"`); XRP `amount` is integer drops (`"2310"`);
     - 112 of 3,207 XRPL listings are XRP-only, and some also accept USDC on XRPL;
     - `extra.invoiceId` is the value from the crawler's 402 challenge (question 8).
4. **Will t54's mainnet facilitator settle to any `payTo`, so Plumb can collect its own fee?**
   **`BLOCKED_EXTERNAL`:** `/verify` needs a blob signed by a funded mainnet seed.
   - **The read-only part** (`p5.json`): mainnet `/supported` lists `exact` and `batch-settlement` (binding `xrpl-check-session`) on `xrpl:0`, the extension `x402Secure`, and an empty `signers` list. Testnet lists `exact` and `upto` on `xrpl:1`.
   - **Indirect evidence:** 10 different Bazaar `payTo` accounts receive t54-tagged payments carrying an InvoiceID (`p1b.json`), so t54 isn't tied to one merchant. Whether it accepts a brand-new `payTo` like Plumb's is still open.
5. **Which embedding and judge models are available on Bedrock in the event's region?**
   **`BLOCKED_EXTERNAL`:** there are no AWS credentials in this environment.
6. **U0 probe 6, the first live audit.**
   **`NOT_RUN`:** it was out of scope for this session (no auditor seed, no go-ahead).
7. **Extra check A: can one `account_info` call date an account?**
   **`ANSWERED`: not an active one** (`xa.json`).
   - **The starting `Sequence` is the creating ledger.** For 5 of 5 farm senders from `research/s1/p5.json`, the AccountRoot's starting `Sequence` (`NewFields.Sequence` in the creating Payment's metadata) equals that Payment's ledger index. The account's first own transaction uses that same `Sequence`.
   - **`account_info` returns the *current* `Sequence`,** which is the start plus every transaction sent since. For these accounts that overshoots by 109,155–112,909 ledgers, about 5 days of ledgers, far beyond the 10-minute cluster window (§3).
   - **Exact dating takes one different call:** `account_tx` with `forward: true, limit: 1` on a full-history server. It returns the creating transaction, giving the ledger, the close time, the funder and `NewFields.Sequence`.
   - **For U2:** use that call for `account.created_ledger`. Treat `account_info.Sequence` only as an upper bound.
8. **Extra check B: does any public invoiceId's SHA-256 match an on-ledger InvoiceID?**
   **`ANSWERED`: yes, but only for a seller whose invoiceIds are static** (`xb.json`).
   - **vet402:** its export has no invoiceId column, and its `purchase_id` isn't the preimage (0 of 92 settled XRPL rows).
   - **The Bazaar** caches `extra.invoiceId` on 3,178 XRPL listings (5,606 values).
     - fizzl.eu (`r9xmBs…`) uses static strings such as `"presign-guard.fizzl.eu POST /v1/check"`. SHA-256 (UTF-8, uppercase hex) of 8 of them equals the InvoiceID of 18 validated payments, out of 242 x402-like payments scanned across 13 `payTo`. That confirms `InvoiceID = SHA-256(invoiceId)` on mainnet, with public preimages.
     - The other 5 operators sampled issue a fresh invoiceId per 402 challenge, and none of their cached values matched.
   - **What it means:**
     - showing the preimage proves "payer or merchant" only where invoiceIds are nonces; for static-ID sellers the preimage is public and proves nothing;
     - for static-ID sellers, the InvoiceID names the endpoint on-ledger, so they have endpoint-level ledger evidence, an exception to "the ledger names the merchant, not the endpoint";
     - a proof-of-purchase review can't be checked from public data alone. The reviewer has to supply the invoiceId from their own 402 challenge.
9. **New, raised by U0: t54's SourceTag doesn't cover the whole XRPL market.**
   - **In the catalogue,** 637 of 3,207 XRPL listings (20%) offer no option with t54's tag:
     - `pay.edge-agents.ai` advertises `402402402` on all 587 of its listings;
     - horizonpulse.dev advertises no tag (29);
     - stablecoingateways uses `26100002`–`26100015` (14);
     - bruk-agent-api advertises no tag on 7.
   - **On-ledger,** 5 of 243 x402-like payments (those with an InvoiceID) to Bazaar `payTo` carry a non-t54 tag or none (`p1b.json`).
   - **`pay.edge-agents.ai` has never been paid an x402 sale on-ledger:** none of its 20 incoming payments (2026-03-02 to 10-03) carries an InvoiceID or a tag. That backs up E2's 0 for 88.
   - **Suggested for the `ledger` owner (§1 and §3 are unchanged here):** also keep Payments whose `Destination` is a catalogue `payTo`, and use InvoiceID presence as the x402 marker alongside the SourceTag.

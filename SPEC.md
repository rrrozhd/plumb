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

**Payer clusters** come from account creation: accounts created within a 10-minute window from the same funder (exchange hot wallets included, E6) form one cluster.

## 4. Ranking
1. **Candidates.** Up to 40 endpoints: the top 20 from the Bazaar's XRPL search, plus our own embedding search over the listings (description, schemas, example).
2. **Relevance.** An LLM judge reads the need plus each candidate's listing and returns `P(fit) ∈ [0,1]` with a one-line reason, as structured output.
   - **Provider is a config value:** Claude on **Bedrock** by default, the Anthropic API as fallback.
   - Results are cached per `(need_hash, endpoint)`.
   - Listing text is **untrusted data** and goes into the judge as quoted data.
3. **Rank.** By **expected cost per good answer** = `price / (P(fit) × lower80 × P(settle))`, with ties broken by latency. Return the top `k` (default 3, maximum 5).
4. **Exploration.** In `live` mode, 10% of slots are Thompson-sampled from endpoints with little evidence. In `demo` mode it's **off**, with fixed seeds, so runs reproduce.
5. **Each result carries:** `trust{mean, lower80, n_audits, n_reports, settle_ok, price_honest}`, `price`, `why`, and `evidence[]` (audit tx hashes and sample payment tx hashes).

## 5. API (x402 seller on XRPL)
- **`POST /v1/shortlist`** with body `{need: str ≤ 1000, max_price?: Decimal, k?: 1..5}`.
  - With no payment, it returns `402` with `PAYMENT-REQUIRED` (`exact`, `xrpl:0`, RLUSD, the fee, `payTo` = Plumb's account, `extra.invoiceId` = a fresh UUID, `extra.sourceTag` = configured).
  - With a payment, it verifies and settles through the facilitator. Then `200 {shortlist_id, results[]}`.
  - A replayed `paid_tx` returns the stored result.
- **`POST /v1/outcomes`** (free) with `{shortlist_id, endpoint_id, payment_tx, verdict}`.
  - It's accepted only if the invariants in §2 hold on the ledger: `400` if malformed, `409` if the `payment_tx` was already used, `422` if it doesn't qualify.
- **`GET /v1/endpoints/{id}/score`** (free, rate-limited): the score with its evidence.
- **Errors** share one body `{error:{code, message}}`. The codes are a closed list.
- The MCP tool `plumb.shortlist(need, max_price?, k?)` calls the same service. The AgentCore Gateway target uses the OpenAPI spec.

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

## 11. Open questions (answered in BUILD_PLAN U0)
1. Does the Bazaar's XRPL search return **at least two operators** for realistic needs? If not, the demo reranks endpoints within an operator and removes storefronts that won't settle.
2. Does Quicknode's XRPL WebSocket `subscribe` stream every transaction, including the tagged payments? Can Streams' "Ledger" dataset stand in for it?
3. What is the exact path of the Bazaar search endpoint, and does it filter by `network`?
4. Will t54's mainnet facilitator settle to any `payTo`, so Plumb can collect its own fee?
5. Which embedding and judge models are available on Bedrock in the event's region?

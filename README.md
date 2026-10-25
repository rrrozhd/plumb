# Plumb

**The router that tells AI agents which XRPL merchant to pay, for them.**

An agent asks for what it needs. Plumb returns three XRPL x402 merchants ranked by expected cost per usable answer, using saved purchase and ledger evidence, and only merchants the agent's AP4M mandate can pay. Live deck: `site/`. Customer feedback persists across restarts and changes that customer's recommendations. The agent pays Plumb per shortlist through **Mastercard AP4M**.

Built at the XRPL NYC AI & Fintech Hackathon (Agentic Finance track) on **XRPL**, **Quicknode**, **AWS Bedrock**, **AgentCore Memory** and **Mastercard AP4M**.

## Results (real money, XRPL mainnet, pre-registered, graded by code)
| Test | Plumb | Coinbase Bazaar #1 | Reading |
|---|---|---|---|
| **E26:** 100 new questions, each answer bought and checked against a public source | 77 good | 72 good | a tie (p = 0.40); the Bazaar was cheaper per good answer (0.0032 vs 0.0065 RLUSD), mostly because of our flat fee |
| **E27:** why we missed (offline, no purchases) | the right merchant never reached our shortlist on 28 of 72 needs | | meaning-only search; adding keyword search recovers all 72 |
| **E28:** the 14 questions we failed, bought again after the fix | 10 of 14 good (was 0) | 9 of 14 (in E26, not re-bought) | recovery, not overall accuracy; re-running all 100 is next |

- **The problem we measured:** of 17,684 real x402 purchase attempts across chains, 44% got no usable answer (E3); on XRPL, 2 in 3 (E2). The Bazaar's #1 for one need, pay.edge-agents.ai, settled 0 of 88; Plumb never recommends it.
- **Speed:** 0.13 ms worst-5% per cached shortlist, no LLM on the request path (E25).
- **Mastercard AP4M (testnet):** identities and a funded 0.005 channel cap, HTTP 402 → agent-signed voucher → resource released, an over-cap attempt refused, settlement and an AP4M receipt linking channel, claim and payout (E18; slide 6 of the deck, built by `ap4m/proof.py`).

The data behind each result is committed in `data/` (`e26_result.json`, `e26_union_replay.json`, `e28_result.json`, `e21_result.json`), with pre-registrations in `eval/`.

## What's mocked or not live
- **AP4M** runs on XRPL EVM **testnet** and pays only our own merchant (AP4M's rule). New channels are blocked by AP4M's per-merchant channel limit (L27), so the deck replays the last completed run (2026-10-25 05:25 UTC); every hash links to the explorer.
- **Per-customer learning** is shown with **simulated** customers. The live, real part is the payment constraint: Quicknode reads each account's trust lines and balances.
- **Our own test purchases are not yet in the trust scores**; trust comes from vet402's public purchase log plus ledger reads. Only 9% of candidate endpoints have any purchase on record (E15).
- **Pricing:** 0.002 RLUSD per shortlist today; the percentage fee is a calculation, not a live test.

## How it works
1. **Catalogue:** Bazaar XRPL listings; a liveness check excludes dead endpoints.
2. **Relevance:** Titan embeddings, then BM25, then an offline Claude judge (exact / partial / wrong). Exact matches always rank first. A never-seen need is judged once by the AI judge, then cached.
3. **Trust:** P(the payment settles) per merchant account and rail × P(the answer is good, given it settled) per endpoint. The current fitter uses saved vet402 purchase observations and ledger payments read through Quicknode.
4. **Ranking:** expected cost per good answer, with one result per operator.
5. **Personalisation:** account constraints and a per-customer posterior over its own outcomes, with a co-purchase signal from the snapshot. Saved customer feedback does not train other customers.
6. **Feedback:** `good`/`bad` reports persist in SQLite and reload in CLI, MCP and HTTP recommendations. Identical retries count once; conflicting feedback for the same customer, shortlist and endpoint is rejected. Payment-proven reports are stored separately; the global trust fitter does not yet consume them.

Full spec: [`SPEC.md`](SPEC.md).

## Run it

This source snapshot includes the market data and frozen evaluation results needed
for cached recommendations and the offline tests. Raw purchase response bodies,
customer databases, cloud receipts, AP4M replay trails and backup videos are local
artifacts and are not included. The memory demo can show historical payment
metadata without the saved response body. Live integrations need your own
credentials and resources.
```bash
uv sync
uv run pytest -m p0                                  # offline gate; zero selected tests is a failure
uv run plumb recommend "Current XRP price in USD"    # a shortlist from the committed snapshot
uv run plumb recommend "<need>" --as <r-address>     # personalised
uv run plumb bench                                   # p50 / p95 latency
uv run python -m plumb.mcp_server                    # MCP tools: recommend, report_outcome
```

**Customer-memory browser demo:**

```bash
uv run python -m plumb.memory_demo
```

Open [localhost:8405](http://127.0.0.1:8405). Teach the fast shopper, then reload
the worker: a new process restores its ranking from `out/memory-demo.sqlite`,
while the control shopper and global trust stay unchanged. Both generated
personas start with identical payment profiles and empty personal histories.
The response and purchase record are historical; latency dissatisfaction is
explicitly simulated. Quicknode's optional verification button reads that
existing payment and makes no new purchase. This demonstrates memory and
isolation, not proven customer benefit or a network effect.

The ordinary services use `[paths].db` in `config/plumb.toml`; CLI
`recommend --db <path>` can inspect another customer store. MCP's
`report_outcome` records feedback for a saved shortlist; HTTP remains a
shortlist endpoint. 
The managed AWS rehearsal restored exact simulated feedback into a fresh
database and reproduced that customer's learned ranking (EVIDENCE MEM2).
Backup is an explicit operator action; ordinary ranking uses local SQLite.

**Mastercard AP4M (XRPL EVM testnet).** First complete the [AP4M setup](ap4m/README.md), including the sponsor helper downloads, your `env/ap4m.env`, and team onboarding:
```bash
uv run python -m plumb.api &
(cd ap4m && node merchant.mjs) &
(cd ap4m && node agent.mjs)
```
**Refresh data** (network; Bedrock needs `env/judge.env`, Quicknode needs `env/ledger.env`): `uv run plumb snapshot`, then `uv run plumb build`, then `uv run plumb liveness`.

**Evals** (dry-run by default; `--live` spends mainnet RLUSD within the caps in `config/plumb.toml`): `uv run plumb eval-free`, `uv run plumb e21`.

## Layout

The Python package groups implementation by responsibility:

```text
plumb/
├── core/             # config.py, db.py, models.py, money.py: shared foundations
├── interfaces/       # cli.py, api.py, mcp_server.py, memory_demo.py and HTML
├── sources/          # catalog.py, ledger.py: marketplace and XRPL evidence
├── recommendation/   # recommender.py, rank.py, score.py, relevance.py,
│                     # judge.py, principals.py: fit and rank recommendations
├── customer/         # memory.py, outcomes.py, agentcore_memory.py: feedback and backup
├── evaluation/       # eval_free.py, eval_paid.py, grader.py, stats.py
├── __init__.py
└── cli.py, api.py, mcp_server.py, memory_demo.py, agentcore_memory.py
                      # small compatibility launchers
```

Only package initialization and compatibility launchers remain at the root, so
the commands above remain unchanged. Import implementation modules from their
owning package, for example `from plumb.core import config`,
`from plumb.interfaces import api` or `from plumb.customer import memory`.

CLI, HTTP and MCP requests enter through `interfaces/` and call
`recommendation/rank.py`, which loads the snapshot fit, applies customer memory,
and ranks eligible endpoints. The fit combines `sources/catalog.py` with saved
audit and ledger evidence; customer feedback persists through
`customer/outcomes.py` and `customer/memory.py`. Shared configuration, value
types, money handling and SQLite access live in `core/`. Evaluation runners and
response grading live together in `evaluation/`.

The surrounding repository keeps its existing roles:

- `ap4m/`: Mastercard AP4M merchant shim and buyer agent (Node).
- `data/`: the committed market snapshot, judge labels and eval results.
- `eval/`: the frozen needs, the rubric and the E21 pre-registration.

## Demo, team and licence
- **Demo video:** _add the unlisted link here_. Presenter deck: `cd site && npm run dev`, then http://127.0.0.1:5173.
- **Team:** rrrozhd.
- **Licence:** _not yet chosen_.


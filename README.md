# Plumb

**The router that tells AI agents which XRPL merchant to pay, for them.**

An agent asks for what it needs. Plumb returns, in under a millisecond, the three XRPL x402 merchants most likely to deliver *for that agent*, ranked by what actually happened on the ledger, not by call counts. The agent pays Plumb per shortlist through **Mastercard AP4M**.

Built at the XRPL NYC AI & Fintech Hackathon (Agentic Finance track) on **XRPL**, **Quicknode**, **AWS Bedrock** and **Mastercard AP4M**.

## Results (real money, mainnet, pre-registered)
| 20 frozen needs, every answer bought and graded | Good answers | Cost per good answer (RLUSD) |
|---|---|---|
| Coinbase Bazaar's #1 | 7 / 20 | 0.0133 |
| **Plumb's #1** (fee included) | **11 / 20** | **0.0068** |
| fizzl (buys on any chain) | 13 / 20 | 0.0277 |

- **Speed:** a shortlist takes 0.13 ms at worst-5% (E25), with no LLM on the request path.
- **AP4M:** live on testnet, with a capped channel, paid shortlists, an over-cap refusal and a settled receipt.

Sources and caveats: [`docs/EVIDENCE.md`](docs/EVIDENCE.md) (E18–E23) and [`docs/LIMITS.md`](docs/LIMITS.md).

## How it works
1. **Catalogue:** Bazaar XRPL listings; a liveness check excludes dead endpoints.
2. **Relevance:** Titan embeddings, then BM25, then an offline Claude judge (exact / partial / wrong). Exact matches always rank first. A never-seen need is judged once (~20 s), then cached.
3. **Trust:** P(the payment settles) per merchant account and rail × P(the answer is good, given it settled) per endpoint. Built from real purchases (vet402, our audits) and ledger payments read through Quicknode.
4. **Ranking:** expected cost per good answer, with one result per operator.
5. **Personalisation:** hard limits from the account's ledger state, then a per-customer posterior over its own outcomes, then an "agents who paid A also paid B" nudge.
6. **Feedback:** reports personalise; only reports proven on the ledger change global trust.

Full spec: [`docs/RECOMMENDER.md`](docs/RECOMMENDER.md) and [`SPEC.md`](SPEC.md).

## Run it
```bash
uv sync
uv run pytest -m p0                                  # offline gate (78 tests)
uv run plumb recommend "Current XRP price in USD"    # a shortlist from the committed snapshot
uv run plumb recommend "<need>" --as <r-address>     # personalised
uv run plumb bench                                   # p50 / p95 latency
uv run python -m plumb.mcp_server                    # MCP tools: recommend, report_outcome
```
**Mastercard AP4M (XRPL EVM testnet).** It needs `env/ap4m.env` and an onboarded team:
```bash
uv run python -m plumb.api &
cd ap4m && npm install && node merchant.mjs &
PLUMB_NEW_CHANNEL=1 node agent.mjs
```
**Refresh data** (network; Bedrock needs `env/judge.env`, Quicknode needs `env/ledger.env`): `uv run plumb snapshot`, then `uv run plumb build`, then `uv run plumb liveness`.

**Evals** (dry-run by default; `--live` spends mainnet RLUSD within the caps in `config/plumb.toml`): `uv run plumb eval-free`, `uv run plumb e21`.

## Layout
- `plumb/`: catalogue, ledger, scorer, relevance, judge, recommender, ranker, principals, outcomes, grader, evals, MCP server, API.
- `ap4m/`: Mastercard AP4M merchant shim and buyer agent (Node).
- `data/`: the committed market snapshot, judge labels and eval results.
- `eval/`: the frozen needs, the rubric and the E21 pre-registration.
- `docs/`: pitch, demo script, evidence, limits, markets, prep.

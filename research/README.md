# research/: the probes behind `docs/EVIDENCE.md`

These are one-off scripts, read-only against XRPL mainnet and public APIs. **The live data drifts**, so re-running them gives today's numbers, not the 2026-10-24 snapshot. The stored JSON files are that snapshot.

| Script | What it measures | Run |
|---|---|---|
| `vet402/xrpl_outcomes.py` | E2: XRPL purchase outcomes, prices and waste, from vet402's public export | `uv run --no-project --with xrpl-py python research/vet402/xrpl_outcomes.py` |
| `s1/p1_identify.py` | x402 markers on XRPL (SourceTag, InvoiceID) from vet402's settled tx hashes | `... python research/s1/p1_identify.py <vet402.csv> out/p1.json` |
| `s1/p2_collect.py` | 30-day x402 payments to known merchants, plus funding parents | `... python research/s1/p2_collect.py out/p1.json out/p2.json` |
| `s1/p3_wash.py` | four simple wash rules applied to p2 | `... python research/s1/p3_wash.py out/p2.json` |
| `s1/p4_ledgerscan.py` | x402 payments in N recent ledgers (E4, E5) | `... python research/s1/p4_ledgerscan.py out/p4.json 150` |
| `s1/p5_parents.py` | creation time and funding parents of the senders | `... python research/s1/p5_parents.py out/p4.json out/p5.json` |
| `s1/p6_roots.py` | funding ancestry walk (E6) | `... python research/s1/p6_roots.py out/p4.json out/p5.json` |
| `m1/check2_verify.py` | t54 testnet facilitator `/verify` with single-sig vs multisig payers | `... python research/m1/check2_verify.py` (creates testnet faucet wallets) |

`...` = `uv run --no-project --with xrpl-py --with httpx`. `p6_roots.py` needs no labels file. The exchange-label check used XRPScan's public `/api/v1/names/well-known`, which you can fetch as needed.

## `u0/`: BUILD_PLAN U0 probes (2026-10-24)
These answer SPEC §11. They're read-only: nothing is signed, submitted or paid. Constants come from `u0/u0.toml`. They use public XRPL servers on port 443 (`s1`/`s2.ripple.com`) in place of Quicknode, and run from the repo root.

| Script | What it measures | Run | Snapshot |
|---|---|---|---|
| `u0/p1_bazaar.py` | Bazaar `/search` path and `network` filter (Q3); census of XRPL listings (assets, SourceTags, invoiceIds) | `... python research/u0/p1_bazaar.py` | `u0/p1.json`, `u0/catalog.json.gz` |
| `u0/p1b_payto_tags.py` | SourceTag and InvoiceID of recent incoming payments to each XRPL `payTo` | `... python research/u0/p1b_payto_tags.py` | `u0/p1b.json` |
| `u0/p2_diversity.py` | operator diversity per eval need (Q1) | `... --with pyyaml python research/u0/p2_diversity.py eval/queries.yaml` | `u0/p2.json` |
| `u0/p3_feed.py` | 10 min of the `transactions` stream: tagged payments, latency, and a JSON-RPC rescan for completeness (Q2) | `... python research/u0/p3_feed.py 600 research/u0/p3_runN.json` | `u0/p3_run1.json`, `u0/p3_run2.json` |
| `u0/p3b_xref.py` | who sends and receives the live tagged payments (Bazaar `payTo`? S1 farm?) | `... python research/u0/p3b_xref.py research/u0/p3_run*.json` | `u0/p3b.json` |
| `u0/p5_t54_supported.py` | t54 `/supported` on mainnet and testnet (the read-only half of Q4) | `... python research/u0/p5_t54_supported.py` | `u0/p5.json` |
| `u0/xa_account_dates.py` | extra check A: starting `Sequence` = creating ledger, and what one `account_info` call gives | `... python research/u0/xa_account_dates.py` | `u0/xa.json` |
| `u0/xb_invoice_preimage.py` | extra check B: any public invoiceId whose SHA-256 is an on-ledger InvoiceID | `... python -I research/u0/xb_invoice_preimage.py` (downloads vet402's export) | `u0/xb.json` |

`p3_run1.json` came from an earlier `p3_feed.py` that didn't yet record which ledgers the stream skipped. `xb_invoice_preimage.py` sends unpaid GETs to 7 merchant endpoints, only to read their 402 challenges.

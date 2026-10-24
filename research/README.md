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

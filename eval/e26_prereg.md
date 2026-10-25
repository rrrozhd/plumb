# E26 pre-registration: 100 code-checked needs, Plumb #1 vs Bazaar #1 (committed before any E26 pick or purchase, 2026-10-25)

**Question:** is Plumb's accuracy edge over the Bazaar's top XRPL result real? E24 pooled 30 needs, with 6 wins and 1 loss (p = 0.125). That is suggestive, not significant.

**Needs:** `eval/queries_e26.yaml`, generated once by `eval/gen_e26.py` from fixed lists rather than from the catalogue. There are 100 needs in 6 families:

| Family | Count |
|---|---|
| Crypto price in USD | 25 |
| Crypto price in EUR | 10 |
| Currency conversion | 25 |
| US city weather | 15 |
| Chain block height | 10 |
| Public holiday by country | 15 |

No two needs share a template, and none was seen before. `tests/test_e26_needs.py` checks both.

## Arms
- **Bazaar:** its #1 XRPL result under 0.05 RLUSD, from a live search at dry-run time. Arguments come from the same judge-v2 argument filler Plumb uses.
- **Plumb:** its #1 with `fit_v2.json` plus the cold path (judge v2), no principal, called with its `call.args`.
- **Freezing:** both arms' picks are frozen to `data/e26_picks.json` by the dry-run and committed. The live run buys exactly those picks.

## Grading (frozen)
- Grader **v3** (`plumb/grader.py`, `VERSION = 3`, commit `5da91f3`). Every need has a family oracle against a free public source:
  - CoinGecko, within 2%;
  - ECB rates via frankfurter, within 1% of the rate (or within 0.1% of 100 × the rate);
  - NWS station observation, within 4 °C, temperature fields only;
  - a public RPC head, within about 120 s of blocks;
  - nager.date: the date plus a holiday flag or the holiday's name.
- **LLM fallback:** the LLM is used only where an oracle is unavailable. The share of verdicts graded by oracle vs LLM is reported.
- **Outcomes that are never good:** no pick, refused (no x402 challenge, or over the cap), and unsettled (no own validated payment).

## Analysis (fixed now)
1. **Primary:** exact two-sided sign test on good answers, paired by need, at α = 0.05.
2. **Cluster sensitivity (pre-registered):** many needs in one family can route to the same endpoints, so need-level pairs are not independent. Collapse the discordant needs into distinct (Bazaar URL, Plumb URL) pairs, take each pair's majority outcome, and sign-test those. If the effect holds only at need level, we report it that way.
3. **Secondary:**
   - good answers per arm;
   - cost per good answer, with Plumb's 0.002 fee included and without, plus a 10,000-resample bootstrap interval over needs;
   - a per-family table;
   - the oracle vs LLM share.
4. E26 is reported alone and also pooled with E24. Because the Plumb versions differ, the pooled figure is secondary.

## Expectations stated in advance
- Most of these families resell free data (LIMITS L26), and their prices are about 0.001–0.004. With a flat 0.002 fee, cost per good answer will probably favour the Bazaar, as in E23. The question E26 answers is accuracy.
- The power estimate was simulated from E24's observed discordance of 23% and a win share of 6/7: 0.95 at 100 needs if needs are independent, about 0.6 if the true win share is 0.75. Clustering lowers it, so the dry-run reports the number of distinct discordant (B, P) pairs before any money moves.

## Rules
- One attempt per pick.
- Caps: 0.05 per purchase and 3 in total, from `config/plumb.toml`.
- The live run writes its report after every need and resumes by (need, arm), so a crash never re-buys.
- After the dry-run, changes are allowed only as a dated addendum. The need set is never edited.

## Addendum, 2026-10-25 05:40 UTC: dry-run gate, before any E26 purchase
- Picks frozen in `data/e26_picks.json`; the cold-path labels behind Plumb's picks are in `data/fit_cold.json`.
- **Independence:** the two arms pick different endpoints on 80 needs, which collapse to **40 distinct (Bazaar URL, Plumb URL) pairs** (≥ 30, so the cluster test can reach significance if the effect holds). By family: crypto USD 20, crypto EUR 9, FX 24, weather 8, blocks 4, holidays 15.
- **No pick:** Plumb returns none on 9 needs; they count as not good for Plumb, as pre-registered.
- **Spend:** 180 purchases, expected **0.502 RLUSD + 0.030 RLUSD-eq in XRP** to merchants (plus 0.2 notional fee). The auditor wallet holds about 0.30 RLUSD, so **the live run waits for an RLUSD top-up of at least 0.3**; running dry mid-run would leave later RLUSD purchases unsettled on whichever arm pays in RLUSD.

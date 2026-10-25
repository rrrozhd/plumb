# E22 pre-registration: held-out needs, judge v2 (committed before any E22 label or purchase, 2026-10-25)

**Question:** on 10 **new** needs (`eval/queries_e22.yaml`) that played no part in building or tuning Plumb, does Plumb with judge v2 (capability rule and call arguments) still beat the Bazaar on good answers and on cost per good answer?

## Arms
| Arm | Pick | Request |
|---|---|---|
| **Bazaar** | its #1 XRPL result under 0.05 RLUSD, live search at run time | arguments from the **same** judge-v2 argument filler, so both arms get equally good calls |
| **Plumb v2** | its #1, with `fit_v2.json` plus the cold path for these needs, no principal | its `call.args` |

fizzl is not repeated (E21 covers it). A pick shared by both arms is bought once and counted on both, label and spend (rubric §1.6).

## Grading, frozen
- Grader v2 (`plumb/grader.py`): oracles for all 10 needs, from the public sources named in each `check`, added in the same commit as this file. The LLM is used only for what's left.
- LLM-only grades are reported alongside.

## Rules
- One attempt per pick; caps 0.05 per purchase and 3 total; expected spend about 0.06 RLUSD-equivalent.
- **Metric:** good answers out of 10 and cost per good answer (Plumb includes 0.002 per need).
- Reported next to E20 and E21; it replaces neither.

## Addendum, 2026-10-25, committed before any E22 purchase
- **e08 is not held out for Plumb.** "WHOIS … coinbase.com" masks to the same need template as frozen q14 (ripple.com), so Plumb serves q14's judged labels. E22 is reported on all 10 needs **and** on the 9 that are truly new (e08 excluded).
- **Two argument bugs found by the first dry-run, fixed before freezing** (commit 45934c2): cached labels carried the judged need's entities (e08 would have queried ripple.com), and some judge args copied the listing's `{queryParams: …}` wrapper (e02 Bazaar arm). The picks were re-frozen after the fix (bab0f33). Same endpoints on both arms; only arguments changed.
- **The live run buys exactly `data/e22_picks.json`** as committed, with no new Bazaar search or judge call.
- **Known grader-v2 limits, not changed (v2 stays frozen):** the oracle's number extractor reads only JSON numbers, and the freshness check ignores UTC offsets. Full bodies are stored. A regrade with a fixed grader will be reported as a sensitivity, never in place of v2.
- Ledger attribution is now by each purchase's own signed tx hash (2ef1aed, 81203b1).

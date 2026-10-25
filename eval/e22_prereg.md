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

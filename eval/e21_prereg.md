# E21 pre-registration (committed before any E21 purchase, 2026-10-25)

**Question:** for the 20 frozen needs (`eval/queries.yaml`, unchanged), which source delivers more good answers per RLUSD?

## Arms
| Arm | What is bought | Cost counted per need |
|---|---|---|
| **Bazaar** | its #1 XRPL pick under the need's max price, from `data/u7_paid_picks.json` (frozen 2026-10-25) | the merchant's price |
| **Plumb** | its #1 pick from the same file | the merchant's price **+ 0.002 RLUSD** (Plumb's own fee per shortlist) |
| **fizzl** | `POST https://buy.fizzl.eu/v1/buy` with `{"need": <need text verbatim>}` | its charge (0.02 RLUSD listed); 0 if nothing is charged |

Shared picks between Bazaar and Plumb are bought once, and both get the same label (rubric §1.6).

## Grading, frozen
- **Primary: grader v2** at commit `8c4d153` (`plumb/grader.py`). Code checks first, ground-truth oracles for 12 needs, then the LLM only for what's left, on the **full** response body.
- **Secondary, reported alongside: LLM-only.** The same Sonnet 5.5 prompt as E20, on the full body (up to 200k characters).
- Both graders run on the same stored bodies. A disagreement on the overall result is reported, not resolved.
- Responses are saved verbatim under `out/u7-bodies-v2-*`.

## Rules
- One paid attempt per pick (rubric §1.5). A retry is allowed only if no payment was submitted.
- Caps: 0.05 RLUSD per purchase, 3 RLUSD total; this run is expected to cost at most about 0.6 RLUSD.
- **Metric:** good answers out of 20, and cost per good answer, per arm and per grader.
- E21 sits **next to** E20 and never replaces it.
- No E21 outcome feeds the ranking before this report is published. After that, only the universal checks feed it (RECOMMENDER §4c).

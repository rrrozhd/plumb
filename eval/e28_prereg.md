# E28 pre-registration: does union recall recover E26's failures? (committed before any E28 purchase, 2026-10-25)

**Question:** E26's 9 lost needs and 5 extra no-pick needs were caused mainly by embedding-only candidate recall (EVIDENCE E27). With union recall, how many of those 14 needs does Plumb now answer well?

- **Needs:** `eval/queries_e28.yaml`, the same 14 needs copied unchanged from `eval/queries_e26.yaml`, with the same oracles.
- **Picks:** Plumb #1 with union recall and judge v2, frozen with their call arguments in `data/e28_picks.json` before buying. One arm only: the Bazaar's E26 result on these needs is already recorded (8 good of 14, since some are needs it also failed).
- **Grading:** grader v3, unchanged from E26.
- **Metric:** good answers out of 14. Baseline: E26 Plumb got **0 of 14** on these needs.
- **Bias, stated in advance:** these needs were selected *because* Plumb failed them, so this measures recovery on failures, not overall accuracy. Some recovery is expected by chance alone. It is not pooled into E26.
- **The replay differed:** the frozen picks for f062 and f063 differ from the earlier replay (`data/e26_union_replay.json`) because the judge is not deterministic. These frozen picks are the ones bought.
- **Rules:** one attempt per pick; caps 0.05 per purchase and 3 in total (config). The live run waits for the user's go-ahead.

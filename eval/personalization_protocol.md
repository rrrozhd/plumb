# Personalization comparison, v1

This protocol is frozen before running the comparison. The question is whether
own outcomes and then shared-buyer information improve a customer's choices over
global trust. No ranker changes, network requests, model calls or purchases are
part of this experiment. Existing paid evaluations are not customer preference data.

## Evidence gate

First inspect stored principal outcomes and proven reports, without modifying the
database. A real chronological customer evaluation requires customer-linked task,
candidate, exposure, outcome and time records. Payments alone do not establish
satisfaction. If those labels are absent, report the real comparison as unavailable.

## Offline diagnostic

Use the original frozen needs in `eval/queries.yaml`, their cached `data/fit.json`
labels and the existing catalog, liveness and trust snapshot. Exercise the unchanged
production `Ranker.shortlist()`. Do not include the later cold-query benchmark.
Hash determining code, configuration and data before and after the run; reject a
run whose inputs changed. This is an ordinary local experiment, not managed execution.

Three arms share the same candidates, prices, relevance, gates and common default
Profile (both assets, no price cap or schema restriction):

- Global: empty personal history, no collaborative signal.
- Personal: synthetic own history, no collaborative signal.
- Collaborative: identical own history plus the existing real-ledger operator
  co-occurrence matrix. Do not manufacture a favorable synthetic peer graph.

Use the two existing persona preference dictionaries and a neutral control.
Override their payment profiles with the common profile to isolate preference
learning from eligibility. Synthetic satisfaction depends only on declared output
field count and the snapshot's observed/fallback latency: apply the existing slow
and thin penalties from `config/personas.toml`. Missing latency is fixed in the
experiment config. Never use q_mean, q_lo, predicted fit or selected rank to generate
these labels. Latency and output metadata themselves remain imperfect proxies.
Neutral satisfaction is always one; it is a control for unnecessary ranking changes.

Use every configured seed. Uniformly sample training exposures from the union of
eligible endpoints, deduplicated across needs. Generate Bernoulli training outcomes
using a training-only random stream. Freeze this history before ranking. A separate
deterministic random draw per seed/persona/need/endpoint supplies the hypothetical
future outcome, shared by all arms if they pick the same endpoint. No future draw
enters the history or collaborative graph. This is a synthetic future-event split,
not evidence of generalization to new real customers or new task categories.

Evaluate two scenarios: `repeat` permits previously tried endpoints; `unseen_operator`
splits the sorted eligible operators into seeded, disjoint halves, training only on
one half and restricting every arm's evaluation candidates to the other half.
Retain empty-result queries and seeds with no trainable candidates. Global trust
still knows the held-out merchants: only the target customer's familiarity is held out.

Report top-one synthetic satisfaction per query (abstention counts as zero), offer
coverage, expected synthetic satisfaction, exact Decimal quoted merchant cost per
synthetic success, and changes in selected endpoint. Prices assume every selected
offer is paid once; they exclude fees, failed-settlement modeling and time costs.
Report results by persona and scenario and paired seed-level wins/ties/losses.
Do not treat random seeds as independent real customers or report significance.
Keep losses and null results; do not tune preferences, sample sizes or the ranker.

## Interpretation and next real comparison

This diagnostic can reveal an inert or harmful component under declared assumptions.
It cannot demonstrate factual answer quality, real satisfaction, commercial demand,
algorithmic originality or superiority to a contextual LLM. The LLM comparator is
not run offline and must not be represented as beaten.

For a real study, freeze customer tasks and chronological histories, give all arms
the same eligible catalog and evidence, and collect blinded customer-specific
outcome judgments for the union of selected alternatives. Evaluate global, personal,
collaborative and an LLM supplied with the same context. A separate experiment can
measure the value of Plumb assembling evidence rather than its ranking method.
Previously selected purchases alone cannot reveal outcomes for unchosen alternatives.


"""The recommender (RECOMMENDER §4b): `fit` offline, `score` as pure arithmetic on the request path.

v1 HybridRecommender = content (p_fit) x trust (settle x quality, personalised) + a collaborative nudge.
The ledger names operators, not endpoints, so real interactions are operator-level; the collaborative signal is
operator-operator co-occurrence ("agents who paid A also paid B"). Swap `fit` for ALS once real outcomes exist.
"""
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from plumb.sources import catalog
from plumb.recommendation import score
from plumb.core.models import Endpoint, Profile


@dataclass
class Principal:
    addr: str
    label: str
    profile: Profile
    source: str                                               # ledger | simulated
    outcomes: dict[str, list[float]] = field(default_factory=dict)  # endpoint_id -> [good, bad]
    operators: dict[str, list[float]] = field(default_factory=dict)  # payTo -> [good, bad] (operator-level, from the ledger)


class Recommender(Protocol):
    def score(self, principal: Principal | None, candidates: dict[str, float]) -> dict[str, float]: ...


@dataclass
class HybridRecommender:
    cfg: dict
    endpoints: dict[str, Endpoint]
    trust: dict[str, score.Trust]
    cooc: dict[str, dict[str, float]]
    principals: dict[str, Principal]
    xrp_in_rlusd: Decimal
    evidence: dict[str, list[dict]]                      # endpoint_id -> vet402 rows
    payments: dict[str, list[dict]]                      # payTo -> real ledger payments

    # ---- request path -------------------------------------------------------------------------
    def personal_q(self, p: Principal | None, eid: str) -> tuple[float, float, int]:
        """(q_mean, q_lo) for this principal; n = personal observations behind it."""
        t = self.trust[eid]
        if p is None:
            return t.q_mean, t.q_lo, 0
        op = self.endpoints[eid].payto
        g, b = p.outcomes.get(eid, [0.0, 0.0])
        og, ob = p.operators.get(op, [0.0, 0.0])
        g, b = g + og, b + ob
        if g + b == 0:  # collaborative nudge only where the principal has no evidence of its own
            g += self.cf_affinity(p, op) * float(self.cfg["score"]["cf_max_shift"])
        kappa = float(self.cfg["score"]["principal_strength_kappa"])
        a, bb = score.personal(t, g, b, kappa)
        if (a, bb) == (t.alpha, t.beta):
            return t.q_mean, t.q_lo, 0
        return a / (a + bb), score.beta_quantile(a, bb), round(g + b)

    def cf_affinity(self, p: Principal, op: str) -> float:
        liked = [o for o, (g, b) in p.operators.items() if g > b] + \
                list({self.endpoints[e].payto for e, (g, b) in p.outcomes.items() if g > b})
        return max((self.cooc.get(o, {}).get(op, 0.0) for o in liked if o != op), default=0.0)

    def score(self, principal: Principal | None, candidates: dict[str, float]) -> dict[str, float]:
        """candidates: endpoint_id -> p_fit. Returns p_good = p_fit x p_settle x q_lo (personalised)."""
        return {e: f * self.trust[e].p_settle * self.personal_q(principal, e)[1] for e, f in candidates.items()}

    def price_rlusd(self, e: Endpoint, prof: Profile) -> tuple[Decimal, str] | None:
        opts = []
        if e.price_rlusd and "RLUSD" in prof.assets:
            opts.append((e.price_rlusd, "RLUSD"))
        if e.price_xrp_drops and "XRP" in prof.assets:
            opts.append((Decimal(e.price_xrp_drops) / 1_000_000 * self.xrp_in_rlusd, "XRP"))
        return min(opts) if opts else None


def _url_key(url: str) -> str:
    return url.split("://", 1)[-1].rstrip("/")


def fit(cfg: dict, root, principals: dict[str, Principal] | None = None) -> HybridRecommender:
    """Build the recommender from the committed snapshot (offline, a few seconds)."""
    eps = catalog.load_endpoints(cfg, root)
    by_url = {_url_key(e.url): e for e in eps.values()}
    rail = {i: (e.payto, e.source_tag) for i, e in eps.items()}

    attempts, evidence = [], defaultdict(list)
    for row in csv.DictReader((root / "vet402_xrpl.csv").open()):
        e = by_url.get(_url_key(row["resource_key"]))
        if not e:
            continue
        lat = int(row["latency_ms"]) if row["latency_ms"].isdigit() else None
        attempts.append(score.Attempt(e.id, rail[e.id], score.classify_vet402(row), lat))
        evidence[e.id].append({"source": "vet402", "tx": row["tx_hash"] or None, "verdict": score.classify_vet402(row),
                               "at": row["attempted_at"]})

    payments = json.loads((root / "ledger_payments.json").read_text())
    merchants = {e.payto for e in eps.values()}
    by_payto = defaultdict(list)
    for p in payments:
        by_payto[p["payto"]].append(p)
    real = [p for p in payments if p["payer"] not in merchants]  # a merchant paying merchants is not independent
    payers_on_rail = Counter()
    for (payto, tag), payers in _group(real).items():
        payers_on_rail[(payto, tag)] = len(payers)
    trust = score.fit_trust(rail, attempts, dict(payers_on_rail), cfg)

    # Real principals: each independent payer, with operator-level implicit outcomes (repeat purchase = weak good).
    w = float(cfg["score"]["implicit_repeat_weight"])
    ps = dict(principals or {})
    hist = defaultdict(Counter)
    for p in real:
        hist[p["payer"]][p["payto"]] += 1
    for payer, ops in hist.items():
        ps.setdefault(payer, Principal(payer, f"ledger {payer[:6]}", Profile(), "ledger"))
        for op, n in ops.items():
            ps[payer].operators[op] = [w * (n - 1), 0.0]

    # Operator co-occurrence (cosine over who paid whom), from real payers and simulated principals alike.
    users_by_op = defaultdict(set)
    for p in ps.values():
        for op in p.operators:
            users_by_op[op].add(p.addr)
        for e in p.outcomes:
            users_by_op[eps[e].payto].add(p.addr)
    cooc: dict[str, dict[str, float]] = defaultdict(dict)
    for a, ua in users_by_op.items():
        for b, ub in users_by_op.items():
            if a != b and ua & ub:
                cooc[a][b] = len(ua & ub) / math.sqrt(len(ua) * len(ub))

    meta = json.loads((root / "meta.json").read_text())
    return HybridRecommender(cfg, eps, trust, dict(cooc), ps, Decimal(meta["xrp_in_rlusd"]), dict(evidence), dict(by_payto))


def _group(payments: list[dict]) -> dict[tuple[str, int | None], set[str]]:
    out = defaultdict(set)
    for p in payments:
        out[(p["payto"], p["source_tag"])].add(p["payer"])
    return out

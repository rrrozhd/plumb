"""Trust = P(settle) per (payTo, rail) x P(good | settled) per endpoint (RECOMMENDER §4), plus the per-principal posterior.

Probabilities are floats; money never passes through here.
"""
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache

import mpmath

Rail = tuple[str, int | None]  # (payTo, SourceTag)


@dataclass(frozen=True)
class Attempt:
    """One observed purchase: vet402's, our audit, or a verified report."""
    endpoint_id: str
    rail: Rail
    outcome: str             # good | bad (settled), rail_fail (never settled), rejected (4xx before payment)
    latency_ms: int | None = None


@dataclass(frozen=True)
class Trust:
    p_settle: float          # posterior mean of P(settle) on the endpoint's rail
    settle_ok: bool
    alpha: float             # quality Beta, settled attempts only
    beta: float
    q_mean: float
    q_lo: float              # 20th percentile
    n_obs: int               # endpoint-level observations behind q
    latency_ms: int | None   # median of good attempts; operator-level fallback


def classify_vet402(row: dict) -> str:
    """Map one vet402 export row to an Attempt outcome (vet402 definitions, research/vet402/xrpl_outcomes.py)."""
    if row["status"] in ("settled", "settle_claimed"):
        ok = row["http_status_paid"].startswith("2") and row["l2_reading"] != "mismatch"
        return "good" if ok else "bad"
    return "rejected" if row["held_reason"] == "unsettled_4xx" else "rail_fail"


def beta_quantile(a: float, b: float, p: float = 0.2) -> float:
    """Exact Beta quantile by bisection on the regularised incomplete beta; cached, since endpoints share priors."""
    return _bq(round(a, 6), round(b, 6), p)


@lru_cache(maxsize=65536)
def _bq(a: float, b: float, p: float) -> float:
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if mpmath.betainc(a, b, 0, mid, regularized=True) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _median(xs: list[int]) -> int | None:
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else None


def fit_trust(endpoints: dict[str, Rail], attempts: list[Attempt], ledger_payers: dict[Rail, int], cfg: dict) -> dict[str, Trust]:
    """endpoints: id -> rail. ledger_payers: distinct real payers seen settling on each rail (any-payer settlement proof)."""
    s = cfg["score"]
    m, settle_min = float(s["prior_strength_m"]), float(s["settle_min"])

    settled = [a for a in attempts if a.outcome in ("good", "bad")]
    fails = [a for a in attempts if a.outcome == "rail_fail"]
    g_settle = (len(settled) + 1) / (len(settled) + len(fails) + 2)
    g_good = (sum(a.outcome == "good" for a in settled) + 1) / (len(settled) + 2)

    rail_ok, rail_fail = defaultdict(float), defaultdict(float)
    for a in settled:
        rail_ok[a.rail] += 1
    for a in fails:
        rail_fail[a.rail] += 1
    for rail, n in ledger_payers.items():
        rail_ok[rail] += n

    by_ep, by_op = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    lat_ep, lat_op = defaultdict(list), defaultdict(list)
    for a in settled:
        k = 0 if a.outcome == "good" else 1
        by_ep[a.endpoint_id][k] += 1
        by_op[a.rail[0]][k] += 1
        if a.outcome == "good" and a.latency_ms:
            lat_ep[a.endpoint_id].append(a.latency_ms)
            lat_op[a.rail[0]].append(a.latency_ms)

    out = {}
    for eid, rail in endpoints.items():
        ok, bad = rail_ok[rail], rail_fail[rail]
        p_settle = (m * g_settle + ok) / (m + ok + bad)
        g, b = by_ep[eid]
        og, ob = by_op[rail[0]]
        mu_op = (og - g + m * g_good) / (og + ob - g - b + m)  # leave-one-out operator prior
        alpha, beta = m * mu_op + g, m * (1 - mu_op) + b
        out[eid] = Trust(p_settle=p_settle, settle_ok=p_settle >= settle_min, alpha=alpha, beta=beta,
                         q_mean=alpha / (alpha + beta), q_lo=beta_quantile(alpha, beta), n_obs=g + b,
                         latency_ms=_median(lat_ep[eid]) or _median(lat_op[rail[0]]))
    return out


def personal(t: Trust, good: float, bad: float, kappa: float) -> tuple[float, float]:
    """Per-principal quality posterior (RECOMMENDER §4): exactly global with no outcomes; else global capped at kappa."""
    if good + bad == 0:
        return t.alpha, t.beta
    s = min(kappa, t.alpha + t.beta)
    return s * t.q_mean + good, s * (1 - t.q_mean) + bad

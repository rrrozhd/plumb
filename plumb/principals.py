"""Principals (RECOMMENDER §4): real XRPL accounts seeded from the ledger, plus simulated personas (labelled).

A real principal's hard constraints come from its ledger state: it can pay RLUSD only if it holds an RLUSD trust line.
Simulated outcomes are drawn from real endpoint evidence plus each persona's preferences, with a fixed seed.
"""
import json
import random
import tomllib
from decimal import Decimal

from plumb.models import Profile
from plumb.recommender import HybridRecommender, Principal


def seed_from_ledger(ledger, addr: str, cfg: dict) -> dict:
    """Read-only: account_lines -> which assets this account can pay with. Returns a JSON-able record."""
    x = cfg["xrpl"]
    lines = ledger.account_lines(addr)
    rlusd = next((ln for ln in lines if ln.get("currency") == x["rlusd_currency"] and ln.get("account") == x["rlusd_issuer"]), None)
    info = ledger.account_info(addr)
    return {"addr": addr, "assets": ["RLUSD", "XRP"] if rlusd else ["XRP"],
            "rlusd_balance": rlusd["balance"] if rlusd else "0", "xrp_drops": info.get("Balance", "0")}


def load_ledger_principals(path) -> dict[str, Principal]:
    if not path.exists():
        return {}
    out = {}
    for r in json.loads(path.read_text()):
        out[r["addr"]] = Principal(r["addr"], f"ledger {r['addr'][:6]} ({'+'.join(r['assets'])})",
                                   Profile(assets=tuple(r["assets"])), "ledger")
    return out


def load_personas(path) -> dict[str, Principal]:
    out = {}
    for p in tomllib.loads(path.read_text())["persona"]:
        prof = Profile(max_price_rlusd=Decimal(p["max_price"]) if p.get("max_price") else None,
                       assets=tuple(p.get("assets", ["RLUSD", "XRP"])), require_output_schema=p.get("require_output_schema", False))
        out[p["principal"]] = Principal(p["principal"], p["label"], prof, "simulated")
        out[p["principal"]].prefs = p.get("prefs", {})  # type: ignore[attr-defined]
    return out


def simulate(rec: HybridRecommender, fit: dict, personas: dict[str, Principal], n: int, seed: int) -> None:
    """Give each persona n simulated purchases among judged candidates (p_fit >= 0.5), in place.

    P(good) = the endpoint's real quality mean x the persona's own satisfaction (its prefs). Labelled simulated."""
    rng = random.Random(seed)
    pool = [(e, x) for v in fit.values() for e, x in v["labels"].items() if x["p_fit"] >= 0.5 and e in rec.trust]
    for p in personas.values():
        prefs = getattr(p, "prefs", {})
        for _ in range(n):
            e, _x = rng.choice(pool)
            ep, tr = rec.endpoints[e], rec.trust[e]
            if rec.price_rlusd(ep, p.profile) is None:
                continue
            sat = 1.0
            if prefs.get("max_latency_ms") and (tr.latency_ms or 5000) > prefs["max_latency_ms"]:
                sat *= prefs.get("slow_penalty", 0.2)
            if prefs.get("min_output_fields") and ep.output_fields < prefs["min_output_fields"]:
                sat *= prefs.get("thin_penalty", 0.3)
            if prefs.get("distrusts") and ep.payto.startswith(tuple(prefs["distrusts"])):
                sat *= 0.1
            good = rng.random() < tr.q_mean * sat
            g, b = p.outcomes.get(e, [0.0, 0.0])
            p.outcomes[e] = [g + good, b + (not good)]

"""Run with uv run --offline python -m eval.personalization. No purchases or LLM calls."""
import csv
import hashlib
import json
import random
import socket
import tomllib
from collections import defaultdict
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

import numpy as np
import yaml

from plumb import config, rank, recommender, relevance
from plumb.models import Profile
from plumb.recommender import Principal

ARMS = ("global", "personal", "collaborative")


def probability(endpoint, trust, prefs, missing_latency_ms):
    """Assumed satisfaction; deliberately independent of the ranker's quality estimates."""
    p = 1.0
    latency = trust.latency_ms if trust.latency_ms is not None else missing_latency_ms
    if prefs.get("max_latency_ms") and latency > prefs["max_latency_ms"]:
        p *= prefs["slow_penalty"]
    if prefs.get("min_output_fields") and endpoint.output_fields < prefs["min_output_fields"]:
        p *= prefs["thin_penalty"]
    return p


def operator_split(rec, pool, seed, unseen):
    if not unseen:
        return set(pool), set(pool)
    operators = sorted({rec.endpoints[e].payto for e in pool})
    random.Random(f"split:{seed}").shuffle(operators)
    seen = set(operators[:len(operators) // 2])
    train = {e for e in pool if rec.endpoints[e].payto in seen}
    return train, set(pool) - train


def draw_history(rec, pool, prefs, seed, name, n, missing_latency_ms):
    rng = random.Random(f"train:{seed}:{name}")
    pool = sorted(pool)
    history = {}
    for _ in range(n if pool else 0):
        e = rng.choice(pool)
        good = rng.random() < probability(rec.endpoints[e], rec.trust[e], prefs, missing_latency_ms)
        counts = history.setdefault(e, [0, 0])
        counts[0 if good else 1] += 1
    return history


def make_arm(base, history, arm, allowed):
    assert arm in ARMS
    principal = Principal("sim:eval", "simulated evaluation", Profile(), "simulated",
                          {} if arm == "global" else deepcopy(history))
    rec = replace(base.rec, principals={principal.addr: principal},
                  cooc=base.rec.cooc if arm == "collaborative" else {})
    fit = {t: {**v, "labels": {e: x for e, x in v["labels"].items() if e in allowed}}
           for t, v in base.fit.items()}
    return replace(base, rec=rec, fit=fit, log=[])


def evaluate(base, queries, personas, settings):
    """Future labels are held outside each arm. All arms receive the same eligible pool."""
    rec = base.rec
    pool = {e for q in queries for e, f in base.candidates(relevance.template(q["need"]))[0].items()
            if f >= float(rec.cfg["rank"]["fit_min"]) and e not in base.dead
            and rec.trust[e].settle_ok and rec.price_rlusd(rec.endpoints[e], Profile()) is not None}
    missing = settings["missing_latency_ms"]
    rows = []
    for scenario in settings["scenarios"]:
        for seed in settings["seeds"]:
            train, test = operator_split(rec, pool, seed, scenario == "unseen_operator")
            for persona in personas:
                name, prefs = persona["name"], persona["prefs"]
                history = draw_history(rec, train, prefs, seed, name, settings["training_events"], missing)
                arms = {a: make_arm(base, history, a, test) for a in ARMS}
                for q in queries:
                    row = {"scenario": scenario, "seed": seed, "persona": name, "need": q["id"],
                           "training_events": sum(sum(x) for x in history.values())}
                    for arm, r in arms.items():
                        choices = r.shortlist(q["need"], k=1, principal="sim:eval")["results"]
                        e = choices[0]["endpoint_id"] if choices else None
                        expected, satisfied, price = 0.0, 0, Decimal("0")
                        if e is not None:
                            expected = probability(rec.endpoints[e], rec.trust[e], prefs, missing)
                            satisfied = int(random.Random(f"test:{seed}:{name}:{q['id']}:{e}").random() < expected)
                            quote = rec.price_rlusd(rec.endpoints[e], Profile())
                            assert quote is not None
                            price = quote[0]
                        row[arm] = {"endpoint": e, "satisfied": satisfied, "expected_satisfaction": expected,
                                    "quoted_merchant_cost_rlusd": str(price)}
                    rows.append(row)
    return rows


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["scenario"], row["persona"])].append(row)
    summary = []
    for (scenario, persona), subset in groups.items():
        result = {"scenario": scenario, "persona": persona, "queries": len(subset), "arms": {}, "paired_seeds": {}}
        for arm in ARMS:
            successes = sum(r[arm]["satisfied"] for r in subset)
            cost = sum((Decimal(r[arm]["quoted_merchant_cost_rlusd"]) for r in subset), Decimal("0"))
            result["arms"][arm] = {
                "satisfied": successes, "offered": sum(r[arm]["endpoint"] is not None for r in subset),
                "expected_satisfaction": round(sum(r[arm]["expected_satisfaction"] for r in subset) / len(subset), 6),
                "quoted_merchant_cost_rlusd": str(cost),
                "quoted_cost_per_synthetic_success": str(cost / successes) if successes else None,
                "changed_from_global": sum(r[arm]["endpoint"] != r["global"]["endpoint"] for r in subset),
                "changed_from_personal": sum(r[arm]["endpoint"] != r["personal"]["endpoint"] for r in subset),
            }
        for a, b in (("personal", "global"), ("collaborative", "personal")):
            deltas = defaultdict(int)
            for r in subset:
                deltas[r["seed"]] += r[a]["satisfied"] - r[b]["satisfied"]
            result["paired_seeds"][f"{a}_minus_{b}"] = {
                "wins": sum(v > 0 for v in deltas.values()), "ties": sum(v == 0 for v in deltas.values()),
                "losses": sum(v < 0 for v in deltas.values()), "deltas": dict(deltas)}
        summary.append(result)
    return summary


def source_hashes(root):
    paths = ["config/plumb.toml", "config/personas.toml", "eval/queries.yaml", "eval/personalization.toml",
             "eval/personalization_protocol.md", "eval/personalization.py", "data/catalog.json.gz",
             "data/vet402_xrpl.csv", "data/ledger_payments.json", "data/meta.json", "data/fit.json", "data/liveness.json"]
    paths += [f"plumb/{name}.py" for name in ("config", "models", "catalog", "score", "recommender", "rank", "relevance")]
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths}


def main():
    root = config.ROOT
    before = source_hashes(root)
    cfg = config.load()
    settings = tomllib.loads((root / "eval/personalization.toml").read_text())
    templates = tomllib.loads((root / "config/personas.toml").read_text())["persona"]
    personas = [{"name": x["principal"], "prefs": x.get("prefs", {})} for x in templates]
    personas.append({"name": "sim:neutral-control", "prefs": {}})
    queries = yaml.safe_load((root / "eval/queries.yaml").read_text())["queries"]
    rec = recommender.fit(cfg, root / "data")
    fit = json.loads((root / "data/fit.json").read_text())
    assert all(relevance.template(q["need"]) in fit for q in queries), "a frozen need lacks cached labels"
    dead = {e for e, x in json.loads((root / "data/liveness.json").read_text())["endpoints"].items() if not x["alive"]}
    # Every evaluated need is cached; retrieval/model objects cannot initiate a call.
    base = rank.Ranker(rec, fit, relevance.Vectors([], np.empty((0, 0))), relevance.Lexical({}), dead=dead)

    def refuse(*args, **kwargs):
        raise AssertionError("network attempted in offline diagnostic")

    with patch.object(socket.socket, "connect", refuse), patch.object(socket.socket, "connect_ex", refuse):
        rows = evaluate(base, queries, personas, settings)
    assert before == source_hashes(root), "inputs changed during evaluation; discard this run"
    payments = json.loads((root / "data/ledger_payments.json").read_text())
    with (root / "data/vet402_xrpl.csv").open() as f:
        audit_tx = {r["tx_hash"].upper() for r in csv.DictReader(f) if r["tx_hash"]}
    merchants = {e.payto for e in rec.endpoints.values()}
    nonmerchant = [p for p in payments if p["payer"] not in merchants]
    overlap = [p for p in nonmerchant if p["tx_hash"].upper() in audit_tx]
    result = {"status": "synthetic diagnostic only; real customer holdout unavailable", "settings": settings,
              "personas": personas, "sources_sha256": before,
              "ledger_provenance": {"payments": len(payments), "nonmerchant_payments": len(nonmerchant),
                                    "known_audit_overlap": len(overlap), "audit_payers": len({p["payer"] for p in overlap})},
              "summary": summarize(rows), "rows": rows}
    path = root / "out/personalization_result.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("rows", "sources_sha256")}, indent=2))


if __name__ == "__main__":
    main()


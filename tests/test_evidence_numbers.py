"""Every headline number in the pitch is recomputed here from committed data, so docs can't drift from evidence."""
import csv
import json
from decimal import Decimal as D
from math import comb

import pytest

from plumb import config, score

pytestmark = pytest.mark.p0
DATA = config.ROOT / "data"
FEE = D("0.002")


def cost_per_good(rows, arm, fee=D(0), override=None):
    rs = [r[arm] for r in rows]
    good = sum(r["verdict"] == "good" for r in rs)
    spent = override if override is not None else sum((D(r.get("spent", "0")) for r in rs), D(0))  # shared spend counts on both arms
    return good, (spent + fee * len(rows)) / good


def test_e20_numbers():
    rows = json.loads((DATA / "u7_paid_result.json").read_text())["rows"]
    gb, cb = cost_per_good(rows, "bazaar")
    gp, cp = cost_per_good(rows, "plumb", FEE)
    assert (gb, gp) == (6, 10)
    assert round(cb, 4) == D("0.0159") and round(cp, 4) == D("0.0074")  # q13 unsettled (audit 2026-10-25)
    txs = [r[a]["tx"] for r in rows for a in ("bazaar", "plumb") if r[a].get("tx") and not r[a].get("shared")]
    assert len(txs) == len(set(txs))  # one ledger payment, one purchase


def test_e21_numbers():
    rows = json.loads((DATA / "e21_result.json").read_text())["rows"]
    gb, cb = cost_per_good(rows, "bazaar")
    gp, cp = cost_per_good(rows, "plumb", FEE)
    gf, cf = cost_per_good(rows, "fizzl", override=D("0.36"))  # ledger recount (static invoiceIds)
    assert (gb, gp, gf) == (7, 11, 13)
    assert round(cb, 4) == D("0.0133") and round(cp, 4) == D("0.0068") and round(cf, 4) == D("0.0277")
    assert round(cb / cp, 2) == D("1.95") and round(cf / cp, 1) == D("4.1")
    txs = [r[a]["tx"] for r in rows for a in ("bazaar", "plumb") if r[a].get("tx") and not r[a].get("shared")]
    assert len(txs) == len(set(txs))  # fizzl's static invoiceIds are why its spend is a ledger recount


def test_e21_paired_sign_test():
    rows = json.loads((DATA / "e21_result.json").read_text())["rows"]
    won = sum(r["plumb"]["verdict"] == "good" and r["bazaar"]["verdict"] != "good" for r in rows)
    lost = sum(r["bazaar"]["verdict"] == "good" and r["plumb"]["verdict"] != "good" for r in rows)
    n = won + lost
    p = min(1.0, 2 * sum(comb(n, k) for k in range(max(won, lost), n + 1)) / 2 ** n)
    assert (won, lost) == (4, 0) and round(p, 2) == 0.12


def test_e2_and_e16_e17_from_vet402():
    rows = list(csv.DictReader((DATA / "vet402_xrpl.csv").open()))
    kinds = [score.classify_vet402(r) for r in rows]
    good = [r for r, k in zip(rows, kinds) if k == "good"]
    edge = [r for r in rows if r["resource_key"].startswith("pay.edge-agents.ai")]
    assert len(edge) == 88 and all(r["status"] == "settle_failed" for r in edge)          # E2: 0 for 88
    assert len(good) == 65 and sum(r["l2_reading"] in ("not_checked", "no_declaration") for r in good) == 41  # E16
    lat = sorted(int(r["latency_ms"]) for r in good if r["latency_ms"].isdigit())
    assert lat[len(lat) // 2] == pytest.approx(8500, abs=600)                              # E17


def test_e15_evidence_coverage():
    from plumb import recommender
    fit = json.loads((DATA / "fit.json").read_text())  # the v1 labels E15 was measured on
    rec = recommender.fit(config.load(), DATA)
    cands = {e for v in fit.values() for e in v["labels"]}
    with_ev = sum(1 for e in cands if rec.evidence.get(e))
    assert (len(cands), with_ev) == (602, 53)


def test_e23_heldout_numbers():
    rows = json.loads((DATA / "e22_result.json").read_text())["rows"]
    gb, cb = cost_per_good(rows, "bazaar")
    gp, cp = cost_per_good(rows, "plumb", FEE)
    _, cp_nofee = cost_per_good(rows, "plumb")
    assert (gb, gp) == (7, 8) and round(cb, 4) == D("0.0026") and round(cp, 4) == D("0.0048") and cp_nofee == D("0.00225")
    new = [r for r in rows if r["id"] != "e08"]
    assert (sum(r["bazaar"]["verdict"] == "good" for r in new), sum(r["plumb"]["verdict"] == "good" for r in new)) == (6, 7)
    txs = [r[a]["tx"] for r in rows for a in ("bazaar", "plumb") if r[a].get("tx") and not r[a].get("shared")]
    assert len(txs) == len(set(txs)) == 18


def test_e24_pooled():
    rows = json.loads((DATA / "e21_result.json").read_text())["rows"] + json.loads((DATA / "e22_result.json").read_text())["rows"]
    gb, cb = cost_per_good(rows, "bazaar")
    gp, cp = cost_per_good(rows, "plumb", FEE)
    won = sum(r["plumb"]["verdict"] == "good" and r["bazaar"]["verdict"] != "good" for r in rows)
    lost = sum(r["bazaar"]["verdict"] == "good" and r["plumb"]["verdict"] != "good" for r in rows)
    n = won + lost
    p = min(1.0, 2 * sum(comb(n, k) for k in range(max(won, lost), n + 1)) / 2 ** n)
    assert (len(rows), gp, gb, won, lost, round(p, 3)) == (30, 19, 14, 6, 1, 0.125)
    assert round(cp, 4) == D("0.0060") and round(cb, 4) == D("0.0080") and round(cb / cp, 2) == D("1.34")


def test_e26_powered():
    import yaml
    from plumb import stats
    rows = json.loads((DATA / "e26_result.json").read_text())["rows"]
    fam = {q["id"]: q["family"] for q in yaml.safe_load((config.ROOT / "eval" / "queries_e26.yaml").read_text())["queries"]}
    r = stats.report(rows, fam)
    assert r["good"] == {"plumb": 77, "bazaar": 72}
    assert (r["primary"]["won"], r["primary"]["lost"], round(r["primary"]["p"], 2)) == (14, 9, 0.40)
    assert (r["cluster"]["won"], r["cluster"]["lost"], round(r["cluster"]["p"], 2)) == (9, 7, 0.80)
    assert round(D(r["cost_per_good"]["bazaar"]), 4) == D("0.0032") and round(D(r["cost_per_good"]["plumb_fee"]), 4) == D("0.0065")
    txs = [x[a]["tx"] for x in rows for a in ("bazaar", "plumb") if x[a].get("tx") and not x[a].get("shared")]
    assert len(txs) == len(set(txs)) == 158

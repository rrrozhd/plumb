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
    assert round(cb, 4) == D("0.0162") and round(cp, 4) == D("0.0076")


def test_e21_numbers():
    rows = json.loads((DATA / "e21_result.json").read_text())["rows"]
    gb, cb = cost_per_good(rows, "bazaar")
    gp, cp = cost_per_good(rows, "plumb", FEE)
    gf, cf = cost_per_good(rows, "fizzl", override=D("0.36"))  # ledger recount (static invoiceIds)
    assert (gb, gp, gf) == (7, 11, 13)
    assert round(cb, 4) == D("0.0133") and round(cp, 4) == D("0.0068") and round(cf, 4) == D("0.0277")
    assert round(cb / cp, 2) == D("1.95") and round(cf / cp, 1) == D("4.1")


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
    from plumb import rank
    r = rank.load(config.load(), DATA, with_principals=False)
    cands = {e for v in r.fit.values() if not v.get("cold") for e in v["labels"]}
    with_ev = sum(1 for e in cands if r.rec.evidence.get(e))
    assert (len(cands), with_ev) == (602, 53)

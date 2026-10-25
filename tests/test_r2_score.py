import csv
from pathlib import Path

import pytest

from plumb.core import config
from plumb.recommendation import score
from plumb.recommendation.score import Attempt

pytestmark = pytest.mark.p0
CFG = config.load()
OK: score.Rail = ("rGood", 804681468)
BAD: score.Rail = ("rNever", 402402402)


def fit(attempts, endpoints=None, ledger=None):
    endpoints = endpoints or {"e1": OK, "e2": OK, "e3": BAD, "e4": OK}
    return score.fit_trust(endpoints, attempts, ledger or {}, CFG)


def test_never_settling_rail_is_gated_and_good_rail_is_not():
    t = fit([Attempt("e3", BAD, "rail_fail")] * 88 + [Attempt("e1", OK, "good")] * 5)
    assert not t["e3"].settle_ok and t["e3"].p_settle < 0.05
    assert t["e1"].settle_ok


def test_no_evidence_endpoint_gets_its_operators_prior():
    t = fit([Attempt("e1", OK, "good")] * 6 + [Attempt("e2", OK, "good")] * 6)
    assert t["e4"].n_obs == 0
    assert t["e4"].q_mean > 0.75  # siblings on the same operator are all good


def test_leave_one_out_does_not_double_count():
    t = fit([Attempt("e1", OK, "good")] * 3)
    lone = fit([Attempt("e1", OK, "good")] * 3, endpoints={"e1": OK})
    assert t["e1"].alpha == pytest.approx(lone["e1"].alpha)


def test_rail_failures_never_move_quality():
    a = fit([Attempt("e1", OK, "good")] * 2)
    b = fit([Attempt("e1", OK, "good")] * 2 + [Attempt("e1", OK, "rail_fail")] * 5)
    assert a["e1"].alpha == b["e1"].alpha and a["e1"].beta == b["e1"].beta
    assert b["e1"].p_settle < a["e1"].p_settle


def test_rejected_requests_move_neither_settle_nor_quality():
    a = fit([Attempt("e1", OK, "good")])
    b = fit([Attempt("e1", OK, "good"), Attempt("e1", OK, "rejected")])
    assert a["e1"] == b["e1"]


def test_ledger_payers_prove_settlement():
    a = fit([Attempt("e1", OK, "rail_fail")] * 3)
    b = fit([Attempt("e1", OK, "rail_fail")] * 3, ledger={OK: 10})
    assert b["e1"].p_settle > a["e1"].p_settle


def test_exact_quantile_is_below_mean():
    assert score.beta_quantile(2, 2) < 0.5
    assert score.beta_quantile(1.28, 2.72) == pytest.approx(0.123, abs=0.01)  # panel's cold-start check


def test_principal_with_no_outcomes_equals_global():
    t = fit([Attempt("e1", OK, "good")] * 30)["e1"]
    assert score.personal(t, 0, 0, 8) == (t.alpha, t.beta)


def test_kappa_caps_global_once_principal_has_outcomes():
    t = fit([Attempt("e1", OK, "good")] * 100)["e1"]
    a, b = score.personal(t, 0, 3, 8)
    assert a + b == pytest.approx(8 + 3)
    assert a / (a + b) < t.q_mean - 0.2  # three own bad outcomes visibly move a strong global score


def test_vet402_classification_on_real_rows():
    rows = list(csv.DictReader((config.ROOT / "data" / "vet402_xrpl.csv").open()))
    kinds = [score.classify_vet402(r) for r in rows]
    assert {"good", "bad", "rail_fail", "rejected"} <= set(kinds)
    assert kinds.count("good") >= 60

from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest

from eval import personalization as study
from plumb.core import config
from plumb.recommendation import rank, relevance
from plumb.core.models import Endpoint
from plumb.recommendation.recommender import HybridRecommender
from plumb.recommendation.score import Trust

pytestmark = pytest.mark.p0


@pytest.fixture
def base():
    cfg = config.load()
    endpoints = {e: Endpoint(e, f"https://{e}.example", "GET", e, e, "", (),
                             Decimal("0.001"), None, None, 5, True) for e in "abcd"}
    trust = {e: Trust(1, True, 4, 1, .8, .6, 0, 1000) for e in endpoints}
    rec = HybridRecommender(cfg, endpoints, trust, {"a": {"b": 1.0}}, {}, Decimal("1"), {}, {})
    fit = {"test": {"need": "test", "labels": {e: {"p_fit": .9, "label": "exact"} for e in endpoints}}}
    return rank.Ranker(rec, fit, relevance.Vectors([], np.empty((0, 1))), relevance.Lexical({}))


def test_labels_do_not_depend_on_ranker_quality(base):
    ep, tr = base.rec.endpoints["a"], base.rec.trust["a"]
    prefs = {"max_latency_ms": 500, "slow_penalty": .2}
    assert study.probability(ep, tr, prefs, 5000) == .2
    assert study.probability(ep, replace(tr, q_mean=.01, q_lo=.001), prefs, 5000) == .2
    assert study.probability(ep, tr, {}, 5000) == 1
    assert study.probability(ep, replace(tr, latency_ms=None), prefs, 5000) == .2


def test_unseen_operators_are_disjoint_and_reproducible(base):
    pool = set(base.rec.endpoints)
    train, test = study.operator_split(base.rec, pool, 3, True)
    assert train and test and not train & test and train | test == pool
    assert (train, test) == study.operator_split(base.rec, pool, 3, True)
    assert study.operator_split(base.rec, pool, 3, False) == (pool, pool)


def test_history_contains_only_training_exposures(base):
    history = study.draw_history(base.rec, {"a", "b"}, {}, 3, "neutral", 17, 5000)
    assert set(history) <= {"a", "b"}
    assert sum(sum(x) for x in history.values()) == 17
    assert all(bad == 0 for good, bad in history.values())
    assert history == study.draw_history(base.rec, {"a", "b"}, {}, 3, "neutral", 17, 5000)
    assert study.draw_history(base.rec, set(), {}, 3, "neutral", 17, 5000) == {}


def test_arms_preserve_constraints_and_isolate_feedback(base):
    history = {"a": [0, 20]}
    arms = {a: study.make_arm(base, history, a, {"a", "b"}) for a in ("global", "personal", "collaborative")}
    assert len({r.rec.principals["sim:eval"].profile for r in arms.values()}) == 1
    assert not arms["global"].rec.principals["sim:eval"].outcomes
    assert arms["personal"].rec.principals["sim:eval"].outcomes == history
    assert not arms["personal"].rec.cooc
    assert arms["collaborative"].rec.cooc == base.rec.cooc
    assert not base.rec.principals and set(base.fit["test"]["labels"]) == set("abcd")
    assert arms["global"].shortlist("test", 1, "sim:eval")["results"][0]["endpoint_id"] == "a"
    assert arms["personal"].shortlist("test", 1, "sim:eval")["results"][0]["endpoint_id"] == "b"


def test_full_comparison_is_offline_repeatable_and_keeps_abstentions(base, monkeypatch):
    import socket

    def refuse(*args, **kwargs):
        raise AssertionError("network used by offline evaluation")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    queries = [{"id": "test", "need": "test"}]
    personas = [{"name": "neutral", "prefs": {}}]
    settings = {"seeds": [0, 1], "scenarios": ["repeat", "unseen_operator"],
                "training_events": 8, "missing_latency_ms": 5000}
    a = study.evaluate(base, queries, personas, settings)
    assert a == study.evaluate(base, queries, personas, settings)
    assert len(a) == 4
    assert all(x[arm]["satisfied"] for x in a for arm in study.ARMS)
    base.dead = set(base.rec.endpoints)
    empty = study.evaluate(base, queries, personas, settings)
    assert len(empty) == 4
    assert all(x[arm]["endpoint"] is None and x[arm]["satisfied"] == 0 for x in empty for arm in study.ARMS)

import pytest

from plumb.core import config
from plumb.recommendation import principals, rank

pytestmark = pytest.mark.p0
CFG = config.load()
ROOT = config.ROOT / "data"


@pytest.fixture(scope="module")
def ranker():
    return rank.load(CFG, ROOT)


def ids(out):
    return [x["endpoint_id"] for x in out["results"]]


def test_personas_get_different_top3_somewhere(ranker):
    differ = [v["need"] for v in ranker.fit.values()
              if ids(ranker.shortlist(v["need"], principal="sim:trading-bot")) != ids(ranker.shortlist(v["need"], principal="sim:research-agent"))]
    assert differ, "personalisation changed nothing"


def test_persona_outcomes_are_labelled_and_reproducible():
    a, b = rank.load(CFG, ROOT), rank.load(CFG, ROOT)
    pa, pb = a.rec.principals["sim:trading-bot"], b.rec.principals["sim:trading-bot"]
    assert pa.source == "simulated" and pa.outcomes and pa.outcomes == pb.outcomes


def test_xrp_only_ledger_principal_is_never_offered_rlusd(ranker):
    xrp_only = [p for p in ranker.rec.principals.values() if p.source == "ledger" and p.profile.assets == ("XRP",)]
    assert xrp_only, "expected a real XRP-only account in data/principals.json"
    for v in ranker.fit.values():
        for x in ranker.shortlist(v["need"], principal=xrp_only[0].addr)["results"]:
            assert x["price"]["asset"] == "XRP"


def test_rlusd_only_persona_is_never_offered_xrp(ranker):
    for v in ranker.fit.values():
        for x in ranker.shortlist(v["need"], principal="sim:trading-bot")["results"]:
            assert x["price"]["asset"] == "RLUSD"


def test_ledger_principals_load_from_snapshot():
    ps = principals.load_ledger_principals(ROOT / "principals.json")
    assert ps and all(p.source == "ledger" and p.addr.startswith("r") for p in ps.values())

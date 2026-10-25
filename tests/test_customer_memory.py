import copy
import json
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from plumb import config, db, outcomes, rank
from plumb.models import Profile
from plumb.recommender import Principal

pytestmark = pytest.mark.p0
CFG = config.load()
NEED = "Current BTC perpetual futures funding rate on major exchanges"


@pytest.fixture(scope="module")
def base():
    return rank.load(CFG, config.ROOT / "data", with_principals=False)


def case(base, tmp_path):
    rk = copy.deepcopy(base)
    rk.rec.principals["sim:fast"] = Principal("sim:fast", "Fast shopper", Profile(), "simulated")
    conn = db.connect(tmp_path / "memory.sqlite")
    out = rk.shortlist(NEED, principal="sim:fast")
    outcomes.save_shortlist(conn, out, NEED, datetime.now(timezone.utc))
    return rk, conn, out


def report(rk, conn, out, **overrides):
    args = dict(shortlist_id=out["shortlist_id"], endpoint_id=out["results"][0]["endpoint_id"], verdict="bad")
    return outcomes.report(conn, rk, None, CFG, **(args | overrides))


def signature(out):
    return [(r["endpoint_id"], r["cost_per_good_rlusd"], r["trust"]) for r in out["results"]]


def test_accepted_customer_feedback_is_saved_with_its_provenance(base, tmp_path):
    rk, conn, out = case(base, tmp_path)
    assert report(rk, conn, out)["accepted"]
    rows = conn.execute("SELECT principal, endpoint, verdict, source FROM principal_outcome").fetchall()
    assert [tuple(row) for row in rows] == [("sim:fast", out["results"][0]["endpoint_id"], "bad", "simulated")]
    assert conn.execute("SELECT label, source FROM principal").fetchone()["source"] == "simulated"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_retry_of_one_feedback_does_not_teach_twice(base, tmp_path):
    rk, conn, out = case(base, tmp_path)
    assert report(rk, conn, out)["accepted"]
    once = signature(rk.shortlist(NEED, principal="sim:fast"))
    again = report(rk, conn, out)
    assert again["accepted"]
    assert signature(rk.shortlist(NEED, principal="sim:fast")) == once
    assert conn.execute("SELECT COUNT(*) FROM principal_outcome").fetchone()[0] == 1


def test_report_cannot_replace_the_shortlists_customer(base, tmp_path):
    rk, conn, out = case(base, tmp_path)
    result = report(rk, conn, out, principal="sim:someone-else")
    assert not result["accepted"]
    assert "sim:someone-else" not in rk.rec.principals
    assert conn.execute("SELECT COUNT(*) FROM principal_outcome").fetchone()[0] == 0


def test_failed_payment_lookup_does_not_partially_change_memory(base, tmp_path):
    rk, conn, out = case(base, tmp_path)
    before = signature(rk.shortlist(NEED, principal="sim:fast"))

    class UnavailableLedger:
        def tx(self, tx):
            raise RuntimeError("RPC unavailable")

    with pytest.raises(RuntimeError, match="RPC unavailable"):
        outcomes.report(conn, rk, UnavailableLedger(), CFG, shortlist_id=out["shortlist_id"],
                        endpoint_id=out["results"][0]["endpoint_id"], verdict="bad", payment_tx="existing-payment")
    assert signature(rk.shortlist(NEED, principal="sim:fast")) == before
    assert conn.execute("SELECT COUNT(*) FROM principal_outcome").fetchone()[0] == 0


def test_fresh_process_restores_memory_and_leaves_another_customer_unchanged(base, tmp_path):
    rk, conn, out = case(base, tmp_path)
    before_other = signature(rk.shortlist(NEED, principal="sim:control"))
    before_global = copy.deepcopy(rk.rec.trust)
    report(rk, conn, out)
    after = signature(rk.shortlist(NEED, principal="sim:fast"))
    assert after[0][0] != out["results"][0]["endpoint_id"]
    assert rk.rec.trust == before_global
    conn.close()
    script = """
import json, sys
from plumb import config, db, rank
c = db.connect(sys.argv[1])
r = rank.load(config.load(), config.ROOT / 'data', with_principals=False, conn=c)
def signature(p):
    return [(x['endpoint_id'], x['cost_per_good_rlusd'], x['trust']) for x in r.shortlist(sys.argv[2], principal=p)['results']]
print(json.dumps([signature('sim:fast'), signature('sim:control'), signature('sim:fast')]))
"""
    loaded = json.loads(subprocess.check_output([sys.executable, "-c", script, str(tmp_path / "memory.sqlite"), NEED], text=True))
    assert loaded == json.loads(json.dumps([after, before_other, after]))


def test_conflicting_retry_is_rejected_without_changing_the_customer(base, tmp_path):
    rk, conn, out = case(base, tmp_path)
    report(rk, conn, out)
    after = signature(rk.shortlist(NEED, principal="sim:fast"))
    assert not report(rk, conn, out, verdict="good")["accepted"]
    assert signature(rk.shortlist(NEED, principal="sim:fast")) == after


def test_storage_failure_rolls_back_and_does_not_change_ranking(base, tmp_path):
    rk, conn, out = case(base, tmp_path)
    before = signature(out)
    conn.execute("CREATE TRIGGER fail_memory BEFORE INSERT ON principal_outcome BEGIN SELECT RAISE(ABORT, 'disk failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match="disk failed"):
        report(rk, conn, out)
    assert signature(rk.shortlist(NEED, principal="sim:fast")) == before
    assert conn.execute("SELECT COUNT(*) FROM principal").fetchone()[0] == 0


def test_export_restore_preserves_exact_profile_and_deduplicates(base, tmp_path):
    from plumb import memory
    rk, conn, out = case(base, tmp_path)
    rk.rec.principals["sim:fast"].profile = Profile(max_price_rlusd=Decimal("0.020000000000000001"))
    report(rk, conn, out)
    event = memory.export_events(conn, "sim:fast")[0]
    assert event["principal"]["profile"]["max_price_rlusd"] == "0.020000000000000001"
    target = db.connect(tmp_path / "restored.sqlite")
    assert memory.restore_event(target, rk.rec, event)
    assert not memory.restore_event(target, rk.rec, event)
    restored = memory.load_principal(target, "sim:fast")
    assert restored.profile.max_price_rlusd == Decimal("0.020000000000000001")
    assert restored.outcomes[out["results"][0]["endpoint_id"]] == [0, 1]
    assert memory.load_principal(target, "sim:control") is None


def test_legacy_database_upgrade_retains_existing_customer_outcome(tmp_path):
    path = tmp_path / "legacy.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE principal_outcome(id INTEGER PRIMARY KEY, principal TEXT, endpoint TEXT, verdict TEXT, latency_ms INTEGER, at TEXT, source TEXT)")
    conn.execute("INSERT INTO principal_outcome VALUES (1, 'old', 'old-endpoint', 'good', NULL, 'old-time', 'report')")
    conn.commit()
    conn.close()
    upgraded = db.connect(path)
    row = upgraded.execute("SELECT * FROM principal_outcome").fetchone()
    assert row["id"] == 1 and row["verdict"] == "good" and row["shortlist_id"] is None


def test_other_request_cannot_commit_a_failed_reports_memory(base, tmp_path, monkeypatch):
    from plumb import memory
    rk, conn, first = case(base, tmp_path)
    other = rk.shortlist(NEED, principal="sim:control")
    outcomes.save_shortlist(conn, other, NEED, datetime.now(timezone.utc))
    conn.execute("CREATE TRIGGER fail_proof BEFORE INSERT ON outcome_report BEGIN SELECT RAISE(ABORT, 'proof failed'); END")
    inserted, attempted, finished = threading.Event(), threading.Event(), threading.Event()
    original = memory.record_outcome

    def pause_first(*args, **kwargs):
        added = original(*args, **kwargs)
        if kwargs["shortlist_id"] == first["shortlist_id"]:
            inserted.set()
            assert attempted.wait(5)
            finished.wait(0.3)  # the second request must wait for the first transaction
        return added

    class Ledger:
        def tx(self, _):
            return {"tx": {"Account": "sim:fast"}}

        def account_created(self, _):
            return {}

    monkeypatch.setattr(memory, "record_outcome", pause_first)
    monkeypatch.setattr(outcomes, "check_payment", lambda *a, **kw: [{"check": "fixture", "ok": True}])

    def fail_first():
        with pytest.raises(sqlite3.IntegrityError, match="proof failed"):
            outcomes.report(conn, rk, Ledger(), CFG, shortlist_id=first["shortlist_id"],
                            endpoint_id=first["results"][0]["endpoint_id"], verdict="bad", payment_tx="proof")

    def save_other():
        assert inserted.wait(5)
        attempted.set()
        try:
            assert report(rk, conn, other)["accepted"]
        finally:
            finished.set()

    with ThreadPoolExecutor(2) as pool:
        a, b = pool.submit(fail_first), pool.submit(save_other)
        a.result(timeout=10)
        b.result(timeout=10)
    rows = conn.execute("SELECT principal FROM principal_outcome").fetchall()
    assert [r["principal"] for r in rows] == ["sim:control"]
    assert rk.rec.principals["sim:fast"].outcomes == {}


def test_retired_endpoint_history_is_retained_but_excluded_from_scoring(base, tmp_path):
    rk, conn, out = case(base, tmp_path)
    assert report(rk, conn, out, verdict="good")["accepted"]
    retired = out["results"][0]["endpoint_id"]
    rk.rec.endpoints.pop(retired)
    for need in rk.fit.values():
        need["labels"].pop(retired, None)
    assert rk.shortlist(NEED, principal="sim:fast")["results"]
    assert retired not in rk.rec.principals["sim:fast"].outcomes
    assert conn.execute("SELECT endpoint FROM principal_outcome").fetchone()[0] == retired


def test_cli_recommendation_loads_and_records_customer_memory(base, tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    from plumb import cli, relevance
    rk, conn, out = case(base, tmp_path)
    assert report(rk, conn, out, verdict="good")["accepted"]
    conn.close()
    monkeypatch.setattr(cli, "_load_env", lambda _: None)
    monkeypatch.setattr(cli, "_cold_judge", lambda _: None)
    monkeypatch.setattr(relevance, "Titan", lambda _: SimpleNamespace(embed=None))
    cli.main(["recommend", NEED, "--as", "sim:fast", "--db", str(tmp_path / "memory.sqlite")])
    result = json.loads(capsys.readouterr().out)
    assert result["results"][0]["trust"]["n_personal"] == 1
    reopened = db.connect(tmp_path / "memory.sqlite")
    assert reopened.execute("SELECT principal FROM shortlist WHERE id=?", (result["shortlist_id"],)).fetchone()[0] == "sim:fast"


def test_mcp_tools_restore_feedback_in_a_new_ranker(base, tmp_path, monkeypatch):
    from plumb import mcp_server
    conn = db.connect(tmp_path / "tools.sqlite")
    monkeypatch.setattr(mcp_server, "CONN", conn)
    monkeypatch.setattr(mcp_server, "RANKER", rank.load(CFG, config.ROOT / "data", with_principals=False, conn=conn))
    initial = mcp_server.recommend(NEED, principal="sim:mcp")
    first = initial["results"][0]["endpoint_id"]
    assert mcp_server.report_outcome(initial["shortlist_id"], first, "bad")["persisted"]
    monkeypatch.setattr(mcp_server, "RANKER", rank.load(CFG, config.ROOT / "data", with_principals=False, conn=conn))
    assert mcp_server.recommend(NEED, principal="sim:mcp")["results"][0]["endpoint_id"] != first
    assert mcp_server.recommend(NEED, principal="sim:other")["results"][0]["endpoint_id"] == first

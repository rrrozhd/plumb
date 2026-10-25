"""The stage demo proves persisted customer memory, not personalization uplift."""
import importlib
import json
from decimal import Decimal

import pytest

from plumb.core import config

pytestmark = pytest.mark.p0


def demo_module():
    return importlib.import_module("plumb.interfaces.memory_demo")


def comparable(rows):
    return [(r["endpoint_id"], r["cost_per_good_rlusd"], r["trust"]) for r in rows]


def test_memory_survives_new_worker_and_leaves_control_unchanged(tmp_path):
    demo = demo_module()
    with demo.Controller(tmp_path / "demo.sqlite") as controller:
        initial = controller.request("state")
        assert initial["counts"] == {"shopper": 0, "control": 0}
        assert comparable(initial["current"]["shopper"]) == comparable(initial["current"]["control"])
        assert initial["historical"]["url"] == initial["baseline"]["shopper"][0]["url"]
        assert initial["historical"]["verdict"] == "good"
        assert initial["historical"]["ms"] > initial["max_latency_ms"]
        taught = controller.request("teach")
        assert taught["counts"] == {"shopper": 1, "control": 0}
        assert taught["feedback"]["scope"] == "principal"
        assert taught["learned"]["n_personal"] == 1
        assert taught["learned"]["q_mean"] < taught["learned"]["before_q_mean"]
        assert taught["current"]["shopper"][0]["endpoint_id"] != initial["current"]["shopper"][0]["endpoint_id"]
        assert comparable(taught["current"]["control"]) == comparable(initial["current"]["control"])
        again = controller.request("teach")
        assert again["counts"] == taught["counts"]
        prior_pid = taught["worker_pid"]
        reloaded = controller.reload()
        assert reloaded["worker_pid"] != prior_pid
        assert reloaded["counts"] == taught["counts"]
        assert comparable(reloaded["current"]["shopper"]) == comparable(taught["current"]["shopper"])
        assert comparable(reloaded["current"]["control"]) == comparable(initial["current"]["control"])
        assert reloaded["global_unchanged"]
        old_session = reloaded["session"]
        fresh = controller.request("fresh")
        assert fresh["session"] != old_session
        assert fresh["counts"] == {"shopper": 0, "control": 0}
        assert comparable(fresh["current"]["shopper"]) == comparable(initial["current"]["shopper"])
    with demo.Controller(tmp_path / "demo.sqlite") as restarted:
        assert restarted.request("state")["session"] == fresh["session"]


def test_demo_refuses_production_database():
    demo = demo_module()
    with pytest.raises(ValueError, match="production database"):
        demo.Controller(config.path(config.load(), "db"))


def test_quicknode_missing_config_never_falls_back(monkeypatch):
    demo = demo_module()
    monkeypatch.delenv("QUICKNODE_HTTP_URL", raising=False)
    monkeypatch.setattr(demo.ledger, "rpc_url", lambda cfg: "https://public.example")
    monkeypatch.setattr(demo.ledger, "Ledger", lambda cfg: pytest.fail("must not make a request"))
    out = demo.verify_payment({}, config.load())
    assert not out["verified"]
    assert "configured" in out["error"]


@pytest.mark.parametrize("amount,merchant,expected", [("0.002", "merchant", True), ("0.001", "merchant", False), ("0.002", "other", False)])
def test_verification_compares_historical_receipt_without_satisfaction(monkeypatch, amount, merchant, expected):
    demo = demo_module()
    url = "https://demo.quiknode.pro/SECRET/"
    monkeypatch.setenv("QUICKNODE_HTTP_URL", url)
    monkeypatch.setattr(demo.ledger, "rpc_url", lambda cfg: url)
    cfg = config.load()
    entry = {"validated": True, "tx": {"hash": "A" * 64, "TransactionType": "Payment", "InvoiceID": "B" * 64,
             "Account": "payer", "Destination": merchant, "date": 1, "ledger_index": 42},
             "meta": {"TransactionResult": "tesSUCCESS", "delivered_amount": {
                 "currency": cfg["xrpl"]["rlusd_currency"], "issuer": cfg["xrpl"]["rlusd_issuer"], "value": amount}}}
    class FakeLedger:
        def __init__(self, cfg):
            pass

        def tx(self, tx):
            assert tx == "A" * 64
            return entry
    monkeypatch.setattr(demo.ledger, "Ledger", FakeLedger)
    historical = {"tx": "A" * 64, "payto": "merchant", "spent": "0.002"}
    out = demo.verify_payment(historical, cfg)
    assert out["verified"] is expected
    assert "satisfaction" not in out
    assert "SECRET" not in json.dumps(out)
    if expected:
        assert Decimal(out["payment"]["amount"]) == Decimal("0.002")


def test_verification_error_does_not_leak_provider_url(monkeypatch):
    demo = demo_module()
    url = "https://demo.quiknode.pro/SECRET/"
    monkeypatch.setenv("QUICKNODE_HTTP_URL", url)
    monkeypatch.setattr(demo.ledger, "rpc_url", lambda cfg: url)
    class BrokenLedger:
        def __init__(self, cfg):
            raise RuntimeError(url)
    monkeypatch.setattr(demo.ledger, "Ledger", BrokenLedger)
    out = demo.verify_payment({"tx": "A" * 64}, config.load())
    assert not out["verified"]
    assert "SECRET" not in json.dumps(out)

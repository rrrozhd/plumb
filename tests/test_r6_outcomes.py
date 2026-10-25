import copy
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from plumb import config, ledger, outcomes

pytestmark = pytest.mark.p0
CFG = config.load()
ENTRY = json.loads((Path(__file__).parent / "fixtures" / "account_tx_x402.json").read_text())[0]
PAY = ledger.parse_payment(ENTRY, CFG)
assert PAY is not None
AT = datetime.fromisoformat(PAY["close_time"])
OLD = {"created_at": (AT - timedelta(days=90)).isoformat()}


def run(entry=ENTRY, created=OLD, principal=PAY["payer"], payto=PAY["payto"], after=AT - timedelta(minutes=5),
        invoice_id=None, used=False, min_amount=None):
    checks = outcomes.check_payment(copy.deepcopy(entry), created, cfg=CFG, principal=principal, payto=payto,
                                    min_amount=min_amount, after=after, invoice_id=invoice_id, used=used)
    return {c["check"]: c["ok"] for c in checks}


def test_a_genuine_post_shortlist_payment_passes():
    assert all(run().values())


@pytest.mark.parametrize("kw,failing", [
    ({"after": AT + timedelta(minutes=5)}, "after the shortlist, within 24 h"),
    ({"after": AT - timedelta(days=2)}, "after the shortlist, within 24 h"),
    ({"payto": "rSomeOtherMerchantXXXXXXXXXXXXXXXX"}, "paid this merchant"),
    ({"principal": "rSomeoneElseXXXXXXXXXXXXXXXXXXXXXX"}, "paid by this principal"),
    ({"used": True}, "payment not used before"),
    ({"created": {"created_at": AT.isoformat()}}, "account older than the shortlist"),
    ({"invoice_id": "not-the-preimage"}, "invoiceId hashes to the on-ledger InvoiceID"),
])
def test_each_failed_check_blocks_global_credit(kw, failing):
    res = run(**kw)
    assert res[failing] is False


def test_correct_preimage_passes():
    e = copy.deepcopy(ENTRY)
    e["tx"]["InvoiceID"] = hashlib.sha256(b"nonce-123").hexdigest().upper()
    assert run(entry=e, invoice_id="nonce-123")["invoiceId hashes to the on-ledger InvoiceID"]


def test_underpayment_fails():
    from decimal import Decimal
    assert run(min_amount=Decimal("1"))["delivered at least the price"] is False


def test_unvalidated_tx_fails_everything_payment_related():
    e = copy.deepcopy(ENTRY)
    e["validated"] = False
    assert run(entry=e)["validated x402 payment"] is False


@pytest.fixture(scope="module")
def ranker():
    from plumb import rank
    return rank.load(CFG, config.ROOT / "data", with_principals=False)


def _shortlisted(ranker, tmp_path, t):
    from plumb import db
    conn = db.connect(tmp_path / "t.db")
    out = ranker.shortlist(ranker.fit[t]["need"], principal=None)
    outcomes.save_shortlist(conn, out, ranker.fit[t]["need"], AT - timedelta(minutes=5))
    return conn, out


class _Ledger:
    def tx(self, h):
        return ENTRY

    def account_created(self, a):
        return OLD


def test_unproven_wrong_answer_changes_nothing(ranker, tmp_path):
    t = next(t for t, v in ranker.fit.items() if any(x["p_fit"] >= 0.5 for x in v["labels"].values()))
    conn, out = _shortlisted(ranker, tmp_path, t)
    e = out["results"][0]["endpoint_id"]
    before = ranker.fit[t]["labels"][e]["p_fit"]
    r = outcomes.report(conn, ranker, _Ledger(), CFG, shortlist_id=out["shortlist_id"], endpoint_id=e, verdict="wrong_answer")
    assert not r["accepted"] and ranker.fit[t]["labels"][e]["p_fit"] == before


def test_proven_wrong_answer_lowers_fit_only_for_the_shortlists_need(ranker, tmp_path, monkeypatch):
    shared = next((e, [t for t, v in ranker.fit.items() if e in v["labels"]]) for e in ranker.rec.endpoints
                  if sum(e in v["labels"] for v in ranker.fit.values()) >= 2)
    e, (first, second) = shared[0], shared[1][:2]
    conn, out = _shortlisted(ranker, tmp_path, second)
    out["results"] = [{"endpoint_id": e, "price": {"asset": "XRP", "amount_rlusd": "0"}}]
    conn.execute("UPDATE shortlist SET results = ?", (json.dumps(out["results"]),))
    monkeypatch.setattr(outcomes, "check_payment", lambda *a, **k: [{"check": "stub", "ok": True}])
    keep = ranker.fit[first]["labels"][e]["p_fit"]
    r = outcomes.report(conn, ranker, _Ledger(), CFG, shortlist_id=out["shortlist_id"], endpoint_id=e,
                        verdict="wrong_answer", principal=PAY["payer"], payment_tx="TX")
    assert r["accepted"] and ranker.fit[second]["labels"][e]["p_fit"] == float(CFG["judge"]["p_fit"]["wrong"])
    assert ranker.fit[first]["labels"][e]["p_fit"] == keep

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

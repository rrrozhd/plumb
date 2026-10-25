"""A purchase counts only its own signed payment, never another one found in the account's history (audit HIGH 1)."""
import copy
import json
from pathlib import Path

import pytest

from plumb import config, eval_paid, ledger

pytestmark = pytest.mark.p0
CFG = config.load()
ENTRY = json.loads((Path(__file__).parent / "fixtures" / "account_tx_x402.json").read_text())[0]
PAY = ledger.parse_payment(ENTRY, CFG)


class _Ledger:
    def __init__(self, by_hash):
        self.by_hash = by_hash

    def tx(self, h):
        return copy.deepcopy(self.by_hash.get(h, {"validated": False}))

    def rpc(self, *a, **k):
        raise AssertionError("must not search account history")


def test_own_payment_is_found_by_its_hash():
    lg = _Ledger({"MINE": ENTRY})
    assert eval_paid.settled_on_ledger(lg, CFG, PAY["payer"], PAY["payto"], PAY["invoice_id"].upper(), "MINE") == PAY


def test_a_matching_older_payment_does_not_count(monkeypatch):
    monkeypatch.setattr(eval_paid.time, "sleep", lambda s: None)
    lg = _Ledger({"OLD": ENTRY})  # same payer, payTo and static InvoiceID, but not this purchase's tx
    assert eval_paid.settled_on_ledger(lg, CFG, PAY["payer"], PAY["payto"], PAY["invoice_id"].upper(), "MINE") is None

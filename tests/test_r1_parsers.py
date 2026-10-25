import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from plumb import catalog, config, ledger

pytestmark = pytest.mark.p0
FIX = Path(__file__).parent / "fixtures"
CFG = config.load()


def listing():
    return json.loads((FIX / "listing_multi.json").read_text())


def test_multi_network_listing_takes_the_xrpl_rlusd_option():
    e = catalog.parse_listing(listing(), CFG)
    assert e is not None
    assert e.payto.startswith("r") and e.price_rlusd == Decimal("0.003")
    assert isinstance(e.price_xrp_drops, int) and e.price_xrp_drops > 0
    assert e.source_tag == 804681468 and e.method == "POST" and e.has_output_schema and e.output_fields > 0
    assert e.id == catalog.endpoint_id(e.url, "POST")


def test_xrp_only_listing():
    res = listing()
    res["accepts"] = [a for a in res["accepts"] if a["network"] == "xrpl:0" and a["asset"] == "XRP"]
    e = catalog.parse_listing(res, CFG)
    assert e is not None and e.price_rlusd is None and e.price_xrp_drops == 2310


def test_listing_without_xrpl_or_with_fake_issuer_is_skipped():
    res = listing()
    res["accepts"] = [a for a in res["accepts"] if a["network"] != "xrpl:0"]
    assert catalog.parse_listing(res, CFG) is None
    res = listing()
    res["accepts"] = [copy.deepcopy(a) for a in res["accepts"] if a["network"] == "xrpl:0" and a["asset"] != "XRP"]
    res["accepts"][0]["extra"]["issuer"] = "rFakeIssuerXXXXXXXXXXXXXXXXXXXXXXX"
    assert catalog.parse_listing(res, CFG) is None


def entries():
    return json.loads((FIX / "account_tx_x402.json").read_text())


def test_payment_parser_uses_delivered_amount():
    p = ledger.parse_payment(entries()[0], CFG)
    assert p is not None
    assert p["asset"] == "RLUSD" and p["amount"] == "0.003" and p["source_tag"] == 804681468
    assert p["invoice_id"] and p["payer"] != p["payto"] and p["close_time"].startswith("20")


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(validated=False),
    lambda e: e["meta"].update(TransactionResult="tecPATH_PARTIAL"),
    lambda e: e["tx"].pop("InvoiceID"),
    lambda e: e["meta"].update(delivered_amount={"currency": "USD", "issuer": "rX", "value": "1"}),
])
def test_payment_parser_rejects_non_x402_or_unvalidated(mutate):
    e = entries()[0]
    mutate(e)
    assert ledger.parse_payment(e, CFG) is None


def test_xrp_delivered_amount_is_drops():
    e = entries()[0]
    e["meta"]["delivered_amount"] = "2310"
    p = ledger.parse_payment(e, CFG)
    assert p is not None
    assert p["asset"] == "XRP" and p["amount"] == "2310"

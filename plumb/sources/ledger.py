"""Settlement adapter for XRPL (RECOMMENDER §1b): read-only JSON-RPC through Quicknode.

The Quicknode URL embeds a token, so it is read from env/ledger.env (AGENTS.md rule 5) and never logged.
"""
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx

from plumb.core import money
from plumb.core.config import ROOT

RIPPLE_EPOCH = 946684800


def rpc_url(cfg: dict) -> str:
    env = Path(ROOT / "env" / "ledger.env")
    if "QUICKNODE_HTTP_URL" not in os.environ and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("QUICKNODE_HTTP_URL="):
                os.environ["QUICKNODE_HTTP_URL"] = line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("QUICKNODE_HTTP_URL") or cfg["xrpl"]["rpc_url"]


def ripple_time(t: int) -> datetime:
    return datetime.fromtimestamp(t + RIPPLE_EPOCH, tz=timezone.utc)


def parse_payment(entry: dict, cfg: dict) -> dict | None:
    """An account_tx entry -> an x402-like payment, or None.

    Counts only validated tesSUCCESS Payments carrying an InvoiceID (the x402 marker, SPEC §11 Q9);
    the amount is meta.delivered_amount, never Amount (AGENTS.md rule 3)."""
    tx, meta = entry.get("tx") or entry.get("tx_json") or {}, entry.get("meta") or {}
    if not entry.get("validated") or meta.get("TransactionResult") != "tesSUCCESS":
        return None
    if tx.get("TransactionType") != "Payment" or not tx.get("InvoiceID"):
        return None
    delivered = meta.get("delivered_amount")
    if isinstance(delivered, str):
        asset, amount = "XRP", Decimal(money.xrp_drops(delivered))
    elif isinstance(delivered, dict) and delivered.get("currency") == cfg["xrpl"]["rlusd_currency"] \
            and delivered.get("issuer") == cfg["xrpl"]["rlusd_issuer"]:
        asset, amount = "RLUSD", money.rlusd(delivered["value"])
    else:
        return None
    if amount <= 0:
        return None
    return {"tx_hash": tx.get("hash") or entry.get("hash"), "ledger_index": tx.get("ledger_index") or entry.get("ledger_index"),
            "close_time": ripple_time(tx["date"]).isoformat(), "payer": tx["Account"], "payto": tx["Destination"],
            "asset": asset, "amount": str(amount), "invoice_id": tx["InvoiceID"], "source_tag": tx.get("SourceTag")}


class Ledger:
    def __init__(self, cfg: dict, client: httpx.Client | None = None):
        self.cfg, self.url = cfg, rpc_url(cfg)
        self.http = client or httpx.Client(timeout=30)

    def rpc(self, method: str, **params) -> dict:
        for attempt in range(3):
            try:
                r = self.http.post(self.url, json={"method": method, "params": [params]})
                r.raise_for_status()
                result = r.json()["result"]
                if result.get("status") == "error":
                    raise RuntimeError(f"{method}: {result.get('error')}")
                return result
            except (httpx.HTTPError, KeyError):
                if attempt == 2:
                    raise RuntimeError(f"{method} failed after 3 attempts") from None
        raise AssertionError("unreachable")

    def payments_to(self, payto: str, max_txs: int = 2000) -> list[dict]:
        """x402-like payments received by one merchant account, newest first."""
        out, marker, seen = [], None, 0
        while seen < max_txs:
            res = self.rpc("account_tx", account=payto, limit=min(400, max_txs - seen), ledger_index_min=-1,
                           ledger_index_max=-1, **({"marker": marker} if marker else {}))
            txs = res.get("transactions", [])
            seen += len(txs)
            out += [p for p in (parse_payment(t, self.cfg) for t in txs) if p and p["payto"] == payto]
            marker = res.get("marker")
            if not marker or not txs:
                break
        return out

    def account_created(self, addr: str) -> dict | None:
        """The creating transaction of an account (SPEC §11 Q7): ledger, time and funder."""
        res = self.rpc("account_tx", account=addr, forward=True, limit=1, ledger_index_min=-1, ledger_index_max=-1)
        txs = res.get("transactions", [])
        if not txs:
            return None
        tx = txs[0].get("tx") or txs[0].get("tx_json") or {}
        return {"addr": addr, "created_ledger": tx.get("ledger_index"), "created_at": ripple_time(tx["date"]).isoformat(),
                "funded_by": tx.get("Account") if tx.get("Destination") == addr else None}

    def xrp_in_rlusd(self) -> Decimal:
        """XRP/RLUSD mid price from the DEX order book (eval/rubric.md §1.2)."""
        x = self.cfg["xrpl"]
        rl = {"currency": x["rlusd_currency"], "issuer": x["rlusd_issuer"]}
        bids = self.rpc("book_offers", taker_gets={"currency": "XRP"}, taker_pays=rl, limit=1)["offers"]
        asks = self.rpc("book_offers", taker_gets=rl, taker_pays={"currency": "XRP"}, limit=1)["offers"]
        # Best offer on each side of the book, each as RLUSD per XRP; the mid is their average.
        a = Decimal(bids[0]["TakerPays"]["value"]) / (Decimal(bids[0]["TakerGets"]) / money.DROPS_PER_XRP)
        b = Decimal(asks[0]["TakerGets"]["value"]) / (Decimal(asks[0]["TakerPays"]) / money.DROPS_PER_XRP)
        return (a + b) / 2

    def tx(self, tx_hash: str) -> dict:
        """One transaction in account_tx entry shape ({tx, meta, validated}) so parse_payment applies."""
        r = self.rpc("tx", transaction=tx_hash, binary=False)
        tx = r.get("tx_json") or {k: v for k, v in r.items() if k not in ("meta", "validated")}
        tx.setdefault("hash", r.get("hash", tx_hash))
        tx.setdefault("ledger_index", r.get("ledger_index"))
        if "date" not in tx and "close_time_iso" in r:
            tx["date"] = int(datetime.fromisoformat(r["close_time_iso"].replace("Z", "+00:00")).timestamp()) - RIPPLE_EPOCH
        return {"tx": tx, "meta": r.get("meta", {}), "validated": r.get("validated", False)}

    def account_lines(self, addr: str) -> list[dict]:
        return self.rpc("account_lines", account=addr, ledger_index="validated").get("lines", [])

    def account_info(self, addr: str) -> dict:
        return self.rpc("account_info", account=addr, ledger_index="validated").get("account_data", {})

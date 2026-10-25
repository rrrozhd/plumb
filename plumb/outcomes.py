"""Outcome reports (RECOMMENDER §5): every report personalises; only a proven one moves global trust.

A report counts globally only if its payment is a validated tesSUCCESS Payment from the principal to the endpoint's
payTo, delivering at least the listed price, after the shortlist and within 24 h, never used before, from an account
older than the shortlist, and (when given) whose invoiceId hashes to the on-ledger InvoiceID.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal

from plumb import ledger as L
from plumb.models import Profile
from plumb.recommender import Principal
from plumb.rank import Ranker

VERDICTS = ("good", "bad", "wrong_answer")


def check_payment(entry: dict | None, created: dict | None, *, cfg: dict, principal: str, payto: str,
                  min_amount: Decimal | None, after: datetime, invoice_id: str | None, used: bool) -> list[dict]:
    """Pure: the list of {check, ok} for one payment. `entry` is a tx in account_tx shape; `created` its payer's creation."""
    p = L.parse_payment(entry, cfg) if entry else None
    at = datetime.fromisoformat(p["close_time"]) if p else None
    checks = [
        ("validated x402 payment", p is not None),
        ("paid by this principal", bool(p) and p["payer"] == principal),
        ("paid this merchant", bool(p) and p["payto"] == payto),
        ("delivered at least the price", bool(p) and (min_amount is None or p["asset"] != "RLUSD" or Decimal(p["amount"]) >= min_amount)),
        ("after the shortlist, within 24 h", bool(at) and after <= at <= after + timedelta(hours=24)),
        ("payment not used before", not used),
        ("account older than the shortlist", bool(created) and datetime.fromisoformat(created["created_at"]) < after),
    ]
    if invoice_id is not None:
        checks.append(("invoiceId hashes to the on-ledger InvoiceID",
                       bool(p) and hashlib.sha256(invoice_id.encode()).hexdigest().upper() == p["invoice_id"].upper()))
    return [{"check": c, "ok": ok} for c, ok in checks]


def save_shortlist(conn: sqlite3.Connection, out: dict, need: str, at: datetime) -> None:
    conn.execute("INSERT INTO shortlist(id, need_hash, need_text, principal, at, results, mode) VALUES (?,?,?,?,?,?,?)",
                 (out["shortlist_id"], hashlib.sha256(out["need_template"].encode()).hexdigest(), need[:1000],
                  out["principal"], at.isoformat(), json.dumps(out["results"]), "demo"))
    conn.commit()


def report(conn: sqlite3.Connection, ranker: Ranker, lg, cfg: dict, *, shortlist_id: str, endpoint_id: str, verdict: str,
           principal: str | None = None, payment_tx: str | None = None, invoice_id: str | None = None) -> dict:
    if verdict not in VERDICTS:
        return {"accepted": False, "error": f"verdict must be one of {VERDICTS}"}
    row = conn.execute("SELECT * FROM shortlist WHERE id = ?", (shortlist_id,)).fetchone()
    if not row:
        return {"accepted": False, "error": "unknown shortlist_id"}
    results = {r["endpoint_id"]: r for r in json.loads(row["results"])}
    if endpoint_id not in results:
        return {"accepted": False, "error": "endpoint not in that shortlist"}
    who = principal or row["principal"]
    rec = ranker.rec
    if verdict == "wrong_answer":  # misrouting is Plumb's error, not the merchant's: lower fit, never trust
        t = next((k for k, v in ranker.fit.items() if endpoint_id in v["labels"]), None)
        if t:
            ranker.fit[t]["labels"][endpoint_id]["p_fit"] = float(cfg["judge"]["p_fit"]["wrong"])
        return {"accepted": True, "scope": "fit", "checks": []}

    if who:
        p = rec.principals.setdefault(who, Principal(who, who, Profile(), "ledger"))
        g, b = p.outcomes.get(endpoint_id, [0.0, 0.0])
        p.outcomes[endpoint_id] = [g + (verdict == "good"), b + (verdict == "bad")]

    checks: list[dict] = []
    if payment_tx and who:
        used = conn.execute("SELECT 1 FROM outcome_report WHERE payment_tx = ?", (payment_tx,)).fetchone() is not None
        entry = lg.tx(payment_tx)
        payer = (entry.get("tx") or {}).get("Account")
        created = lg.account_created(payer) if payer else None
        price = results[endpoint_id]["price"]
        checks = check_payment(entry, created, cfg=cfg, principal=who, payto=rec.endpoints[endpoint_id].payto,
                               min_amount=Decimal(price["amount_rlusd"]) if price["asset"] == "RLUSD" else None,
                               after=datetime.fromisoformat(row["at"]), invoice_id=invoice_id, used=used)
    proven = bool(checks) and all(c["ok"] for c in checks)
    if proven:
        conn.execute("INSERT INTO outcome_report VALUES (?,?,?,?,?,?,?)",
                     (payment_tx, shortlist_id, endpoint_id, who, verdict, datetime.now().isoformat(), 1.0))
        conn.commit()
    return {"accepted": True, "scope": "principal+global" if proven else "principal", "checks": checks}

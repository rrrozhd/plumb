"""Outcome reports: good/bad feedback persists for its customer; payment proofs are stored separately.

A report's payment evidence is stored only if its payment is a validated tesSUCCESS Payment from the principal to the endpoint's
payTo, meeting the RLUSD price check when applicable, after the shortlist and within 24 h, never used before, from an account
older than the shortlist, and (when given) whose invoiceId hashes to the on-ledger InvoiceID.
Stored global report evidence is not yet consumed by the trust fitter.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from plumb.core import db
from plumb.sources import ledger as L
from plumb.customer import memory
from plumb.core.models import Profile
from plumb.recommendation.recommender import Principal
from plumb.recommendation.rank import Ranker

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


@db.serialized
def save_shortlist(conn: sqlite3.Connection, out: dict, need: str, at: datetime) -> None:
    conn.execute("INSERT INTO shortlist(id, need_hash, need_text, principal, at, results, mode) VALUES (?,?,?,?,?,?,?)",
                 (out["shortlist_id"], hashlib.sha256(out["need_template"].encode()).hexdigest(), need[:1000],
                  out["principal"], at.isoformat(), json.dumps(out["results"]), "demo"))
    conn.commit()


@db.serialized
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
    if principal and row["principal"] and principal != row["principal"]:
        return {"accepted": False, "error": "principal does not match this shortlist"}
    rec = ranker.rec

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
    if verdict == "wrong_answer":  # misrouting is Plumb's error, not the merchant's: lower this need's fit, never trust
        if not proven:  # unproven, anyone could knock a rival out of a need
            return {"accepted": False, "error": "wrong_answer needs a proven payment", "checks": checks}
        t = next((k for k in ranker.fit if hashlib.sha256(k.encode()).hexdigest() == row["need_hash"]), None)
        if t and endpoint_id in ranker.fit[t]["labels"]:
            ranker.fit[t]["labels"][endpoint_id]["p_fit"] = float(cfg["judge"]["p_fit"]["wrong"])
        return {"accepted": True, "scope": "fit", "checks": checks}  # outcome_report holds merchant verdicts only
    if not who:
        return {"accepted": False, "error": "a principal is required for customer feedback", "checks": checks}
    ranker.bind_memory(conn)
    p = rec.principals.get(who) or Principal(who, who, Profile(), "simulated" if who.startswith("sim:") else "ledger")
    try:
        with conn:
            added = memory.record_outcome(conn, rec, p, endpoint_id=endpoint_id, verdict=verdict,
                                          shortlist_id=shortlist_id, at=datetime.now(timezone.utc).isoformat(),
                                          source="simulated" if p.source == "simulated" else "report")
            if proven:
                conn.execute("INSERT INTO outcome_report VALUES (?,?,?,?,?,?,?)",
                             (payment_tx, shortlist_id, endpoint_id, who, verdict, datetime.now(timezone.utc).isoformat(), 1.0))
    except ValueError as exc:
        return {"accepted": False, "error": str(exc), "checks": checks}
    ranker.refresh_principal(who)
    return {"accepted": True, "scope": "principal", "persisted": True, "duplicate": not added,
            "global_evidence_stored": proven, "checks": checks}

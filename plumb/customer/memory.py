"""Exact customer feedback in SQLite. Personal reports never train other customers."""
import copy
import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal

from plumb.core import db
from plumb.core.models import Profile
from plumb.recommendation.recommender import HybridRecommender, Principal


def _profile(profile: Profile) -> dict:
    return json.loads(json.dumps(asdict(profile), default=str))


def _principal(row) -> Principal:
    profile = json.loads(row["profile"]) if isinstance(row["profile"], str) else dict(row["profile"])
    price = profile.get("max_price_rlusd")
    if price is not None:
        if not isinstance(price, str):
            raise ValueError("customer price must be a decimal string")
        profile["max_price_rlusd"] = Decimal(price)
        if not profile["max_price_rlusd"].is_finite() or profile["max_price_rlusd"] < 0:
            raise ValueError("invalid customer price")
    assets = profile.get("assets", ["RLUSD", "XRP"])
    if not isinstance(assets, (list, tuple)) or any(a not in ("RLUSD", "XRP") for a in assets):
        raise ValueError("invalid customer assets")
    profile["assets"] = tuple(assets)
    return Principal(row["addr"], row["label"], Profile(**profile), row["source"])


def _save_principal(conn: sqlite3.Connection, p: Principal) -> None:
    conn.execute("INSERT INTO principal(addr,label,profile,source) VALUES (?,?,?,?) "
                 "ON CONFLICT(addr) DO UPDATE SET label=excluded.label,profile=excluded.profile,source=excluded.source",
                 (p.addr, p.label, json.dumps(_profile(p.profile)), p.source))


@db.serialized
def save_principal(conn: sqlite3.Connection, p: Principal) -> None:
    with conn:
        _save_principal(conn, p)


def record_outcome(conn: sqlite3.Connection, rec: HybridRecommender, p: Principal, *, endpoint_id: str,
                   verdict: str, shortlist_id: str, at: str, source: str) -> bool:
    """Caller owns the transaction. An identical retry is a no-op; conflicting feedback is rejected."""
    ep = rec.endpoints[endpoint_id]
    _save_principal(conn, p)
    conn.execute("INSERT OR IGNORE INTO operator(payto) VALUES (?)", (ep.payto,))
    conn.execute("INSERT OR IGNORE INTO endpoint(id,url,method,payto,price_rlusd,price_xrp_drops) VALUES (?,?,?,?,?,?)",
                 (ep.id, ep.url, ep.method, ep.payto, str(ep.price_rlusd) if ep.price_rlusd is not None else None, ep.price_xrp_drops))
    added = conn.execute("INSERT INTO principal_outcome(principal,endpoint,verdict,at,source,shortlist_id) VALUES (?,?,?,?,?,?) "
                         "ON CONFLICT(principal,shortlist_id,endpoint) DO NOTHING",
                         (p.addr, endpoint_id, verdict, at, source, shortlist_id)).rowcount == 1
    if not added:
        previous = conn.execute("SELECT verdict, source FROM principal_outcome WHERE principal=? AND shortlist_id=? AND endpoint=?",
                                (p.addr, shortlist_id, endpoint_id)).fetchone()
        if previous["verdict"] != verdict or previous["source"] != source:
            raise ValueError("this shortlist already has different feedback for that endpoint")
    return added


@db.serialized
def load_principal(conn: sqlite3.Connection, addr: str, baseline: Principal | None = None) -> Principal | None:
    row = conn.execute("SELECT * FROM principal WHERE addr=?", (addr,)).fetchone()
    if row is None:
        return copy.deepcopy(baseline)
    p = _principal(row)
    if baseline:
        p.outcomes, p.operators = copy.deepcopy(baseline.outcomes), copy.deepcopy(baseline.operators)
    for event in conn.execute("SELECT endpoint, verdict FROM principal_outcome WHERE principal=? ORDER BY id", (addr,)):
        g, b = p.outcomes.get(event["endpoint"], [0.0, 0.0])
        p.outcomes[event["endpoint"]] = [g + (event["verdict"] == "good"), b + (event["verdict"] == "bad")]
    return p


@db.serialized
def export_events(conn: sqlite3.Connection, principal: str) -> list[dict]:
    row = conn.execute("SELECT * FROM principal WHERE addr=?", (principal,)).fetchone()
    if row is None:
        return []
    p = {"addr": row["addr"], "label": row["label"], "profile": json.loads(row["profile"]), "source": row["source"]}
    return [{"principal": p, "shortlist_id": r["shortlist_id"], "endpoint_id": r["endpoint"],
             "verdict": r["verdict"], "at": r["at"], "source": r["source"]}
            for r in conn.execute("SELECT * FROM principal_outcome WHERE principal=? AND shortlist_id IS NOT NULL ORDER BY id", (principal,))]


@db.serialized
def restore_event(conn: sqlite3.Connection, rec: HybridRecommender, event: dict) -> bool:
    """Restore explicit feedback, retaining its identity and provenance; never update global trust."""
    p = _principal(event["principal"])
    if not p.addr or not p.label or p.source not in ("ledger", "simulated"):
        raise ValueError("invalid customer identity")
    if event["verdict"] not in ("good", "bad") or event["source"] not in ("report", "simulated"):
        raise ValueError("invalid feedback")
    if p.source == "simulated" and event["source"] != "simulated":
        raise ValueError("simulated customer feedback must remain labelled simulated")
    if not isinstance(event["shortlist_id"], str) or not event["shortlist_id"] or event["endpoint_id"] not in rec.endpoints:
        raise ValueError("unknown endpoint or missing feedback identity")
    if datetime.fromisoformat(event["at"]).tzinfo is None:
        raise ValueError("feedback timestamp must include its timezone")
    with conn:
        return record_outcome(conn, rec, p, endpoint_id=event["endpoint_id"], verdict=event["verdict"],
                              shortlist_id=event["shortlist_id"], at=event["at"], source=event["source"])

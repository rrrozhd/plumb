"""SQLite store (SPEC §2). Invariants that a schema can hold are enforced here, not in application code."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS operator(
  payto TEXT PRIMARY KEY, first_seen TEXT, label TEXT);

CREATE TABLE IF NOT EXISTS endpoint(
  id TEXT PRIMARY KEY, url TEXT NOT NULL, method TEXT NOT NULL,
  payto TEXT NOT NULL REFERENCES operator(payto),
  service_name TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
  price_rlusd TEXT CHECK (price_rlusd IS NULL OR CAST(price_rlusd AS REAL) > 0),
  price_xrp_drops INTEGER CHECK (price_xrp_drops IS NULL OR price_xrp_drops > 0),
  source_tag INTEGER, output_fields INTEGER NOT NULL DEFAULT 0, has_output_schema INTEGER NOT NULL DEFAULT 0,
  bazaar_calls_30d INTEGER, bazaar_payers_30d INTEGER, last_seen TEXT,
  CHECK (price_rlusd IS NOT NULL OR price_xrp_drops IS NOT NULL),
  UNIQUE (url, method));

CREATE TABLE IF NOT EXISTS payment(
  tx_hash TEXT PRIMARY KEY, ledger_index INTEGER NOT NULL, close_time TEXT NOT NULL,
  payer TEXT NOT NULL, payto TEXT NOT NULL, asset TEXT NOT NULL,
  amount TEXT NOT NULL CHECK (CAST(amount AS REAL) > 0), invoice_id TEXT, source_tag INTEGER);

CREATE TABLE IF NOT EXISTS account(
  addr TEXT PRIMARY KEY, created_at TEXT, funded_by TEXT, created_ledger INTEGER);

CREATE TABLE IF NOT EXISTS payer_cluster(
  addr TEXT PRIMARY KEY, cluster_id TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, endpoint TEXT NOT NULL REFERENCES endpoint(id), need_id TEXT, at TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('plumb', 'vet402')),
  http_status INTEGER, latency_ms INTEGER, settled_tx TEXT UNIQUE,
  spent TEXT CHECK (spent IS NULL OR CAST(spent AS REAL) >= 0),
  verdict TEXT NOT NULL CHECK (verdict IN ('good', 'bad', 'unsettled', 'refused')));

CREATE TABLE IF NOT EXISTS shortlist(
  id TEXT PRIMARY KEY, need_hash TEXT NOT NULL, need_text TEXT NOT NULL, principal TEXT, at TEXT NOT NULL,
  paid_tx TEXT UNIQUE, results TEXT NOT NULL, mode TEXT NOT NULL CHECK (mode IN ('demo', 'live')));

CREATE TABLE IF NOT EXISTS outcome_report(
  payment_tx TEXT PRIMARY KEY, shortlist_id TEXT NOT NULL REFERENCES shortlist(id),
  endpoint TEXT NOT NULL REFERENCES endpoint(id), reporter_payer TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK (verdict IN ('good', 'bad')), at TEXT NOT NULL, weight REAL NOT NULL);

CREATE TABLE IF NOT EXISTS score(
  endpoint TEXT PRIMARY KEY REFERENCES endpoint(id), alpha REAL NOT NULL, beta REAL NOT NULL,
  mean REAL NOT NULL CHECK (mean BETWEEN 0 AND 1), lower80 REAL NOT NULL CHECK (lower80 BETWEEN 0 AND 1),
  n_audits INTEGER NOT NULL, n_reports INTEGER NOT NULL, settle_ok INTEGER NOT NULL, price_honest INTEGER NOT NULL,
  latency_ms INTEGER, updated_at TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS principal(
  addr TEXT PRIMARY KEY, label TEXT NOT NULL, profile TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('ledger', 'simulated')));

CREATE TABLE IF NOT EXISTS principal_outcome(
  id INTEGER PRIMARY KEY, principal TEXT NOT NULL REFERENCES principal(addr),
  endpoint TEXT NOT NULL REFERENCES endpoint(id), verdict TEXT NOT NULL CHECK (verdict IN ('good', 'bad')),
  latency_ms INTEGER, at TEXT NOT NULL, source TEXT NOT NULL CHECK (source IN ('report', 'simulated')));

CREATE TABLE IF NOT EXISTS need(
  key TEXT PRIMARY KEY, text TEXT NOT NULL, bazaar_order TEXT NOT NULL DEFAULT '[]');

CREATE TABLE IF NOT EXISTS fit(
  need_key TEXT NOT NULL REFERENCES need(key), endpoint TEXT NOT NULL REFERENCES endpoint(id),
  p_fit REAL NOT NULL CHECK (p_fit BETWEEN 0 AND 1), reason TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (need_key, endpoint));

CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)  # MCP runs sync tools in worker threads; writes are serialised by SQLite
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn

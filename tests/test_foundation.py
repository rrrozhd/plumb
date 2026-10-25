import sqlite3
from decimal import Decimal

import pytest

from plumb.core import config, db, money

pytestmark = pytest.mark.p0


def test_rlusd_parses_exact_strings_and_rejects_floats():
    assert money.rlusd("0.003") == Decimal("0.003")
    with pytest.raises(TypeError):
        money.rlusd(0.003)  # pyright: ignore[reportArgumentType]
    for bad in ("", "abc", "-1", "NaN", "Infinity"):
        with pytest.raises(ValueError):
            money.rlusd(bad)


def test_xrp_drops_are_whole_numbers():
    assert money.xrp_drops("2310") == 2310
    assert money.xrp_drops(15) == 15
    for bad in (1.5, True):
        with pytest.raises(TypeError):
            money.xrp_drops(bad)  # pyright: ignore[reportArgumentType]
    for bad in ("1.5", "-3", "x"):
        with pytest.raises(ValueError):
            money.xrp_drops(bad)


def test_drops_to_rlusd():
    assert money.drops_to_rlusd(2_000_000, Decimal("0.5")) == Decimal("1")


def test_config_refuses_a_missing_cap(tmp_path):
    text = (config.ROOT / "config" / "plumb.toml").read_text().replace('audit_max_total = "5"\n', "")
    p = tmp_path / "plumb.toml"
    p.write_text(text)
    with pytest.raises(config.ConfigError, match="audit_max_total"):
        config.load(p)


def test_config_refuses_a_float_cap(tmp_path):
    text = (config.ROOT / "config" / "plumb.toml").read_text().replace('eval_max_total = "3"', "eval_max_total = 3.0")
    p = tmp_path / "plumb.toml"
    p.write_text(text)
    with pytest.raises(config.ConfigError, match="eval_max_total"):
        config.load(p)


def test_real_config_loads():
    assert config.load()["xrpl"]["source_tag"] == 804681468


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    c.execute("INSERT INTO operator(payto) VALUES ('rOp')")
    c.execute("INSERT INTO endpoint(id, url, method, payto, price_rlusd) VALUES ('e1', 'https://a/x', 'GET', 'rOp', '0.01')")
    return c


def test_schema_enforces_money_and_uniqueness(conn):
    with pytest.raises(sqlite3.IntegrityError):  # an endpoint needs a price
        conn.execute("INSERT INTO endpoint(id, url, method, payto) VALUES ('e2', 'https://a/y', 'GET', 'rOp')")
    with pytest.raises(sqlite3.IntegrityError):  # prices are positive
        conn.execute("INSERT INTO endpoint(id, url, method, payto, price_rlusd) VALUES ('e3', 'https://a/z', 'GET', 'rOp', '0')")
    with pytest.raises(sqlite3.IntegrityError):  # same url and method twice
        conn.execute("INSERT INTO endpoint(id, url, method, payto, price_rlusd) VALUES ('e4', 'https://a/x', 'GET', 'rOp', '0.02')")
    conn.execute("INSERT INTO audit(endpoint, at, source, settled_tx, verdict) VALUES ('e1', 't', 'plumb', 'TX1', 'good')")
    with pytest.raises(sqlite3.IntegrityError):  # an audit settles at most once
        conn.execute("INSERT INTO audit(endpoint, at, source, settled_tx, verdict) VALUES ('e1', 't', 'plumb', 'TX1', 'bad')")
    with pytest.raises(sqlite3.IntegrityError):  # unknown verdict
        conn.execute("INSERT INTO audit(endpoint, at, source, verdict) VALUES ('e1', 't', 'plumb', 'great')")


def test_schema_enforces_paid_tx_and_outcome_uniqueness(conn):
    conn.execute("INSERT INTO shortlist(id, need_hash, need_text, at, paid_tx, results, mode) VALUES ('s1', 'h', 'n', 't', 'P1', '[]', 'demo')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO shortlist(id, need_hash, need_text, at, paid_tx, results, mode) VALUES ('s2', 'h', 'n', 't', 'P1', '[]', 'demo')")
    conn.execute("INSERT INTO outcome_report VALUES ('T1', 's1', 'e1', 'rPayer', 'good', 't', 1.0)")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO outcome_report VALUES ('T1', 's1', 'e1', 'rPayer', 'bad', 't', 1.0)")

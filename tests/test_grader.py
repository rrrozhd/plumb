import json
from datetime import datetime, timezone

import pytest

from plumb import grader

pytestmark = pytest.mark.p0
NOW = datetime(2026, 10, 25, 3, 0, tzinfo=timezone.utc)
Q01 = {"id": "q01", "need": "Current XRP price in USD", "inputs": {"asset": "XRP", "quote": "USD"}, "freshness": "15m"}


@pytest.mark.parametrize("body,ok", [
    ('{"XRP": 1.31, "at": "2026-10-25T02:58:00Z"}', True),
    ('{"XRP": 1.31, "at": "2026-10-25T02:5', False),            # truncated: does not parse
    ('{"error": "upstream timeout"}', False),                     # error body
    ('{"prices": {}, "note": "sample data"}', False),             # placeholder
    ('', False),
])
def test_g3(body, ok):
    assert grader.g3(body, declared_json=True, schema=None)[0] is ok


def test_g3_error_key_with_real_data_is_fine():
    assert grader.g3('{"error": null, "XRP": 1.3}', True, None)[0]


def test_g3_schema_violation():
    schema = {"type": "object", "required": ["price"]}
    assert not grader.g3('{"XRP": 1.3}', True, schema)[0]


def test_entity_rule_catches_wrong_asset():
    assert grader.g4_entity('{"BTC": 67000}', ["XRP"])[0] is False
    assert grader.g4_entity('{"xrp": 1.3}', ["XRP"])[0] is True


def test_freshness_from_timestamps():
    assert grader.g5('{"at": "2026-10-25T02:58:00Z"}', "15m", NOW)[0] is True
    assert grader.g5('{"at": "2026-10-24T02:58:00Z"}', "15m", NOW)[0] is False
    assert grader.g5('{"date": "2026-10-24"}', "1d", NOW)[0] is True       # date-only gets a day of slack
    assert grader.g5('{"x": 1}', "15m", NOW)[0] is None                     # no timestamp: undecided
    assert grader.g5('{"forecast": "2026-10-27"}', "3h", NOW)[0] is None    # future dates are not data age


def test_numbers_walks_nested_and_string_values():
    assert sorted(grader.numbers({"a": [1, {"b": "2.5"}], "c": "3%", "d": True})) == [1.0, 2.5, 3.0]


def test_oracle_decides_g4_and_llm_is_not_called(monkeypatch):
    monkeypatch.setitem(grader.ORACLES, "q01", lambda d, t: (True, "ref 1.31"))
    called = []
    g = grader.grade(Q01, '{"XRP": 1.31, "at": "2026-10-25T02:58:00Z"}', True, None,
                     llm=lambda q, b: called.append(1) or {}, now=NOW)
    assert g["good"] and g["method"]["g4"] == "oracle" and not called


def test_oracle_outage_falls_back_to_llm_not_to_a_verdict(monkeypatch):
    def down(d, t):
        raise ConnectionError("source down")
    monkeypatch.setitem(grader.ORACLES, "q01", down)
    g = grader.grade(Q01, '{"XRP": 1.31, "at": "2026-10-25T02:58:00Z"}', True, None,
                     llm=lambda q, b: {"g4_answers_need": True, "g5_fresh_enough": True, "reason": "x"}, now=NOW)
    assert g["oracle"] is None and g["method"]["g4"] == "llm" and g["good"]


def test_wrong_entity_fails_without_asking_anyone(monkeypatch):
    monkeypatch.setitem(grader.ORACLES, "q01", lambda d, t: (True, "would pass"))
    g = grader.grade(Q01, '{"BTC": 67000, "at": "2026-10-25T02:58:00Z"}', True, None, llm=None, now=NOW)
    assert not g["good"] and g["method"]["g4"] == "entity rule"


def test_truncated_body_never_reaches_oracle_or_llm(monkeypatch):
    monkeypatch.setitem(grader.ORACLES, "q01", lambda d, t: (_ for _ in ()).throw(AssertionError("called")))
    g = grader.grade(Q01, '{"XRP": 1.3', True, None, llm=lambda q, b: (_ for _ in ()).throw(AssertionError("called")), now=NOW)
    assert not g["good"] and g["g3_why"].startswith("declared JSON")


def test_frozen_truth_oracles_are_deterministic():
    assert grader.o_q17(None, json.dumps({"isBusinessDay": False, "holidays": ["2026-11-11", "2026-11-26"]}))[0]
    assert not grader.o_q17(None, json.dumps({"isBusinessDay": True, "holidays": ["2026-11-11", "2026-11-26"]}))[0]
    assert grader.o_q09(None, json.dumps({"sanctioned": True, "entity": "LAZARUS GROUP"}))[0]
    assert not grader.o_q09(None, json.dumps({"sanctioned": False}))[0]


def test_v3_utc_offset_is_respected():
    # 2026-10-24T21:00-05:00 is 02:00Z, one hour before NOW: fresh at 3h (v2 read it as 21:00Z and failed it)
    assert grader.g5('{"start": "2026-10-24T21:00:00-05:00"}', "3h", NOW)[0] is True
    assert grader.g5('{"at": "2026-10-25T02:58:00.123Z"}', "15m", NOW)[0] is True


def test_v3_one_number_inside_a_string():
    assert grader.numbers({"p": "$1.31", "q": "1.31 USD", "r": "XRP/USD: 1.31"}) == [1.31, 1.31, 1.31]
    assert grader.numbers({"d": "2026-10-25", "t": "14:00"}) == []  # dates and times are not values


def test_v3_metadata_only_error_body_fails_g3():
    assert not grader.g3('{"error": "upstream timeout", "status": 504, "request_id": "abc"}', True, None)[0]
    assert grader.g3('{"error": "partial", "price": 1.3}', True, None)[0]


def test_weather_oracle_reads_only_temperature_fields(monkeypatch):
    monkeypatch.setattr(grader, "_cached", lambda key, fn, ttl=60: 15.0)
    o = {"kind": "weather", "station": "KXXX", "tol_c": 4}
    assert grader.f_weather(o, {"humidity": 15, "temperature_c": 30}, "")[0] is False
    assert grader.f_weather(o, {"temp_f": 59}, "")[0] is True


def test_family_oracle_dispatch_and_holiday_rule(monkeypatch):
    q = {"id": "f999", "oracle": {"kind": "holiday", "date": "2026-12-25", "names": ["Christmas Day", "Weihnachtstag"]}}
    assert grader.oracle(q, '{"date": "2026-12-25", "name": "Christmas Day"}')[0] is True
    assert grader.oracle(q, '{"date": "2026-12-25", "is_holiday": false}')[0] is False

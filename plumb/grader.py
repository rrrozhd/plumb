"""Deterministic grading of paid API responses (rubric G3-G5), shared by the U7 eval and the auditor.

Tier 1 (every response): G3 parse + declared-schema + error/placeholder rules; G4a the named entity appears;
G5 newest timestamp in the body vs the need's freshness limit.
Tier 2 (needs with a free public source of truth): numeric or factual check against that source, fetched at grading time.
Tier 3: anything left (G4 coverage without an oracle, G5 without timestamps) goes to the LLM with the full body.
Response text is untrusted: it is parsed and compared here, never executed or followed.
v3 (2026-10-25, before E26): UTC offsets in timestamps, one number inside a string ("$1.31"), metadata-only error
bodies, and family oracles driven by each query's `oracle` params. E21 and E23 were graded with v2.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

UA = {"User-Agent": "plumb-eval/0.1 (hackathon research; contact via repo)"}
PLACEHOLDER = re.compile(r"lorem ipsum|coming soon|payment required|\bmock(ed)? data\b|\bsample (data|response)\b|not implemented", re.I)
VERSION = 3
ISO = re.compile(r"\b(20\d\d-\d\d-\d\d)(?:[T ](\d\d:\d\d(?::\d\d)?)(?:\.\d+)?(Z|[+-]\d\d:?\d\d)?)?")
ONE_NUMBER = re.compile(r"[^\d\-]*?(-?\d+(?:\.\d+)?)\s*[A-Za-z%°/ ]*")  # "$1.31", "1.31 USD", "XRP/USD: 1.31"
ERROR_META = {"status", "code", "statuscode", "status_code", "message", "request_id", "requestid", "detail", "details",
              "timestamp", "path", "success", "ok", "error_code", "errorcode", "type"}


# ---------- tier 1 --------------------------------------------------------------------------------------------------
def parse(body: str):
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return None


def numbers(obj) -> list[float]:
    """Every numeric leaf, including numeric strings."""
    out = []
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, str):
        s = obj.replace(",", "").strip().rstrip("%")
        try:
            return [float(s)]
        except ValueError:
            m = ONE_NUMBER.fullmatch(s)
            return [float(m.group(1))] if m else []
    items = obj.values() if isinstance(obj, dict) else obj if isinstance(obj, list) else []
    for v in items:
        out += numbers(v)
    return out


def g3(body: str, declared_json: bool, schema: dict | None) -> tuple[bool, str]:
    if not body or not body.strip():
        return False, "empty body"
    data = parse(body)
    if declared_json and data is None:
        return False, "declared JSON but does not parse"
    if isinstance(data, dict) and data.get("error") and all(k.lower() in ERROR_META for k in data
                                                            if k != "error" and data[k] not in (None, "", [], {})):
        return False, f"error body: {str(data.get('error'))[:60]}"
    if isinstance(data, (list, dict)) and not data:
        return False, "empty JSON"
    if PLACEHOLDER.search(body[:20000]):
        return False, "placeholder or sample text"
    if schema and data is not None:
        import jsonschema
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            return False, f"schema: {e.message[:80]}"
        except jsonschema.SchemaError:
            pass  # a broken declared schema is the listing's problem, not evidence against the response
    return True, "ok"


def entities(inputs: dict) -> list[str]:
    keys = ("asset", "address", "contract", "domain", "tx_hash", "name")
    return [str(inputs[k]) for k in keys if inputs.get(k)]


def g4_entity(body: str, ents: list[str]) -> tuple[bool, str]:
    low = body.lower()
    missing = [e for e in ents if e.lower() not in low]
    return (not missing), ("ok" if not missing else f"missing entity {missing[0][:20]}")


LIMIT = re.compile(r"^(\d+)([mhd])$")


def g5(body: str, freshness: str, now: datetime) -> tuple[bool | None, str]:
    m = LIMIT.match(str(freshness))
    if not m:
        return None, "no numeric freshness limit"
    unit = {"m": "minutes", "h": "hours", "d": "days"}[m.group(2)]
    limit = timedelta(**{unit: int(m.group(1))})
    stamps = []  # (time, date_only)
    for d, t, tz in ISO.findall(body[:200000]):
        try:
            at = datetime.fromisoformat(f"{d}T{t or '00:00'}{tz.replace('Z', '+00:00') if t else ''}")
            stamps.append((at if at.tzinfo else at.replace(tzinfo=timezone.utc), not t))
        except ValueError:
            pass
    stamps = [s for s in stamps if s[0] <= now + timedelta(minutes=10)]  # forecast dates are not data age
    if not stamps:
        return None, "no timestamp found"
    newest, date_only = max(stamps)
    ok = now - newest <= limit + (timedelta(days=1) if date_only else timedelta(0))
    return ok, f"newest {newest.isoformat()} vs limit {freshness}"


# ---------- tier 2: oracles -----------------------------------------------------------------------------------------
def _near(values: list[float], ref: float, rel: float) -> bool:
    return any(abs(v - ref) <= rel * abs(ref) for v in values if v)


def _get(url, **kw):
    return httpx.get(url, timeout=20, headers=UA, follow_redirects=True, **kw).json()


def _eth(method, params):
    r = httpx.post("https://ethereum.publicnode.com", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=20)
    return r.json()["result"]


def o_q01(data, text):
    ref = _get("https://api.coingecko.com/api/v3/simple/price", params={"ids": "ripple", "vs_currencies": "usd"})["ripple"]["usd"]
    return _near(numbers(data), ref, 0.02), f"CoinGecko XRP {ref}"


def o_q03(data, text):
    ref = int(_get("https://api.alternative.me/fng/")["data"][0]["value"])
    return any(abs(v - ref) <= 1 for v in numbers(data)), f"alternative.me {ref}"


def o_q04(data, text):
    rate = _get("https://api.frankfurter.app/latest", params={"from": "EUR", "to": "USD"})["rates"]["USD"]
    return _near(numbers(data), rate, 0.01) or _near(numbers(data), 250 * rate, 0.0002), f"ECB {rate}"


def o_q07(data, text):
    facts = _get("https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json")["facts"]["us-gaap"]
    rows = [r for k in ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues") for r in facts.get(k, {}).get("units", {}).get("USD", [])
            if r.get("form") == "10-K" and r.get("fp") == "FY"]
    latest = max(rows, key=lambda r: r["end"])
    ref = float(latest["val"])
    vals = numbers(data) + [v * 1e9 for v in numbers(data)] + [v * 1e6 for v in numbers(data)]
    return _near(vals, ref, 0.005), f"EDGAR FY{latest['end']} {ref:.0f}"


def o_q08(data, text):
    t = text.lower()
    hit = "rosneft" in t and bool(re.search(r'"(match|matched|is_?match|sanctioned|listed|hit)"\s*:\s*true|match_found|"matches"\s*:\s*\[\s*\{', t))
    return hit, "frozen truth: Rosneft is on OFAC SDN"


def o_q09(data, text):
    t = text.lower()
    return bool(re.search(r'"(sanctioned|listed|is_?sanctioned|match)"\s*:\s*true', t)) and "lazarus" in t, "frozen truth: OFAC SDN, LAZARUS GROUP"


def o_q11(data, text):
    call = {"to": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "data": "0x70a08231" + "28C6c06298d514Db089934071355E5743bf21d60".lower().rjust(64, "0")}
    ref = int(_eth("eth_call", [call, "latest"]), 16) / 1e6
    return _near(numbers(data), ref, 0.05), f"on-chain USDC {ref:.2f}"


def o_q12(data, text):
    ref = int(_eth("eth_getBlockByNumber", ["latest", False])["baseFeePerGas"], 16) / 1e9
    return _near(numbers(data), ref, 0.5), f"base fee {ref:.4f} gwei"


def o_q13(data, text):
    t = text.lower()
    ok = ("tessuccess" in t or '"validated": true' in t or '"validated":true' in t) and ("0.05" in t) and ("rlusd" in t or "524c555344" in t)
    return ok, "frozen truth: validated tesSUCCESS, 0.05 RLUSD"


def o_q14(data, text):
    rd = _get("https://rdap.verisign.com/com/v1/domain/ripple.com")
    ev = {e["eventAction"]: e["eventDate"][:10] for e in rd.get("events", [])}
    reg = next((v for e in rd.get("entities", []) if "registrar" in e.get("roles", [])
                for v in [x[3] for x in (e.get("vcardArray") or [None, []])[1] if x[0] == "fn"]), "")
    t = text.lower()
    ok = ev.get("registration", "?") in text and ev.get("expiration", "?") in text and reg.split(",")[0].lower()[:8] in t
    return ok, f"RDAP {reg} {ev.get('registration')} {ev.get('expiration')}"


def o_q15(data, text):
    obs = _get("https://api.weather.gov/stations/KNYC/observations/latest")["properties"]["temperature"]["value"]
    if obs is None:
        return None, "NWS KNYC has no current temperature"
    vals = numbers(data)
    ok = any(abs(v - obs) <= 4 for v in vals) or any(abs((v - 32) * 5 / 9 - obs) <= 4 for v in vals)
    return ok, f"NWS KNYC {obs:.1f} C"


def o_q17(data, text):
    t = text.lower()
    not_bd = bool(re.search(r'"(is_?business_?day|business_?day|isbusinessday)"\s*:\s*false', t)) or "not a business day" in t
    return not_bd and "2026-11-11" in t and "2026-11-26" in t, "computed: Thanksgiving; holidays 11-11 and 11-26"


ORACLES = {"q01": o_q01, "q03": o_q03, "q04": o_q04, "q07": o_q07, "q08": o_q08, "q09": o_q09, "q11": o_q11,
           "q12": o_q12, "q13": o_q13, "q14": o_q14, "q15": o_q15, "q17": o_q17}


def oracle(q: dict, body: str) -> tuple[bool | None, str]:
    spec = q.get("oracle")
    fn = (lambda d, t: FAMILY[spec["kind"]](spec, d, t)) if spec else ORACLES.get(q["id"])
    if not fn:
        return None, "no oracle"
    try:
        return fn(parse(body), body)
    except Exception as e:  # an oracle outage must not turn into a verdict against the merchant
        return None, f"oracle unavailable: {type(e).__name__}"


# ---------- combine -------------------------------------------------------------------------------------------------
def grade(q: dict, body: str, declared_json: bool, schema: dict | None, llm=None, now: datetime | None = None) -> dict:
    """Deterministic first; the LLM (callable(need_dict, body) -> {g4, g5, reason}) only fills what code can't decide."""
    now = now or datetime.now(timezone.utc)
    ok3, why3 = g3(body, declared_json, schema)
    ent_ok, why_ent = g4_entity(body, entities(q.get("inputs") or {}))
    fresh, why5 = g5(body, q.get("freshness", "n/a"), now)
    orc, why_o = oracle(q, body) if ok3 else (None, "skipped: G3 failed")
    out = {"g3": ok3, "g3_why": why3, "g4_entity": ent_ok, "g4_entity_why": why_ent, "g5": fresh, "g5_why": why5,
           "oracle": orc, "oracle_why": why_o, "llm": None, "method": {}}
    g4 = None
    if ok3 and ent_ok and orc is not None:
        g4, out["method"]["g4"] = orc, "oracle"
    elif not ent_ok:
        g4, out["method"]["g4"] = False, "entity rule"
    if ok3 and (g4 is None or fresh is None) and llm is not None:
        out["llm"] = llm(q, body)
        if g4 is None:
            g4, out["method"]["g4"] = out["llm"]["g4_answers_need"], "llm"
        if fresh is None:
            fresh = out["llm"]["g5_fresh_enough"]
            out["method"]["g5"] = "llm"
    out["method"].setdefault("g5", "timestamp" if out["g5"] is not None else "n/a")
    fresh = True if fresh is None and str(q.get("freshness")) in ("n/a",) else fresh
    out["g4"], out["g5_final"] = g4, fresh
    out["good"] = bool(ok3 and g4 and fresh)
    return out


# ---------- E22 held-out needs (eval/queries_e22.yaml): oracles from the sources each `check` names ---------------
def _cg(coin):
    return _get("https://api.coingecko.com/api/v3/simple/price", params={"ids": coin, "vs_currencies": "usd"})[coin]["usd"]


def o_e01(data, text):
    ref = _cg("ethereum")
    return _near(numbers(data), ref, 0.02), f"CoinGecko ETH {ref}"


def o_e02(data, text):
    ref = _cg("solana")
    return _near(numbers(data), ref, 0.02), f"CoinGecko SOL {ref}"


def o_e03(data, text):
    rate = _get("https://api.frankfurter.app/latest", params={"from": "GBP", "to": "USD"})["rates"]["USD"]
    return _near(numbers(data), rate, 0.01) or _near(numbers(data), 100 * rate, 0.0001), f"ECB GBP/USD {rate}"


def o_e04(data, text):
    rate = _get("https://api.frankfurter.app/latest", params={"from": "JPY", "to": "EUR"})["rates"]["EUR"]
    return _near(numbers(data), rate, 0.01) or _near(numbers(data), 1000 * rate, 0.0001), f"ECB JPY/EUR {rate}"


def o_e05(data, text):
    ref = int(_eth("eth_blockNumber", []), 16)
    return any(abs(v - ref) <= 50 for v in numbers(data)), f"block {ref}"


def o_e06(data, text):
    obs = _get("https://api.weather.gov/stations/KMDW/observations/latest")["properties"]["temperature"]["value"]
    if obs is None:
        return None, "NWS KMDW has no current temperature"
    vals = numbers(data)
    return any(abs(v - obs) <= 4 for v in vals) or any(abs((v - 32) * 5 / 9 - obs) <= 4 for v in vals), f"NWS KMDW {obs:.1f} C"


def o_e07(data, text):
    t = text.lower()
    not_bd = bool(re.search(r'"(is_?business_?day|business_?day|isbusinessday)"\s*:\s*false', t)) or "not a business day" in t
    return not_bd and "2026-12-25" in t, "computed: Christmas Day"


def o_e08(data, text):
    rd = _get("https://rdap.verisign.com/com/v1/domain/coinbase.com")
    ev = {e["eventAction"]: e["eventDate"][:10] for e in rd.get("events", [])}
    reg = next((v for e in rd.get("entities", []) if "registrar" in e.get("roles", [])
                for v in [x[3] for x in (e.get("vcardArray") or [None, []])[1] if x[0] == "fn"]), "")
    ok = ev.get("registration", "?") in text and ev.get("expiration", "?") in text and reg.split(",")[0].lower()[:8] in text.lower()
    return ok, f"RDAP {reg} {ev.get('registration')} {ev.get('expiration')}"


def o_e09(data, text):
    from plumb import config, ledger
    bal = int(ledger.Ledger(config.load()).account_info("rMxCKbEDwqr76QuheSUMdEGf4B9xJ8m5De")["Balance"])
    xrp = bal / 1e6
    vals = numbers(data)
    return _near(vals, xrp, 0.01) or _near(vals, bal, 0.01), f"ledger {xrp:.6f} XRP"


def o_e10(data, text):
    tip = int(httpx.get("https://mempool.space/api/blocks/tip/height", timeout=20, headers=UA).text)
    return any(abs(v - tip) <= 3 for v in numbers(data)), f"mempool tip {tip}"


ORACLES.update({"e01": o_e01, "e02": o_e02, "e03": o_e03, "e04": o_e04, "e05": o_e05, "e06": o_e06,
                "e07": o_e07, "e08": o_e08, "e09": o_e09, "e10": o_e10})


# ---------- E26 family oracles (eval/queries_e26.yaml): params live in each query, sources are free and public ------
_CACHE: dict = {}


def _cached(key, fn, ttl=60):
    """One reference per minute per key: 190 purchases must not hit public rate limits and fall through to the LLM."""
    import time
    hit = _CACHE.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (time.monotonic(), val)
    return val


def keyed(obj, rx) -> list[float]:
    """Numeric values under keys matching rx (anywhere in the tree)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += numbers(v) if rx.search(str(k)) and not isinstance(v, (dict, list)) else keyed(v, rx)
    elif isinstance(obj, list):
        for v in obj:
            out += keyed(v, rx)
    return out


def f_price(o, data, text):
    ref = _cached(("cg", o["coin"], o["vs"]), lambda: _get("https://api.coingecko.com/api/v3/simple/price",
                                                         params={"ids": o["coin"], "vs_currencies": o["vs"]})[o["coin"]][o["vs"]])
    return _near(numbers(data), ref, o["tol"]), f"CoinGecko {o['coin']}/{o['vs']} {ref}"


def f_fx(o, data, text):
    rate = _cached(("fx", o["from"], o["to"]), lambda: _get("https://api.frankfurter.app/latest",
                                                           params={"from": o["from"], "to": o["to"]})["rates"][o["to"]], ttl=600)
    vals = numbers(data)
    return _near(vals, rate, o["tol"]) or _near(vals, o["amount"] * rate, o["tol"] / 10), f"ECB {o['from']}/{o['to']} {rate}"


TEMP = re.compile(r"temp", re.I)


def f_weather(o, data, text):
    obs = _cached(("nws", o["station"]), lambda: _get(f"https://api.weather.gov/stations/{o['station']}/observations/latest")
                  ["properties"]["temperature"]["value"], ttl=600)
    if obs is None:
        return None, f"NWS {o['station']} has no current temperature"
    vals = keyed(data, TEMP)  # only temperature fields: bodies are full of humidity, wind and hours
    ok = any(abs(v - obs) <= o["tol_c"] or abs((v - 32) * 5 / 9 - obs) <= o["tol_c"] for v in vals)
    return ok, f"NWS {o['station']} {obs:.1f} C"


def f_block(o, data, text):
    if o["rpc"] == "xrpl":
        from plumb import config, ledger
        ref = int(ledger.Ledger(config.load()).rpc("ledger", ledger_index="validated")["ledger_index"])
    else:
        r = httpx.post(o["rpc"], json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []}, timeout=20)
        ref = int(r.json()["result"], 16)
    return any(abs(v - ref) <= o["tol"] for v in numbers(data)), f"head {ref} (tol {o['tol']})"


def f_holiday(o, data, text):
    t = text.lower()
    yes = bool(re.search(r'"(is_?)?(public_?)?holiday"\s*:\s*true', t)) or any(n.lower() in t for n in o["names"])
    return yes and o["date"] in text, f"nager.date: {o['date']} is {o['names'][0]}"


FAMILY = {"price": f_price, "fx": f_fx, "weather": f_weather, "block": f_block, "holiday": f_holiday}

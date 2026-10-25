"""U7, free version: Bazaar's #1 vs Plumb's #1 for each frozen need, probed without paying.

Per pick: is the endpoint alive (a valid x402 challenge), is the challenged price the listed one, can it be paid
(merchant account exists, holds an RLUSD trust line when RLUSD is asked), and what is its track record.
It measures whether a purchase would be wasted outright, not whether the answer is good (that needs the paid U7).
"""
import base64
import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import yaml

from plumb import catalog, config, ledger, rank


def freeze_picks(cfg: dict, root) -> list[dict]:
    """The two #1 picks per need, from the snapshot; written before any probe (rubric §1)."""
    r = rank.load(cfg, root, with_principals=False)
    search = json.loads((root / "bazaar_search.json").read_text())
    mid = r.rec.xrp_in_rlusd
    picks = []
    for q in yaml.safe_load(config.path(cfg, "queries").read_text())["queries"]:
        cap = Decimal(str(q.get("max_price_rlusd", "0.05")))
        bz = None
        for res in search[q["id"]]:
            e = catalog.parse_listing(res, cfg)
            if e and (e.price_rlusd or Decimal(e.price_xrp_drops or 0) / 1_000_000 * mid) <= cap:
                bz = e.url
                break
        out = r.shortlist(q["need"], k=1, constraints={"max_price": str(cap)})["results"]
        picks.append({"id": q["id"], "need": q["need"], "bazaar": bz, "plumb": out[0]["url"] if out else None})
    return picks


def _challenge(res: dict, http: httpx.Client) -> dict:
    """Call the endpoint unpaid, the way a buyer would, and decode its x402 challenge."""
    info = ((res.get("extensions") or {}).get("bazaar") or {}).get("info") or {}
    inp = info.get("input") or {}
    method = (inp.get("method") or "GET").upper()
    try:
        if method == "GET":
            resp = http.get(res["resource"], params=inp.get("queryParams") or None)
        else:
            resp = http.request(method, res["resource"], json=inp.get("body") or {})
    except httpx.HTTPError as e:
        return {"status": None, "error": type(e).__name__}
    req = None
    hdr = resp.headers.get("payment-required")
    if hdr:
        try:
            req = json.loads(base64.b64decode(hdr + "=" * (-len(hdr) % 4)))
        except ValueError:
            req = None
    if req is None:
        try:
            body = resp.json()
            req = body if isinstance(body, dict) and "accepts" in body else None
        except ValueError:
            pass
    return {"status": resp.status_code, "accepts": (req or {}).get("accepts", [])}


def probe(res: dict, cfg: dict, lg, http: httpx.Client, vet: dict, pay_counts: dict) -> dict:
    x = cfg["xrpl"]
    listed = catalog.parse_listing(res, cfg)
    ch = _challenge(res, http)
    opt = next((a for a in ch.get("accepts", []) if a.get("network") == x["network"]
                and a.get("asset") in (x["rlusd_currency"], "XRP")), None)
    alive = ch["status"] == 402 and opt is not None
    honest = False
    if opt is not None and alive and listed:
        got = Decimal(str(opt.get("amount")))
        if opt["asset"] == x["rlusd_currency"]:
            honest = got == listed.price_rlusd
        else:  # XRP prices are often pegged to USD and re-converted live: allow a small drift
            want = Decimal(listed.price_xrp_drops or 0)
            honest = want > 0 and abs(got - want) / want <= Decimal(cfg["eval"]["xrp_price_drift"])
        honest = honest and opt.get("payTo") == listed.payto
    payable = False
    if opt is not None and alive:
        try:
            lg.account_info(opt["payTo"])
            payable = opt["asset"] == "XRP" or any(ln.get("currency") == x["rlusd_currency"] and ln.get("account") == x["rlusd_issuer"]
                                                   for ln in lg.account_lines(opt["payTo"]))
        except RuntimeError:
            payable = False
    key = res["resource"].split("://", 1)[-1]
    rows = vet.get(key, [])
    return {"url": res["resource"], "http": ch["status"], "alive": alive, "price_honest": honest, "payable": payable,
            "ready": alive and honest and payable,
            "vet402": {"n": len(rows), "good": sum(r == "good" for r in rows)},
            "ledger_payments_to_operator": pay_counts.get(listed.payto if listed else "", 0)}


def run(cfg: dict) -> dict:
    from plumb import score
    root = config.ROOT / "data"
    picks = freeze_picks(cfg, root)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    (root / "u7_free_picks.json").write_text(json.dumps({"frozen_at": stamp, "picks": picks}, indent=1))

    with gzip.open(root / "catalog.json.gz", "rt") as fh:
        raw = {r["resource"]: r for r in json.load(fh)}
    for rs in json.loads((root / "bazaar_search.json").read_text()).values():
        for r in rs:
            raw.setdefault(r["resource"], r)
    import csv
    vet: dict[str, list[str]] = {}
    for row in csv.DictReader((root / "vet402_xrpl.csv").open()):
        vet.setdefault(row["resource_key"], []).append(score.classify_vet402(row))
    pay_counts: dict[str, int] = {}
    for p in json.loads((root / "ledger_payments.json").read_text()):
        pay_counts[p["payto"]] = pay_counts.get(p["payto"], 0) + 1

    lg = ledger.Ledger(cfg)
    urls = sorted({u for p in picks for u in (p["bazaar"], p["plumb"]) if u})
    with httpx.Client(timeout=15, follow_redirects=False) as http, ThreadPoolExecutor(6) as pool:
        probed = dict(zip(urls, pool.map(lambda u: probe(raw[u], cfg, lg, http, vet, pay_counts), urls)))

    rows, summary = [], {}
    for p in picks:
        rows.append({**p, "bazaar_probe": probed.get(p["bazaar"]), "plumb_probe": probed.get(p["plumb"])})
    for side in ("bazaar", "plumb"):
        got = [r[f"{side}_probe"] for r in rows if r[f"{side}_probe"]]
        with_ev = [g for g in got if g["vet402"]["n"]]
        summary[side] = {"picks": len(got), "ready": sum(g["ready"] for g in got), "alive": sum(g["alive"] for g in got),
                         "price_honest": sum(g["price_honest"] for g in got), "payable": sum(g["payable"] for g in got),
                         "vet402_backtest": {"picks_with_history": len(with_ev),
                                             "good": sum(g["vet402"]["good"] for g in with_ev),
                                             "attempts": sum(g["vet402"]["n"] for g in with_ev)}}
    report = {"at": stamp, "kind": "free pre-purchase check (no money spent)", "summary": summary, "rows": rows}
    out = config.ROOT / "out" / f"eval-free-{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    report["path"] = str(out)
    return report

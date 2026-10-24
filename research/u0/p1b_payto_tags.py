# U0 probe 1b: for each XRPL payTo found by p1, read its recent incoming Payments on-ledger and tally SourceTag,
# InvoiceID and currency. Does a filter on t54's SourceTag see every merchant's sales? A Payment that carries an
# InvoiceID is counted as x402-like (t54 sets InvoiceID = SHA-256(invoiceId)); untagged top-ups have none. Read-only.
# usage: uv run --no-project --with httpx --with xrpl-py python research/u0/p1b_payto_tags.py [research/u0/p1.json] [research/u0/p1b.json] [pages=3]
import json, sys, time, tomllib
from collections import Counter
from pathlib import Path
import httpx

CFG = tomllib.loads((Path(__file__).parent / "u0.toml").read_text())["xrpl"]
SRC = sys.argv[1] if len(sys.argv) > 1 else "research/u0/p1.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "research/u0/p1b.json"
PAGES = int(sys.argv[3]) if len(sys.argv) > 3 else 3

def rpc(method, **params):
    for i in range(5):
        try:
            r = httpx.post(CFG["rpc_url"], json={"method": method, "params": [params]}, timeout=60).json()["result"]
            if r.get("status") == "success": return r
            if r.get("error") in ("actNotFound",): return r
        except Exception: pass
        time.sleep(2 ** i)
    raise RuntimeError(f"rpc {method} failed")

def currency(d): return "XRP" if isinstance(d, str) else (d or {}).get("currency")

census = json.loads(Path(SRC).read_text())["census"]
out = {}
for payto, m in census.items():
    tags, cur, inv, n, first, last, marker = Counter(), Counter(), Counter(), 0, None, None, None
    for _ in range(PAGES):
        r = rpc("account_tx", account=payto, limit=400, forward=False, **({"marker": marker} if marker else {}))
        for t in r.get("transactions", []):
            tx, meta = t.get("tx_json") or t.get("tx") or {}, t.get("meta") or {}
            if tx.get("TransactionType") != "Payment" or tx.get("Destination") != payto or meta.get("TransactionResult") != "tesSUCCESS": continue
            n += 1; tags[str(tx.get("SourceTag"))] += 1; cur[currency(meta.get("delivered_amount"))] += 1
            if tx.get("InvoiceID"): inv[str(tx.get("SourceTag"))] += 1
            d = tx.get("date"); first = d if first is None else min(first, d); last = d if last is None else max(last, d)
        marker = r.get("marker")
        if not marker: break
    t54, x402 = tags.get(str(CFG["source_tag"]), 0), sum(inv.values())
    iso = lambda d: time.strftime("%Y-%m-%d", time.gmtime(d + CFG["ripple_epoch"])) if d else None
    out[payto] = dict(host=m["top_hosts"][0], listed_tags=m["source_tags"], incoming_payments=n, window=[iso(first), iso(last)],
                      source_tags=tags.most_common(6), t54_tagged=t54, x402_like=x402, x402_like_by_tag=inv.most_common(),
                      x402_like_outside_t54_tag=x402 - inv.get(str(CFG["source_tag"]), 0), currencies=cur.most_common(4))
    print(payto, out[payto]["host"], out[payto]["window"], "in", n, "t54", t54, "x402-like", x402, "by tag", inv.most_common(3), "tags", tags.most_common(3))
tot = lambda k: sum(v[k] for v in out.values())
summary = dict(at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), pages_per_account=PAGES, accounts=len(out),
               incoming_payments=tot("incoming_payments"), t54_tagged=tot("t54_tagged"), x402_like=tot("x402_like"),
               x402_like_outside_t54_tag=tot("x402_like_outside_t54_tag"),
               accounts_with_x402_like_outside_t54_tag={p: v["x402_like_by_tag"] for p, v in out.items() if v["x402_like_outside_t54_tag"]},
               accounts_without_x402_like=[p for p, v in out.items() if not v["x402_like"]])
Path(OUT).write_text(json.dumps(dict(summary=summary, accounts=out), indent=1))
print(json.dumps(summary, indent=1))

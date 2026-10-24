# Probe 4: scan N consecutive recent validated ledgers for x402 payments (SourceTag 804681468); who sends the volume?
import json, sys
from collections import Counter
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import Ledger
c = JsonRpcClient("https://s2.ripple.com:51234")
TAG, N = 804681468, int(sys.argv[2])
top = c.request(Ledger(ledger_index="validated")).result["ledger_index"]
rows, payments_all = [], 0
for li in range(top - N + 1, top + 1):
    led = c.request(Ledger(ledger_index=li, transactions=True, expand=True)).result["ledger"]
    for t in led.get("transactions", []):
        tx = t.get("tx_json", t); m = t.get("meta") or t.get("metaData") or {}
        if tx.get("TransactionType") == "Payment":
            payments_all += 1
            if tx.get("SourceTag") == TAG:
                d = m.get("delivered_amount")
                cur = "XRP" if isinstance(d, str) else (d or {}).get("currency")
                val = int(d) / 1e6 if isinstance(d, str) else float((d or {}).get("value", 0))
                rows.append(dict(frm=tx["Account"], to=tx["Destination"], cur=cur, v=val, res=m.get("TransactionResult"), li=li))
json.dump(rows, open(sys.argv[1], "w"))
secs = N * 3.9
print(f"ledgers {top-N+1}..{top} (~{secs/60:.0f} min), all payments {payments_all}, x402 payments {len(rows)} ({100*len(rows)/max(payments_all,1):.1f}%)")
print(f"rate ~{len(rows)/secs*86400:,.0f}/day  ->  ~{len(rows)/secs*86400*30:,.0f}/30d")
print("results", Counter(r["res"] for r in rows)); print("currency", Counter(r["cur"] for r in rows))
print("distinct senders", len({r['frm'] for r in rows}), "receivers", len({r['to'] for r in rows}))
print("value sum by currency", {k: round(sum(r['v'] for r in rows if r['cur']==k), 6) for k in {r['cur'] for r in rows}})
for (a, b), n in Counter((r["frm"], r["to"]) for r in rows).most_common(8): print(f"  {a} -> {b}: {n}")

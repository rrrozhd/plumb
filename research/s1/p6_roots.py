# Probe 6: walk funding ancestry up to 4 levels; measure how many x402 payments have sender and receiver under one root.
import json, sys, datetime as dt
from collections import Counter
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountTx
c = JsonRpcClient("https://s2.ripple.com:51234"); EPOCH = 946684800
rows = json.load(open(sys.argv[1])); info = json.load(open(sys.argv[2]))
cache = {a: v["parent"] for a, v in info.items()}
def parent(a):
    if a not in cache:
        r = c.request(AccountTx(account=a, limit=1, forward=True)).result
        t = (r.get("transactions") or [None])[0]; tx = (t or {}).get("tx_json") or {}
        cache[a] = tx.get("Account") if tx.get("Account") not in (None, a) else None
    return cache[a]
def chain(a, depth=4):
    out = [a]
    for _ in range(depth):
        p = parent(out[-1])
        if not p: break
        out.append(p)
    return out
chains = {a: chain(a) for a in {r["frm"] for r in rows} | {r["to"] for r in rows}}
def shared(a, b):  # nearest common ancestor within the walked chains
    sa = set(chains[a]); return next((x for x in chains[b] if x in sa), None)
same = [r for r in rows if shared(r["frm"], r["to"])]
print(f"x402 payments whose sender and receiver share a funding ancestor (<=4 hops): {len(same)}/{len(rows)} ({100*len(same)/len(rows):.0f}%)")
print("common ancestors:", Counter(shared(r["frm"], r["to"]) for r in same).most_common(5))
tops = Counter(chains[a][-1] for a in chains); print("top roots of all accounts:", tops.most_common(5))
for a in list(chains)[:3]: print("example chain:", " <- ".join(chains[a]))

# Probe 2: collect x402 payments (SourceTag 804681468) to known merchants over 30 days, snowball one hop via payers,
# and resolve each account's funding parent (the account that activated it). Read-only, mainnet.
import json, sys, time, datetime as dt
from collections import Counter, defaultdict
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountTx
c = JsonRpcClient("https://s2.ripple.com:51234")
EPOCH, TAG = 946684800, 804681468
since = int(time.time()) - 30 * 86400 - EPOCH
seeds = [m for m in Counter(x["dest"] for x in json.load(open(sys.argv[1])) if x["dest"])]

def recent(acct, pages):
    marker = None
    for _ in range(pages):
        r = c.request(AccountTx(account=acct, limit=400, marker=marker, forward=False)).result
        for t in r.get("transactions", []):
            tx = t.get("tx_json") or {}
            if tx.get("date", 0) < since: return
            yield tx, t.get("meta", {}), t.get("hash")
        marker = r.get("marker")
        if not marker: return

def value(d):
    if isinstance(d, str): return ("XRP", int(d) / 1e6)
    if isinstance(d, dict): return (d.get("currency"), float(d.get("value", 0)))
    return (None, 0.0)

pays, outflows, scanned = [], [], {}
def scan(acct, pages):
    if acct in scanned: return
    n = 0
    for tx, m, h in recent(acct, pages):
        n += 1
        if tx.get("TransactionType") != "Payment" or m.get("TransactionResult") != "tesSUCCESS": continue
        cur, v = value(m.get("delivered_amount"))
        row = dict(hash=h, frm=tx["Account"], to=tx["Destination"], tag=tx.get("SourceTag"), cur=cur, v=v, date=tx["date"])
        (pays if tx.get("SourceTag") == TAG else outflows).append(row)
    scanned[acct] = n

for m in seeds: scan(m, 40)
payers = Counter(p["frm"] for p in pays)
for a, _ in payers.most_common(25): scan(a, 15)              # one hop: what else do the busiest payers pay?
uniq = {p["hash"]: p for p in pays}; pays = list(uniq.values())
merchants = Counter(p["to"] for p in pays)

def parent(acct):
    r = c.request(AccountTx(account=acct, limit=1, forward=True)).result
    t = (r.get("transactions") or [None])[0]
    if not t: return None
    tx = t.get("tx_json") or {}
    return tx.get("Account") if tx.get("Account") != acct else None
accts = set(p["frm"] for p in pays) | set(merchants)
parents = {}
for i, a in enumerate(sorted(accts)):
    parents[a] = parent(a)
json.dump(dict(pays=pays, outflows=outflows, parents=parents, scanned=scanned), open(sys.argv[2], "w"))
print("seed merchants", len(seeds), "scanned accounts", len(scanned), "rows scanned", sum(scanned.values()))
print("x402 payments (30d)", len(pays), "payers", len({p['frm'] for p in pays}), "merchants", len(merchants))
print("currencies", Counter(p["cur"] for p in pays))
print("top merchants", merchants.most_common(8))
print("top payers", Counter(p["frm"] for p in pays).most_common(8))

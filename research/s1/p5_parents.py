# Probe 5: funding parents and account age of the senders seen in the ledger scan (read-only).
import json, sys, time, datetime as dt
from collections import Counter
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountTx, AccountInfo
c = JsonRpcClient("https://s2.ripple.com:51234"); EPOCH = 946684800
rows = json.load(open(sys.argv[1]))
def first(acct):
    r = c.request(AccountTx(account=acct, limit=1, forward=True)).result
    t = (r.get("transactions") or [None])[0]
    if not t: return None, None
    tx = t.get("tx_json") or {}
    return (tx.get("Account") if tx.get("Account") != acct else None), tx.get("date")
info = {}
for a in sorted({r["frm"] for r in rows} | {r["to"] for r in rows}):
    p, d = first(a)
    seq = c.request(AccountInfo(account=a)).result.get("account_data", {}).get("Sequence")
    info[a] = dict(parent=p, created=dt.datetime.fromtimestamp(d + EPOCH, dt.UTC).date().isoformat() if d else None, seq=seq)
json.dump(info, open(sys.argv[2], "w"), indent=1)
senders = {r["frm"] for r in rows}; recv = {r["to"] for r in rows}
pc = Counter(info[s]["parent"] for s in senders)
print("senders", len(senders), "distinct funding parents", len(pc))
for p, n in pc.most_common(6): print(f"  parent {p}: funded {n} senders")
print("sender creation dates", Counter(info[s]["created"][:7] if info[s]["created"] else None for s in senders).most_common(6))
print("sender tx counts (Sequence) median", sorted(info[s]["seq"] or 0 for s in senders)[len(senders)//2])
print("receivers", {r: (info[r]["parent"], info[r]["created"]) for r in recv})
print("receiver funded a sender?", sum(1 for s in senders if info[s]["parent"] in recv), "| sender parent == receiver parent:", sum(1 for r in rows if info[r['frm']]['parent'] and info[r['frm']]['parent'] == info[r['to']]['parent']))

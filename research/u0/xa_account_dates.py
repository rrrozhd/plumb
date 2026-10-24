# U0 extra check A: can we date an account from its Sequence? Since the DeletableAccounts amendment, a new account's
# starting Sequence is the index of the ledger that created it. For 5 farm senders from research/s1/p5.json:
#   1. read the creating transaction (account_tx forward, limit 1) and the AccountRoot it created (meta CreatedNode);
#   2. check NewFields.Sequence == the creating ledger index;
#   3. cross-check: the first transaction the account itself sent carries Sequence == that starting value;
#   4. read account_info at the latest validated ledger L: its Sequence is the starting value plus every transaction
#      sent since, so one account_info call over-dates an active account by its own transaction count.
# Read-only.
# usage: uv run --no-project --with httpx --with xrpl-py python research/u0/xa_account_dates.py [research/s1/p5.json] [research/s1/p4.json] [research/u0/xa.json]
import datetime as dt, json, sys, time, tomllib
from pathlib import Path
import httpx

CFG = tomllib.loads((Path(__file__).parent / "u0.toml").read_text())["xrpl"]
P5 = sys.argv[1] if len(sys.argv) > 1 else "research/s1/p5.json"
P4 = sys.argv[2] if len(sys.argv) > 2 else "research/s1/p4.json"
OUT = sys.argv[3] if len(sys.argv) > 3 else "research/u0/xa.json"
N = 5

def rpc(method, **params):
    for i in range(5):
        try:
            r = httpx.post(CFG["rpc_url"], json={"method": method, "params": [params]}, timeout=60).json()["result"]
            if r.get("status") == "success": return r
        except Exception: pass
        time.sleep(2 ** i)
    raise RuntimeError(f"rpc {method} failed")

iso = lambda d: dt.datetime.fromtimestamp(d + CFG["ripple_epoch"], dt.UTC).isoformat()
info = json.loads(Path(P5).read_text())
senders = sorted({r["frm"] for r in json.loads(Path(P4).read_text())})
farm = [a for a in senders if (info.get(a) or {}).get("created") == "2026-08-25"][:N]  # deterministic: first 5 by address
L = rpc("ledger", ledger_index="validated")["ledger_index"]
rows = []
for a in farm:
    t = rpc("account_tx", account=a, limit=1, forward=True)["transactions"][0]
    tx, meta = t.get("tx_json") or t.get("tx"), t["meta"]
    li = t.get("ledger_index") or tx.get("ledger_index")  # API v2 puts it beside tx_json, v1 inside tx
    created = next((n["CreatedNode"] for n in meta["AffectedNodes"] if "CreatedNode" in n
                    and n["CreatedNode"]["LedgerEntryType"] == "AccountRoot" and n["CreatedNode"]["NewFields"]["Account"] == a), None)
    start = created["NewFields"]["Sequence"] if created else None
    now_seq = rpc("account_info", account=a, ledger_index=L)["account_data"]["Sequence"]
    first_sent, marker = None, None  # the account's own first transaction
    while first_sent is None:
        r = rpc("account_tx", account=a, limit=200, forward=True, **({"marker": marker} if marker else {}))
        first_sent = next(((x.get("tx_json") or x.get("tx")) for x in r["transactions"] if (x.get("tx_json") or x.get("tx") or {}).get("Account") == a), None)
        marker = r.get("marker")
        if not marker: break
    over = now_seq - start if start else None
    rows.append(dict(account=a, creating_tx=t.get("hash") or tx.get("hash"), funder=tx.get("Account"), created_ledger=li,
                     created_at=iso(tx["date"]), starting_sequence=start, start_equals_ledger=start == li,
                     first_sent_sequence=(first_sent or {}).get("Sequence"), first_sent_matches=(first_sent or {}).get("Sequence") == start,
                     sequence_at_L=now_seq, account_info_overshoot_ledgers=over,
                     account_info_overshoot_days=round(over * 3.9 / 86400, 1) if over else None))
    print(rows[-1])
summary = dict(at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), ledger_L=L, accounts=len(rows),
               start_equals_creating_ledger=sum(r["start_equals_ledger"] for r in rows),
               first_sent_matches_start=sum(r["first_sent_matches"] for r in rows),
               account_info_overshoot_ledgers=[r["account_info_overshoot_ledgers"] for r in rows],
               created_span=[min(r["created_at"] for r in rows), max(r["created_at"] for r in rows)],
               created_ledger_span=max(r["created_ledger"] for r in rows) - min(r["created_ledger"] for r in rows))
Path(OUT).write_text(json.dumps(dict(summary=summary, accounts=rows), indent=1))
print(json.dumps(summary, indent=1))

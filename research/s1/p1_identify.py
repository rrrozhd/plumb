# Probe 1: fetch vet402's settled XRPL x402 purchases; learn markers (SourceTag, InvoiceID) and merchant payTo accounts.
import csv, json, sys
from collections import Counter
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import Tx
c = JsonRpcClient("https://s2.ripple.com:51234")
rows = [r for r in csv.DictReader(open(sys.argv[1])) if r["network"] == "xrpl:0" and r["tx_hash"]]
out = []
for r in rows:
    res = c.request(Tx(transaction=r["tx_hash"])).result
    tx = res.get("tx_json", {}); m = res.get("meta", {})
    out.append(dict(hash=r["tx_hash"], host=r["resource_key"].split("/")[0], validated=res.get("validated"),
        result=m.get("TransactionResult"), type=tx.get("TransactionType"), account=tx.get("Account"),
        dest=tx.get("Destination"), source_tag=tx.get("SourceTag"), dest_tag=tx.get("DestinationTag"),
        invoice=bool(tx.get("InvoiceID")), memos=len(tx.get("Memos", [])), delivered=m.get("delivered_amount"),
        ledger=res.get("ledger_index"), date=tx.get("date")))
json.dump(out, open(sys.argv[2], "w"), indent=1)
print("fetched", len(out), "validated", sum(1 for o in out if o["validated"]), Counter(o["result"] for o in out))
print("source_tag", Counter(o["source_tag"] for o in out)); print("invoice", Counter(o["invoice"] for o in out), "memos", Counter(o["memos"] for o in out))
print("payers", Counter(o["account"] for o in out))
dests = Counter((o["dest"], o["host"]) for o in out); print("merchants", len({o['dest'] for o in out}))
for (d, h), n in dests.most_common(): print(" ", d, h, n)
print("currencies", Counter((o["delivered"] or {}).get("currency", "XRP") if isinstance(o["delivered"], dict) else "XRP" for o in out))

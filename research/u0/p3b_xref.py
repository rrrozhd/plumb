# U0 probe 3b: who are the live x402 payments in the p3 feed captures? Cross-reference payers and payees with the
# Bazaar's XRPL payTo accounts (p1) and the bot-farm accounts from research/s1 (p4: senders and receivers). Offline.
# usage: uv run --no-project --with httpx --with xrpl-py python research/u0/p3b_xref.py research/u0/p3_run1.json [research/u0/p3_run2.json ...]
import json, sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

bazaar = set(json.loads(Path("research/u0/p1.json").read_text())["census"])
s1 = json.loads(Path("research/s1/p4.json").read_text())
farm_senders, farm_receivers = {r["frm"] for r in s1}, {r["to"] for r in s1}
out = {}
for f in sys.argv[1:]:
    d = json.loads(Path(f).read_text()); rows = d["tagged"]
    value = defaultdict(Decimal)
    for r in rows: value[r["cur"]] += Decimal(r["value"])  # RLUSD as Decimal; XRP in drops
    out[Path(f).name] = dict(window=d["summary"]["ledgers_full"], tagged=len(rows),
                             to_bazaar_payto=sum(r["to"] in bazaar for r in rows),
                             from_s1_farm_senders=sum(r["frm"] in farm_senders for r in rows),
                             to_s1_farm_receivers=sum(r["to"] in farm_receivers for r in rows),
                             receivers=Counter(r["to"] for r in rows).most_common(5),
                             value_by_currency={("RLUSD" if k.startswith("524C5553") else k): str(v) for k, v in value.items()},
                             amounts=Counter(f'{r["value"]} {"RLUSD" if r["cur"].startswith("524C5553") else r["cur"]}' for r in rows).most_common(5))
Path("research/u0/p3b.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))

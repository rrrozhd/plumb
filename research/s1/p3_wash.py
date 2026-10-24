# Probe 3: apply four simple wash rules to the 30-day x402 sample and measure what they flag.
import json, sys, datetime as dt
from collections import Counter, defaultdict
d = json.load(open(sys.argv[1])); pays, outflows, par = d["pays"], d["outflows"], d["parents"]
EPOCH = 946684800; MONITOR = {"r4w68TArDZjivtcFMNL7PvKf7uPg14Vev8"}  # vet402's observatory buyer
day = lambda t: dt.datetime.utcfromtimestamp(t + EPOCH).date().isoformat()
fanout = Counter(par.get(p) for p in {x["frm"] for x in pays} if par.get(p))
burst = Counter((x["frm"], x["to"], round(x["v"], 6), day(x["date"])) for x in pays)
back = {(o["frm"], o["to"]) for o in outflows}
def rules(x):
    p, m = x["frm"], x["to"]; pp, pm = par.get(p), par.get(m); f = set()
    if (pp and pp == pm) or pp == m or pm == p: f.add("R1_self_dealing")
    if pp and fanout[pp] >= 5: f.add("R2_sybil_fanout")
    if burst[(p, m, round(x["v"], 6), day(x["date"]))] >= 50: f.add("R3_identical_burst")
    if (m, p) in back or (pp and (m, pp) in back): f.add("R4_round_trip")
    return f
tags = [(x, rules(x)) for x in pays]
n, v = len(pays), sum(x["v"] for x in pays)
print(f"sample: {n} x402 payments, {len({x['frm'] for x in pays})} payers, {len({x['to'] for x in pays})} merchants, value {v:.2f} ({Counter(x['cur'] for x in pays)})")
print(f"days covered: {min(day(x['date']) for x in pays)} .. {max(day(x['date']) for x in pays)}")
for r in ["R1_self_dealing", "R2_sybil_fanout", "R3_identical_burst", "R4_round_trip"]:
    hit = [x for x, f in tags if r in f]
    print(f"{r:20s} {len(hit):7d} pays ({100*len(hit)/n:5.1f}%)  value {100*sum(x['v'] for x in hit)/max(v,1e-9):5.1f}%")
anyf = [x for x, f in tags if f]
print(f"{'ANY rule':20s} {len(anyf):7d} pays ({100*len(anyf)/n:5.1f}%)  value {100*sum(x['v'] for x in anyf)/max(v,1e-9):5.1f}%")
mon = [x for x in pays if x["frm"] in MONITOR]; print(f"observatory (vet402) {len(mon)} pays")
top = Counter(x["frm"] for x in pays); t10 = sum(c for _, c in top.most_common(10))
print(f"payer concentration: top 10 payers = {100*t10/n:.1f}% of payments; top payer {top.most_common(1)}")
print("parents with >=5 funded payers:", [(p, c) for p, c in fanout.most_common(5) if c >= 5])
print("per merchant (payments, payers, flagged%):")
for m, c in Counter(x["to"] for x in pays).most_common(8):
    mp = [(x, f) for x, f in tags if x["to"] == m]
    print(f"  {m} {c:6d} {len({x['frm'] for x,_ in mp}):4d} {100*sum(1 for _,f in mp if f)/c:5.1f}%")

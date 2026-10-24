# U0 probe 2: operator diversity per need. For each need in eval/queries.yaml (both `queries` and `dropped`), send
# the need text verbatim to Bazaar /search with network=xrpl:0, keep the top N, and count distinct XRPL payTo accounts
# (one payTo = one operator, SPEC §2). Also flags a known non-settling storefront (u0.toml) ranked high, repeats the
# query to check stability, and compares with the unfiltered search filtered client-side. Read-only.
# usage: uv run --no-project --with httpx --with xrpl-py --with pyyaml python research/u0/p2_diversity.py \
#          [eval/queries.yaml] [research/u0/p2.json]
import json, sys, time, tomllib
from collections import Counter
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
import httpx, yaml

CFG = tomllib.loads((Path(__file__).parent / "u0.toml").read_text())
BZ, X, DIV = CFG["bazaar"], CFG["xrpl"], CFG["diversity"]
SRC = sys.argv[1] if len(sys.argv) > 1 else "eval/queries.yaml"
OUT = sys.argv[2] if len(sys.argv) > 2 else "research/u0/p2.json"
doc = yaml.safe_load(Path(SRC).read_text())
needs = (doc.get("queries") or []) + (doc.get("dropped") or [])
c = httpx.Client(timeout=60)

def search(q, network=None):
    params = {"query": q, "limit": BZ["top_n"]} | ({"network": network} if network else {})
    for i in range(4):
        try:
            r = c.get(BZ["base"] + "/search", params=params)
            if r.status_code == 200: return r.json().get("resources", [])
        except httpx.HTTPError: pass
        time.sleep(2 ** i)
    raise RuntimeError(f"search failed: {q!r}")

def xrpl_row(rank, res):  # listing text is untrusted data: we keep only URL, payTo and prices
    acc = [a for a in res.get("accepts", []) if a.get("network") == BZ["network"]]
    if not acc: return None
    rl = next((a for a in acc if a.get("asset") == X["rlusd_currency"] and a.get("extra", {}).get("issuer") == X["rlusd_issuer"]), None)
    xrp = next((a for a in acc if a.get("asset") == "XRP"), None)
    return dict(rank=rank, url=res["resource"], host=urlparse(res["resource"]).hostname, payto=sorted({a["payTo"] for a in acc}),
                price_rlusd=str(Decimal(rl["amount"])) if rl else None, price_xrp_drops=int(xrp["amount"]) if xrp else None,
                assets=sorted({a.get("asset") for a in acc}), source_tags=sorted({a.get("extra", {}).get("sourceTag") or 0 for a in acc}))

out = []
for n in needs:
    runs = [search(n["need"], BZ["network"]) for _ in range(2)]
    rows = [r for r in (xrpl_row(i + 1, x) for i, x in enumerate(runs[0][: BZ["top_n"]])) if r]
    ops = Counter(p for r in rows for p in r["payto"])
    ns_rank = next((r["rank"] for r in rows if r["host"] in DIV["nonsettling_hosts"]), None)
    unf = search(n["need"])
    unf_xrpl = [r for r in (xrpl_row(i + 1, x) for i, x in enumerate(unf[: BZ["top_n"]])) if r]
    qual_ops = len(ops) >= DIV["min_operators"]
    qual_ns = ns_rank is not None and ns_rank <= DIV["nonsettling_max_rank"]
    out.append(dict(id=n["id"], need=n["need"], n_results=len(runs[0]), n_xrpl=len(rows), operators=len(ops),
                    operator_counts=ops.most_common(), nonsettling_rank=ns_rank,
                    qualifies=qual_ops or qual_ns, reason=("operators" if qual_ops else "") + ("+nonsettling" if qual_ns else ""),
                    stable=[x["resource"] for x in runs[0]] == [x["resource"] for x in runs[1]],
                    unfiltered_n=len(unf), unfiltered_xrpl=len(unf_xrpl), unfiltered_operators=len({p for r in unf_xrpl for p in r["payto"]}),
                    top1=rows[0] if rows else None, rows=rows))
    o = out[-1]
    print(f"{o['id']} xrpl={o['n_xrpl']:2d} ops={o['operators']} ns_rank={o['nonsettling_rank']} qual={o['qualifies']!s:5} "
          f"stable={o['stable']!s:5} unfiltered xrpl={o['unfiltered_xrpl']}/{o['unfiltered_n']} ops={o['unfiltered_operators']} "
          f"top1={o['top1']['host'] if o['top1'] else None}")
k = sum(o["qualifies"] for o in out)
summary = dict(at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), source=SRC, needs=len(out), qualifying=k,
               min_qualifying=DIV["min_qualifying"], rule=DIV, all_stable=all(o["stable"] for o in out),
               operators_hist=Counter(o["operators"] for o in out), top1_hosts=Counter(o["top1"]["host"] for o in out if o["top1"]).most_common(),
               nonsettling_in_top_n=sum(o["nonsettling_rank"] is not None for o in out),
               top1_no_rlusd=sum(1 for o in out if o["top1"] and o["top1"]["price_rlusd"] is None),
               top1_non_t54_tag=sum(1 for o in out if o["top1"] and X["source_tag"] not in o["top1"]["source_tags"]))
Path(OUT).write_text(json.dumps(dict(summary=summary, needs=out), indent=1))
print(json.dumps(summary, indent=1))
if k < DIV["min_qualifying"]:
    print(f"\n!!! ONLY {k} NEEDS QUALIFY (< {DIV['min_qualifying']}): switch the demo to BUILD_PLAN U0's fallback "
          "(rerank endpoints within an operator, drop storefronts that won't settle).")

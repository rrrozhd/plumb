# U0 probe 1: the Bazaar search path and its `network` filter (SPEC §11 Q3), then a census of XRPL listings:
# sweep /search with network=xrpl:0 over generic topic words to find XRPL payTo accounts, pull each one's full
# catalogue from /merchant, and tally assets, SourceTags and invoiceIds. Listing text is untrusted: only URLs,
# payTo, assets, amounts and `extra` tags are kept. Read-only.
# usage: uv run --no-project --with httpx --with xrpl-py python research/u0/p1_bazaar.py [research/u0/p1.json] [research/u0/catalog.json.gz]
import gzip, json, sys, time, tomllib
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse
import httpx

CFG = tomllib.loads((Path(__file__).parent / "u0.toml").read_text())
BZ, X = CFG["bazaar"], CFG["xrpl"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "research/u0/p1.json"
CAT = sys.argv[2] if len(sys.argv) > 2 else "research/u0/catalog.json.gz"
c = httpx.Client(timeout=60)

def get(path, **params):
    for i in range(4):
        try:
            r = c.get(BZ["base"] + path, params=params)
            return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200])
        except httpx.HTTPError: time.sleep(2 ** i)
    return None, None

def is_xrpl(res): return any(a.get("network") == BZ["network"] for a in res.get("accepts", []))

# 1. Path and filter.
FILTER_WORDS = ["weather", "crypto price", "news", "sanctions", "whois", "fx rate", "gas fees", "stock price"]
paths = {p: get(p, query="weather")[0] for p in ["/search", "/resources/search", "/search/resources"]}
filt = []
for w in FILTER_WORDS:
    _, un = get("/search", query=w, limit=BZ["top_n"])
    _, fx = get("/search", query=w, network=BZ["network"], limit=BZ["top_n"])
    un, fx = un.get("resources", []), fx.get("resources", [])
    filt.append(dict(query=w, unfiltered=len(un), unfiltered_xrpl=sum(map(is_xrpl, un)), filtered=len(fx), filtered_xrpl=sum(map(is_xrpl, fx))))
other_nets = {n: len(get("/search", query="crypto price", network=n)[1].get("resources", [])) for n in ["xrpl", "xrpl:1", "bogus:0", "eip155:8453"]}
limit5 = len(get("/search", query="crypto price", network=BZ["network"], limit=5)[1].get("resources", []))
_, plain = get("/resources")
_, res_list = get("/resources", network=BZ["network"], limit=5)  # the list endpoint returns `items`
resources_endpoint = dict(returned=len(res_list.get("items", [])), xrpl=sum(map(is_xrpl, res_list.get("items", []))),
                          pagination=res_list.get("pagination"), total_without_network=plain.get("pagination", {}).get("total"))

# 2. Census.
SWEEP = ["weather", "crypto price", "stock price", "news", "sentiment", "translate", "summarize", "search web", "scrape url", "dns",
         "ssl certificate", "domain whois", "email validation", "phone lookup", "ip geolocation", "company data", "sanctions",
         "compliance", "patent", "immigration visa", "tax", "currency exchange rate", "fx rate", "gas fees", "defi yield",
         "token holders", "wallet balance", "nft", "sports scores", "flight status", "shipping tracking", "real estate",
         "job listings", "image generation", "ocr", "pdf", "code review", "security scan", "website uptime", "seo", "recipe",
         "nutrition", "medical", "drug interactions", "legal", "sec filings", "earnings", "macro economic", "inflation",
         "interest rates", "commodities gold", "oil price", "electricity grid", "air quality", "calendar holidays", "time zone",
         "dictionary", "wikipedia", "research papers", "github", "ai agent", "llm", "xrpl", "xrp", "rlusd", "bitcoin",
         "ethereum", "solana", "prediction market", "betting odds", "social media", "music", "movies", "books", "games",
         "debt", "remittance", "arbitrage", "funding rates", "options", "forex", "energy", "carbon", "address risk", "x402"]
payto = set()
for w in SWEEP:
    for res in get("/search", query=w, network=BZ["network"], limit=BZ["top_n"])[1].get("resources", []):
        payto |= {a["payTo"] for a in res["accepts"] if a.get("network") == BZ["network"]}
catalog = {}  # url -> row; a listing can name several XRPL payTo accounts
for p in sorted(payto):
    off = 0
    while True:
        _, d = get("/merchant", payTo=p, limit=100, offset=off)
        items = d.get("resources", [])
        for res in items:
            acc = [a for a in res.get("accepts", []) if a.get("network", "").startswith("xrpl")]
            if res["resource"] in catalog: continue
            catalog[res["resource"]] = dict(url=res["resource"], accepts=[dict(network=a["network"], payTo=a["payTo"], asset=a["asset"],
                                issuer=a.get("extra", {}).get("issuer"), amount=a["amount"], source_tag=a.get("extra", {}).get("sourceTag"),
                                invoice_id=a.get("extra", {}).get("invoiceId")) for a in acc])
        off += 100
        if not items or off >= d["pagination"]["total"]: break
catalog = list(catalog.values())

def asset_name(a):
    if a["asset"] == "XRP": return "XRP"
    if a["asset"] == X["rlusd_currency"] and a["issuer"] == X["rlusd_issuer"]: return "RLUSD"
    return f"{a['asset'][:8]}.{(a['issuer'] or '')[:8]}"
per = defaultdict(lambda: dict(listings=0, hosts=set(), assets=Counter(), source_tags=Counter(), xrp_only=0, xrpl1=0))
for row in catalog:
    acc0 = [a for a in row["accepts"] if a["network"] == BZ["network"]]
    for p in {a["payTo"] for a in acc0}:
        m = per[p]
        m["listings"] += 1; m["hosts"].add(urlparse(row["url"]).hostname)
        m["assets"].update({asset_name(a) for a in acc0}); m["source_tags"].update({a["source_tag"] for a in acc0})
        m["xrp_only"] += all(a["asset"] == "XRP" for a in acc0)
        m["xrpl1"] += any(a["network"] != BZ["network"] for a in row["accepts"])
census = {p: dict(listings=m["listings"], hosts=len(m["hosts"]), top_hosts=sorted(m["hosts"])[:3], assets=dict(m["assets"]),
                  source_tags={str(k): v for k, v in m["source_tags"].items()}, xrp_only=m["xrp_only"], also_xrpl1=m["xrpl1"])
          for p, m in sorted(per.items(), key=lambda kv: -kv[1]["listings"])}
xrpl0 = lambda r: [a for a in r["accepts"] if a["network"] == BZ["network"]]
non_t54 = sum(1 for r in catalog if any(a["source_tag"] != X["source_tag"] for a in xrpl0(r)))
no_t54 = sum(1 for r in catalog if all(a["source_tag"] != X["source_tag"] for a in xrpl0(r)))
rl = [a["amount"] for r in catalog for a in xrpl0(r) if a["asset"] == X["rlusd_currency"]]
xrp = [a["amount"] for r in catalog for a in xrpl0(r) if a["asset"] == "XRP"]
summary = dict(at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), base=BZ["base"], paths=paths, filter=filt,
               other_networks=other_nets, search_limit5_returned=limit5, resources_endpoint_with_network=resources_endpoint,
               payto_accounts=len(census), listings=len(catalog), listings_any_non_t54_option=non_t54, listings_no_t54_option=no_t54,
               listings_xrp_only=sum(1 for r in catalog if all(a["asset"] == "XRP" for a in xrpl0(r))),
               rlusd_amounts=len(rl), rlusd_amounts_with_decimal_point=sum("." in v for v in rl), rlusd_amount_examples=sorted(set(rl))[:8],
               xrp_amounts=len(xrp), xrp_amounts_integer_drops=sum(v.isdigit() for v in xrp),
               listings_with_invoice_id=sum(1 for r in catalog if any(a["invoice_id"] for a in r["accepts"])), census=census)
Path(OUT).write_text(json.dumps(summary, indent=1))
with gzip.open(CAT, "wt") as f: json.dump(catalog, f, separators=(",", ":"))
print(json.dumps({k: v for k, v in summary.items() if k != "census"}, indent=1))
for p, m in census.items(): print(p, m)

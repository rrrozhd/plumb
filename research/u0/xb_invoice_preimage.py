# U0 extra check B: is there a public invoiceId whose SHA-256 equals an on-ledger InvoiceID? If so, a proof-of-purchase
# review ("show the invoiceId behind your payment") could be checked against public data. Candidates:
#   1. vet402's public export: its columns, and `purchase_id` against the InvoiceID of each settled XRPL tx it lists;
#   2. the Bazaar's cached `extra.invoiceId` on every XRPL listing (research/u0/catalog.json.gz) against the InvoiceIDs
#      of recent x402-like payments to the listing's payTo;
#   3. two unpaid 402 challenges per endpoint (no payment), to see whether invoiceIds are per-request nonces.
# Read-only; nothing is signed or paid.
# usage: uv run --no-project --with httpx --with xrpl-py python research/u0/xb_invoice_preimage.py \
#          [vet402.csv | -] [research/u0/catalog.json.gz] [research/u0/xb.json]
import base64, csv, gzip, hashlib, io, json, re, sys, time, tomllib
from collections import Counter, defaultdict
from pathlib import Path
import httpx

CFG = tomllib.loads((Path(__file__).parent / "u0.toml").read_text())
X, BZN = CFG["xrpl"], CFG["bazaar"]["network"]
VET = sys.argv[1] if len(sys.argv) > 1 else "-"
CAT = sys.argv[2] if len(sys.argv) > 2 else "research/u0/catalog.json.gz"
OUT = sys.argv[3] if len(sys.argv) > 3 else "research/u0/xb.json"
PAGES = 3

def rpc(method, **params):
    for i in range(5):
        try:
            r = httpx.post(X["rpc_url"], json={"method": method, "params": [params]}, timeout=60).json()["result"]
            if r.get("status") == "success" or r.get("error") == "txnNotFound": return r
        except Exception: pass
        time.sleep(2 ** i)
    raise RuntimeError(f"rpc {method} failed")

def variants(s):  # ways a seller might derive the 256-bit InvoiceID from an invoiceId string
    out = {"sha256_utf8": s.encode(), "sha256_upper": s.upper().encode(), "sha256_lower": s.lower().encode()}
    out = {k: hashlib.sha256(v).hexdigest().upper() for k, v in out.items()}
    if re.fullmatch(r"(?:[0-9A-Fa-f]{2})+", s): out["sha256_hexbytes"] = hashlib.sha256(bytes.fromhex(s)).hexdigest().upper()
    if re.fullmatch(r"[0-9A-Fa-f]{64}", s): out["raw"] = s.upper()
    return out

def match(cands, onledger):
    hits = []
    for s in cands:
        for k, h in variants(s).items():
            if h in onledger: hits.append(dict(preimage=s, variant=k, invoice_id=h))
    return hits

# 1. vet402.
src = io.StringIO(httpx.get(CFG["vet402"]["export_csv"], timeout=120).text) if VET == "-" else open(VET)
rows = list(csv.DictReader(src)); cols = list(rows[0].keys()) if rows else []
xr = [r for r in rows if r["network"] == BZN]
settled = [r for r in xr if r["tx_hash"]]
vet_hits, vet_inv = [], {}
for r in settled:
    tx = rpc("tx", transaction=r["tx_hash"]); t = tx.get("tx_json") or tx
    if t.get("InvoiceID"): vet_inv[r["tx_hash"]] = t["InvoiceID"].upper()
    vet_hits += match([r["purchase_id"]], {t.get("InvoiceID", "").upper()})
vet = dict(columns=cols, invoice_like_columns=[c for c in cols if "invoice" in c.lower()], xrpl_rows=len(xr),
           settled_with_tx=len(settled), with_invoice_id=len(vet_inv), purchase_id_hits=vet_hits)
print("vet402:", {k: v for k, v in vet.items() if k != "columns"})

# 2. Bazaar cached invoiceIds vs recent on-ledger InvoiceIDs to the same payTo.
catalog = json.load(gzip.open(CAT, "rt"))
cached = defaultdict(set)
for row in catalog:
    for a in row["accepts"]:
        if a["network"] == BZN and a["invoice_id"]: cached[a["payTo"]].add(a["invoice_id"])
onledger, bz_hits = defaultdict(Counter), []  # payTo -> InvoiceID -> payments
for payto in sorted(cached):
    marker = None
    for _ in range(PAGES):
        r = rpc("account_tx", account=payto, limit=400, forward=False, **({"marker": marker} if marker else {}))
        for t in r.get("transactions", []):
            tx, meta = t.get("tx_json") or t.get("tx") or {}, t.get("meta") or {}
            if tx.get("TransactionType") == "Payment" and tx.get("Destination") == payto and tx.get("InvoiceID") and meta.get("TransactionResult") == "tesSUCCESS":
                onledger[payto][tx["InvoiceID"].upper()] += 1
        marker = r.get("marker")
        if not marker: break
    bz_hits += [dict(payto=payto, **h) for h in match(cached[payto], onledger[payto])]
all_onledger = set().union(*map(set, onledger.values())) | set(vet_inv.values())
cross_hits = match(set().union(*cached.values()), all_onledger)  # any cached invoiceId against any InvoiceID seen
bz = dict(listings=len(catalog), cached_invoice_ids=sum(map(len, cached.values())), payto=len(cached),
          onledger_invoice_ids=sum(map(len, onledger.values())), same_payto_hits=bz_hits, any_hits=cross_hits,
          static_ids_per_payto={p: len(ids) for p, ids in cached.items()})
print("bazaar:", bz)

# 3. Fresh unpaid 402 challenges: are invoiceIds per-request?
probe_urls = ["https://api.vextorium.com/v1/crypto-price", "https://api.sitecheck-api.workers.dev/api/crypto/fear-greed",
              "https://api.stablecoingateways.com/v1/business-days", "https://cryptopulse.theaslangroupllc.com/api/funding-check",
              "https://pay.edge-agents.ai/v1/services/perp-funding-rates", "https://presign-guard.fizzl.eu/v1/screen",
              "https://ichimoku-signal.fizzl.eu/scan"]
fresh = {}
for u in probe_urls:
    ids = []
    for _ in range(2):
        try:
            r = httpx.get(u, timeout=30)
            h = r.headers.get("payment-required")
            d = json.loads(base64.b64decode(h)) if h else (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})
            ids.append(sorted(a.get("extra", {}).get("invoiceId") or "" for a in d.get("accepts", []) if a.get("network") == BZN))
        except Exception as e:
            ids.append(f"{type(e).__name__}")
    fresh[u] = dict(status_ok=all(isinstance(i, list) and i for i in ids), distinct_per_request=ids[0] != ids[1], invoice_ids=ids)
    fresh[u]["preimage_on_ledger"] = any(variants(i)["sha256_utf8"] in all_onledger for x in ids if isinstance(x, list) for i in x)
    print(u, fresh[u]["distinct_per_request"], ids)

summary = dict(at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               public_preimage_found=bool(vet_hits or bz_hits or cross_hits),
               vet402_has_invoice_column=bool(vet["invoice_like_columns"]), vet402_purchase_id_hits=len(vet_hits),
               bazaar_cached_ids=bz["cached_invoice_ids"], onledger_ids_checked=len(all_onledger),
               matched_invoice_ids=len(matched := {h["invoice_id"] for h in bz_hits + cross_hits}),
               matched_preimages=sorted({h["preimage"] for h in bz_hits + cross_hits}),
               matched_payments=sum(c[i] for c in onledger.values() for i in matched),
               matched_payto=sorted({h["payto"] for h in bz_hits}),
               x402_like_payments_checked=sum(sum(c.values()) for c in onledger.values()),
               challenge_ids_fresh_per_request=[u for u, v in fresh.items() if v["status_ok"] and v["distinct_per_request"]],
               challenge_ids_static=[u for u, v in fresh.items() if v["status_ok"] and not v["distinct_per_request"]],
               challenge_endpoints_ok=sum(v["status_ok"] for v in fresh.values()))
Path(OUT).write_text(json.dumps(dict(summary=summary, vet402=vet, bazaar=bz, challenges=fresh), indent=1))
print(json.dumps(summary, indent=1))

# Recompute XRPL purchase outcomes from vet402's public export (data drifts as vet402 keeps buying).
# usage: uv run python research/vet402/xrpl_outcomes.py [export.csv]   (downloads the export if no path given)
import csv, io, statistics, sys, urllib.request
URL = "https://vet402.com/api/v1/observatory/export.csv"
src = open(sys.argv[1]) if len(sys.argv) > 1 else io.StringIO(urllib.request.urlopen(URL, timeout=60).read().decode())
rows = [r for r in csv.DictReader(src) if r["network"] == "xrpl:0"]
good = [r for r in rows if r["status"] == "settled" and r["http_status_paid"].startswith("2") and r["l2_reading"] != "mismatch"]
amounts = [int(r["amount_units"]) / 1e6 for r in rows if r["amount_units"]]  # RLUSD in 6-decimal units (assumption: matches vet402's other assets)
print(f"XRPL attempts {len(rows)}, usable {len(good)} ({100*len(good)/max(len(rows),1):.0f}%), hosts {len({r['resource_key'].split('/')[0] for r in rows})}")
print(f"price per attempt (RLUSD): median {statistics.median(amounts):.4f}, mean {statistics.mean(amounts):.4f}, min {min(amounts):.4f}, max {max(amounts):.4f}")
wasted = sum(int(r["spent_units"] or 0) for r in rows if r["status"] == "settled" and r not in good) / 1e6
spent = sum(int(r["spent_units"] or 0) for r in rows if r["status"] == "settled") / 1e6
print(f"RLUSD spent on settled purchases {spent:.4f}, of which on unusable results {wasted:.4f}; waste per usable answer {wasted/max(len(good),1):.4f}")

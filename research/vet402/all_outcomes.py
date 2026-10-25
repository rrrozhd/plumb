# E3: x402 purchase outcomes across all chains from vet402's public export (the export grows; numbers drift).
# usage: uv run --no-project python -I research/vet402/all_outcomes.py [export.csv]   (downloads the export if no path given)
import csv, io, sys, urllib.request
URL = "https://vet402.com/api/v1/observatory/export.csv"
src = open(sys.argv[1]) if len(sys.argv) > 1 else io.StringIO(urllib.request.urlopen(URL, timeout=90).read().decode())
rows = list(csv.DictReader(src))
good = lambda r: r["status"] == "settled" and r["http_status_paid"].startswith("2") and r["l2_reading"] != "mismatch"  # same rule as E2
tried = [r for r in rows if r["status"] in ("settled", "settle_failed", "delivered_no_receipt", "settle_claimed")]  # a payment was attempted
paid = [r for r in rows if r["status"] == "settled"]
g = sum(map(good, tried))
print(f"rows {len(rows)} ({min(r['attempted_at'] for r in rows)[:10]} to {max(r['attempted_at'] for r in rows)[:10]})")
print(f"payment attempted {len(tried)}: usable {g} ({g/len(tried):.0%}), not usable {len(tried)-g} ({1-g/len(tried):.0%})")
print(f"  of which the payment never settled: {sum(r['status'] == 'settle_failed' for r in tried)}")
print(f"settled (money moved) {len(paid)}: unusable answer {len(paid)-g} ({(len(paid)-g)/len(paid):.0%})")

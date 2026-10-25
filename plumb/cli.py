"""plumb CLI. `plumb snapshot` freezes the real market data the demo and tests run on (RECOMMENDER R1)."""
import argparse
import csv
import gzip
import io
import json
import sys
from datetime import datetime, timezone

import httpx
import yaml

from plumb import catalog, config, ledger


def _log(msg: str) -> None:
    print(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "msg": msg}), file=sys.stderr)


def snapshot(cfg: dict) -> None:
    out = config.ROOT / "data"
    out.mkdir(exist_ok=True)
    needs = yaml.safe_load(config.path(cfg, "queries").read_text())["queries"]
    bz, lg = catalog.Bazaar(cfg), ledger.Ledger(cfg)

    search = {q["id"]: bz.search(q["need"]) for q in needs}
    _log(f"bazaar search: {sum(map(len, search.values()))} results for {len(search)} needs")

    paytos = {a["payTo"] for rs in search.values() for r in rs for a in r.get("accepts", []) if a.get("network") == cfg["xrpl"]["network"]}
    listings = {}
    for p in sorted(paytos):
        for r in bz.merchant(p):
            listings[r["resource"]] = r
    _log(f"catalog: {len(listings)} listings under {len(paytos)} payTo")

    raw = httpx.get(cfg["vet402"]["export_csv"], timeout=120).text
    rows = [r for r in csv.DictReader(io.StringIO(raw)) if r["network"] == cfg["xrpl"]["network"]]
    with (out / "vet402_xrpl.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    _log(f"vet402: {len(rows)} XRPL rows")

    payments = [p for t in sorted(paytos) for p in lg.payments_to(t)]
    payers = sorted({p["payer"] for p in payments})
    accounts = [a for a in (lg.account_created(p) for p in payers) if a]
    _log(f"ledger: {len(payments)} x402-like payments from {len(payers)} payers")

    meta = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "xrp_in_rlusd": str(lg.xrp_in_rlusd()),
            "needs": len(search), "listings": len(listings), "paytos": len(paytos), "vet402_rows": len(rows),
            "payments": len(payments), "payers": len(payers)}
    (out / "bazaar_search.json").write_text(json.dumps(search, indent=1))
    with gzip.open(out / "catalog.json.gz", "wt") as fh:
        json.dump(sorted(listings.values(), key=lambda r: r["resource"]), fh)
    (out / "ledger_payments.json").write_text(json.dumps(payments, indent=1))
    (out / "accounts.json").write_text(json.dumps(accounts, indent=1))
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    _log(f"snapshot written: {meta}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="plumb")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="freeze Bazaar, vet402 and ledger data into data/ (read-only, network)")
    args = ap.parse_args(argv)
    cfg = config.load()
    if args.cmd == "snapshot":
        snapshot(cfg)


if __name__ == "__main__":
    main()

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


def _load_env(name: str) -> None:
    """Load one process's secrets file into the environment (AGENTS.md rule 5). Values are never printed."""
    import os
    for line in (config.ROOT / "env" / name).read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _cold_judge(cfg: dict):
    """The offline judge, callable on the cold path for a need nobody judged yet (labels cached after one use)."""
    from anthropic.lib.bedrock import AnthropicBedrock
    from plumb import judge
    client = AnthropicBedrock(aws_region=cfg["judge"]["region"])
    return lambda need, listings: judge.judge(client, cfg, need, listings)


def build(cfg: dict, judge_needs: bool) -> None:
    """Offline: embed every listing and need template (Titan), then judge known needs (Bedrock). Writes data/."""
    import numpy as np
    from anthropic.lib.bedrock import AnthropicBedrock
    from plumb import judge, relevance

    _load_env("judge.env")
    root = config.ROOT / "data"
    eps = catalog.load_endpoints(cfg, root)
    ids = sorted(eps)
    titan = relevance.Titan(cfg)
    cap = cfg["judge"]["max_listing_chars"]

    vec_path = root / "listing_vectors.npy"
    if not vec_path.exists() or json.loads((root / "listing_ids.json").read_text()) != ids:
        vecs = titan.embed_many([relevance.doc_text(eps[i], cap) for i in ids])
        np.save(vec_path, np.array(vecs, dtype=np.float32))
        (root / "listing_ids.json").write_text(json.dumps(ids))
        _log(f"embedded {len(ids)} listings")

    needs = yaml.safe_load(config.path(cfg, "queries").read_text())["queries"]
    need_vecs_path = root / "need_vectors.json"
    need_vecs = json.loads(need_vecs_path.read_text()) if need_vecs_path.exists() else {}
    for q in needs:
        t = relevance.template(q["need"])
        if t not in need_vecs:
            need_vecs[t] = titan.embed(t)
    need_vecs_path.write_text(json.dumps(need_vecs))
    if not judge_needs:
        return

    vectors = relevance.Vectors.load(root)
    search = json.loads((root / "bazaar_search.json").read_text())
    client = AnthropicBedrock(aws_region=cfg["judge"]["region"])
    fit_path = config.path(cfg, "fit")
    fit = json.loads(fit_path.read_text()) if fit_path.exists() else {}
    for q in needs:
        t = relevance.template(q["need"])
        if t in fit:
            continue
        bazaar = [e.id for e in (catalog.parse_listing(r, cfg) for r in search[q["id"]]) if e and e.id in eps]
        emb = [i for i, _ in vectors.top(np.array(need_vecs[t]), cfg["rank"]["embed_top"])]
        cands = list(dict.fromkeys(bazaar + emb))[: cfg["judge"]["candidates_per_need"]]
        groups: dict[str, list[dict]] = {}
        for i in cands:
            e = eps[i]
            groups.setdefault(e.payto, []).append({"id": i, "service": e.service_name, "url": e.url, "tags": ", ".join(e.tags),
                                                   "input": e.input_example, "description": e.description})
        labels = {}
        from concurrent.futures import ThreadPoolExecutor
        # one retry: a refusal returns nothing and would silently drop the operator's listings
        once = lambda g: judge.judge(client, cfg, q["need"], g) or judge.judge(client, cfg, q["need"], g)
        with ThreadPoolExecutor(8) as pool:  # one call per operator, in parallel
            for g, part in zip(groups.values(), pool.map(once, groups.values())):
                if not part:
                    _log(f"judge returned no labels for {q['id']} operator {eps[g[0]['id']].payto} ({len(g)} listings)")
                labels.update(part)
        fit[t] = {"need_id": q["id"], "need": q["need"], "labels": labels}
        fit_path.write_text(json.dumps(fit, indent=1))
        _log(f"judged {q['id']}: {len(labels)} of {len(cands)} candidates over {len(groups)} operators")


def liveness(cfg: dict) -> None:
    """Offline preflight (added after E19): an endpoint is dead unless it answers unpaid with an x402 challenge."""
    from concurrent.futures import ThreadPoolExecutor
    from plumb.eval_free import _challenge
    root = config.ROOT / "data"
    with gzip.open(root / "catalog.json.gz", "rt") as fh:
        raw = {r["resource"]: r for r in json.load(fh)}
    eps = catalog.load_endpoints(cfg, root)
    ids = sorted({e for v in json.loads((root / "fit.json").read_text()).values() for e in v["labels"]})
    with httpx.Client(timeout=10) as http, ThreadPoolExecutor(8) as pool:
        res = list(pool.map(lambda i: _challenge(raw[eps[i].url], http), ids))
    out = {i: {"alive": r["status"] == 402 and bool(r.get("accepts")), "http": r["status"]} for i, r in zip(ids, res)}
    (root / "liveness.json").write_text(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "endpoints": out}, indent=1))
    _log(f"liveness: {sum(v['alive'] for v in out.values())} of {len(out)} judged candidates answer with an x402 challenge")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="plumb")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="freeze Bazaar, vet402 and ledger data into data/ (read-only, network)")
    b = sub.add_parser("build", help="offline: Titan embeddings and the Bedrock judge over known needs (writes data/)")
    b.add_argument("--no-judge", action="store_true")
    r = sub.add_parser("recommend", help="one shortlist, printed as JSON")
    r.add_argument("need")
    r.add_argument("--as", dest="principal")
    r.add_argument("-k", type=int, default=3)
    r.add_argument("--db", help="customer memory database (defaults to configured store)")
    sub.add_parser("bench", help="p50/p95 shortlist latency over the known needs")
    sub.add_parser("liveness", help="offline: probe every judged candidate unpaid; dead endpoints are excluded from ranking")
    ep = sub.add_parser("eval-paid", help="U7 paid head-to-head; dry-run unless --live")
    ep.add_argument("--live", action="store_true")
    ep.add_argument("--grader", type=int, default=1, choices=[1, 2])
    ep.add_argument("--resume", help="earlier live report: keep its completed purchases, retry the unsettled ones")
    e21 = sub.add_parser("e21", help="E21 three-arm head-to-head per eval/e21_prereg.md; dry-run unless --live")
    e21.add_argument("--live", action="store_true")
    e22 = sub.add_parser("e22", help="E22 held-out needs, judge v2, per eval/e22_prereg.md; dry-run unless --live")
    e22.add_argument("--live", action="store_true")
    e26 = sub.add_parser("e26", help="E26 powered needs (100, code-checked), per eval/e26_prereg.md; dry-run unless --live")
    e26.add_argument("--live", action="store_true")
    sub.add_parser("eval-free", help="U7 without money: probe Bazaar #1 vs Plumb #1 for each frozen need")
    args = ap.parse_args(argv)
    cfg = config.load()
    if args.cmd in ("recommend", "bench"):
        from plumb import db, outcomes, rank
        embed = judge_fn = None
        if args.cmd == "recommend" and (config.ROOT / "env" / "judge.env").exists():
            from plumb import relevance
            _load_env("judge.env")
            embed = relevance.Titan(cfg).embed  # one cached Titan call for a need template never seen before
            judge_fn = _cold_judge(cfg)
        conn = db.connect(args.db or config.path(cfg, "db")) if args.cmd == "recommend" else None
        rk = rank.load(cfg, config.ROOT / "data", embed=embed, judge=judge_fn if args.cmd == "recommend" else None, conn=conn)
        if args.cmd == "recommend":
            out = rk.shortlist(args.need, k=args.k, principal=args.principal)
            assert conn is not None
            outcomes.save_shortlist(conn, out, args.need, datetime.now(timezone.utc))
            print(json.dumps(out, indent=1))
            conn.close()
        else:
            import platform
            import statistics
            needs = [v["need"] for v in rk.fit.values()] * 50
            ms = sorted(rk.shortlist(n)["timing_ms"]["total"] for n in needs)
            print(json.dumps({"n": len(ms), "p50_ms": statistics.median(ms), "p95_ms": ms[int(0.95 * len(ms))],
                              "machine": platform.platform(), "cpu": platform.processor()}))
        return
    if args.cmd == "liveness":
        liveness(cfg)
        return
    if args.cmd in ("e22", "e26"):
        from plumb import eval_paid
        rep = eval_paid.run_e22(cfg, live=args.live, name=args.cmd)
        print(json.dumps({k: rep[k] for k in ("mode", "summary", "spent_total_rlusd", "path")} | ({"picks": rep["picks"]} if rep["mode"] == "dry-run" else {}), indent=1, default=str))
        return
    if args.cmd == "e21":
        from plumb import eval_paid
        rep = eval_paid.run_e21(cfg, live=args.live)
        print(json.dumps({"mode": rep["mode"], "summary": rep["summary"], "spent_total_rlusd": rep["spent_total_rlusd"], "report": rep["path"]}, indent=1))
        return
    if args.cmd == "eval-paid":
        from plumb import eval_paid
        rep = eval_paid.run(cfg, live=args.live, resume=args.resume, grader_version=args.grader)
        print(json.dumps({"mode": rep["mode"], "summary": rep["summary"], "spent_total_rlusd": rep["spent_total_rlusd"], "report": rep["path"]}, indent=1))
        return
    if args.cmd == "eval-free":
        from plumb import eval_free
        rep = eval_free.run(cfg)
        print(json.dumps({"summary": rep["summary"], "report": rep["path"]}, indent=1))
        return
    if args.cmd == "snapshot":
        snapshot(cfg)
    elif args.cmd == "build":
        build(cfg, judge_needs=not args.no_judge)


if __name__ == "__main__":
    main()

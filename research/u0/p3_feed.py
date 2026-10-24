# U0 probe 3: subscribe to the public `transactions` + `ledger` streams for N seconds and count x402 payments
# (SourceTag from u0.toml). Then rescan the same ledgers over JSON-RPC to check the stream missed nothing, and
# measure arrival latency against ledger close time. Read-only.
# usage: uv run --no-project --with httpx --with xrpl-py python research/u0/p3_feed.py [seconds=600] [out=research/u0/p3_run2.json]
import asyncio, datetime as dt, json, statistics, sys, time, tomllib
from collections import Counter
from decimal import Decimal
from pathlib import Path
import httpx, websockets

CFG = tomllib.loads((Path(__file__).parent / "u0.toml").read_text())["xrpl"]
TAG, EPOCH = CFG["source_tag"], CFG["ripple_epoch"]
SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 600
OUT = sys.argv[2] if len(sys.argv) > 2 else "research/u0/p3_run2.json"

def amount(d):  # RLUSD/IOU -> (currency, Decimal string); XRP -> ("XRP", int drops as string)
    if isinstance(d, str): return "XRP", str(int(d))
    if isinstance(d, dict): return d.get("currency"), str(Decimal(d["value"]))
    return None, None

def rpc(method, **params):
    for i in range(4):
        try:
            r = httpx.post(CFG["rpc_url"], json={"method": method, "params": [params]}, timeout=60).json()["result"]
            if r.get("status") == "success": return r
        except Exception: pass
        time.sleep(2 ** i)
    raise RuntimeError(f"rpc {method} failed")

def server_offset():  # server clock minus local clock, seconds
    t = rpc("server_info")["info"]["time"]  # e.g. 2026-Oct-24 22:01:23.456789 UTC
    s = dt.datetime.strptime(t.replace(" UTC", ""), "%Y-%b-%d %H:%M:%S.%f").replace(tzinfo=dt.UTC).timestamp()
    return s - time.time()

async def listen():
    ledgers, tagged, payments, gaps = {}, {}, Counter(), []
    end = time.time() + SECS
    while time.time() < end:
        try:
            async with websockets.connect(CFG["wss_url"], open_timeout=30, max_size=2**24) as ws:
                await ws.send(json.dumps({"id": 1, "command": "subscribe", "streams": ["ledger", "transactions"]}))
                while time.time() < end:
                    try: raw = await asyncio.wait_for(ws.recv(), timeout=max(1, end - time.time()))
                    except asyncio.TimeoutError: break
                    now, m = time.time(), json.loads(raw)
                    if m.get("type") == "ledgerClosed":
                        ledgers[m["ledger_index"]] = dict(close=m["ledger_time"] + EPOCH, recv=now, txn_count=m.get("txn_count"))
                    elif m.get("type") == "transaction":
                        tx = m.get("tx_json") or m.get("transaction") or {}
                        if tx.get("TransactionType") != "Payment": continue
                        payments[m.get("ledger_index")] += 1
                        if tx.get("SourceTag") != TAG: continue
                        meta = m.get("meta") or {}
                        cur, val = amount(meta.get("delivered_amount"))
                        h = m.get("hash") or tx.get("hash")
                        tagged[h] = dict(hash=h, ledger=m.get("ledger_index"), recv=now, validated=m.get("validated"),
                                         result=m.get("engine_result") or meta.get("TransactionResult"),
                                         frm=tx.get("Account"), to=tx.get("Destination"), cur=cur, value=val,
                                         invoice=bool(tx.get("InvoiceID")), tx_date=(tx.get("date") or 0) + EPOCH if tx.get("date") else None)
        except Exception as e:
            gaps.append(dict(at=time.time(), error=f"{type(e).__name__}: {e}"))
            await asyncio.sleep(2)
    return ledgers, tagged, payments, gaps

offset = server_offset()
t0 = time.time()
ledgers, tagged, stream_payments, gaps = asyncio.run(listen())
t1 = time.time()
seen = sorted(ledgers)
lo, hi = seen[1], seen[-1]  # the first ledger may be partial: start from the second full one

# Completeness: rescan [lo, hi] over JSON-RPC.
scan, scan_payments = {}, 0
for li in range(lo, hi + 1):
    led = rpc("ledger", ledger_index=li, transactions=True, expand=True)["ledger"]
    for t in led.get("transactions", []):
        tx = t.get("tx_json", t); meta = t.get("meta") or t.get("metaData") or {}
        if tx.get("TransactionType") != "Payment": continue
        scan_payments += 1
        if tx.get("SourceTag") == TAG: scan[t.get("hash") or tx.get("hash")] = dict(ledger=li, result=meta.get("TransactionResult"))
in_range = {h: r for h, r in tagged.items() if lo <= (r["ledger"] or 0) <= hi}
missed, extra = sorted(set(scan) - set(in_range)), sorted(set(in_range) - set(scan))

# Latency: local receive time (corrected to the server clock) minus the ledger's close time.
# Ledger close times are rounded to the close-time resolution (usually 10 s), so this is approximate.
lat = [r["recv"] + offset - ledgers[r["ledger"]]["close"] for r in in_range.values() if r["ledger"] in ledgers]
vs_ledger_msg = [r["recv"] - ledgers[r["ledger"]]["recv"] for r in in_range.values() if r["ledger"] in ledgers]
q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))] if xs else None
summary = dict(
    wss=CFG["wss_url"], rpc=CFG["rpc_url"], started=dt.datetime.fromtimestamp(t0, dt.UTC).isoformat(), seconds=round(t1 - t0),
    ledgers_full=[lo, hi], n_ledgers=hi - lo + 1, reconnects=len(gaps), gaps=gaps, server_clock_offset_s=round(offset, 3),
    stream_payments_in_range=sum(n for li, n in stream_payments.items() if lo <= (li or 0) <= hi), scan_payments=scan_payments,
    tagged_stream=len(in_range), tagged_scan=len(scan), missed_by_stream={h: scan[h]["ledger"] for h in missed}, extra_in_stream=extra,
    ledgers_without_stream_msg=sorted(set(range(lo, hi + 1)) - set(ledgers)),
    all_validated=all(r["validated"] for r in in_range.values()),
    results=Counter(r["result"] for r in in_range.values()), currencies=Counter(r["cur"] for r in in_range.values()),
    senders=len({r["frm"] for r in in_range.values()}), receivers=Counter(r["to"] for r in in_range.values()).most_common(),
    with_invoice_id=sum(r["invoice"] for r in in_range.values()),
    latency_close_to_recv_s=dict(median=round(statistics.median(lat), 2) if lat else None, p95=round(q(lat, .95), 2) if lat else None, max=round(max(lat), 2) if lat else None),
    latency_vs_ledgerClosed_msg_s=dict(median=round(statistics.median(vs_ledger_msg), 3) if vs_ledger_msg else None, max=round(max(vs_ledger_msg), 3) if vs_ledger_msg else None),
    rate_per_day=round(len(in_range) / max((ledgers[hi]["close"] - ledgers[lo]["close"]), 1) * 86400),
)
Path(OUT).write_text(json.dumps(dict(summary=summary, tagged=list(in_range.values())), indent=1, default=str))
print(json.dumps(summary, indent=1, default=str))

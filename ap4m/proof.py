"""Assemble one completed AP4M run into the evidence Mastercard asks to see, for the deck: site/public/ap4m-proof.json.

Sources, all written during the run: the agent's trail (out/ap4m-agent/trail-<run>.jsonl), the merchant's store
(the 402 challenge it issued, the agent's signed payment header, the VoucherRedeemed tx, the resource it released)
and AP4M's public claim receipt. Everything here is public on-chain data; no key or token is read.

Usage: uv run python ap4m/proof.py run-mvndvux0
"""
import base64, json, sqlite3, sys
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
WEI = Decimal(10) ** 18
rlusd = lambda wei: str(Decimal(wei) / WEI)

run = sys.argv[1]
trail = [json.loads(l) for l in (ROOT / f"out/ap4m-agent/trail-{run}.jsonl").read_text().splitlines()]
ev = lambda name: [e for e in trail if e["event"] == name]
opened, settled = ev("channel_open")[0], ev("settled")[0]
channel = opened["channel_id"]

db = sqlite3.connect(f"file:{ROOT / 'out/ap4m-merchant/merchant.sqlite'}?mode=ro", uri=True)
identity = json.loads(db.execute("SELECT value FROM identity").fetchone()[0])
rows = {json.loads(v)["transactionHash"]: (d, json.loads(v)) for d, v in
        db.execute("SELECT voucher_digest, value FROM payments WHERE channel_id = ? AND complete = 1", (channel,))}
released = dict(db.execute("SELECT voucher_digest, content FROM resource_results"))

purchases = []
for paid, listed in zip(ev("paid"), ev("shortlist")):
    digest, p = rows[paid["voucher_redeemed_tx"]]
    challenge = p["challenge"]["value"]
    signed = json.loads(base64.b64decode(p["header"]))
    req = signed["accepted"]
    purchases.append({
        "need": paid["need"],
        "requirement": {"status": 402, "scheme": req["scheme"], "network": req["network"], "amount_rlusd": rlusd(req["amount"]),
                        "asset": req["asset"], "pay_to": req["payTo"], "channel_id": req["extra"]["channelId"],
                        "merchant": challenge["merchantParticipantId"], "valid_before": challenge["validBefore"],
                        "challenge_digest": p["challenge"]["digest"]},
        "voucher": {"cumulative_rlusd": rlusd(signed["payload"]["voucher"]["cumulativeAmount"]),
                    "previous_rlusd": rlusd(challenge["previousCumulativeAmount"]),
                    "agent_signature": signed["payload"]["agentSignature"], "resource_digest": signed["payload"]["resourceDigest"]},
        "redeemed_tx": paid["voucher_redeemed_tx"], "claim_id": paid["claim_id"],
        "resource": {"status": 200, "content": json.loads(released[digest]) if digest in released else None},
        "shortlist": {"id": listed["shortlist_id"], "budget_left_rlusd": listed["mandate"]["budget_left_rlusd"],
                      "top": listed["results"][0]["url"] if listed["results"] else None},
    })

receipt = httpx.get(settled["receipt_url"], timeout=20).raise_for_status().json()
se, vault = receipt["settlementEvidence"], receipt["vaultPayoutEvidence"]
proof = {
    "run": run, "at": opened["at"],
    "identities": {"team": ev("signed_in")[0]["team"], "agent": ev("signed_in")[0]["agent"],
                   "team_budget_rlusd": ev("signed_in")[0]["budget_rlusd"], "merchant": identity["merchantParticipantId"],
                   "payout": identity["payout"], "agent_psp": se["agentPspId"], "merchant_psp": se["merchantPspId"],
                   "ledger": se["context"]["ledger"], "chain_id": se["context"]["chainId"]},
    "channel": {"id": channel, "cap_rlusd": opened["cap_rlusd"], "per_purchase_rlusd": opened["per_purchase_rlusd"]},
    "purchases": purchases,
    "refused": ev("refused_over_cap")[0],
    "settlement": {"claims_settled": settled["claims_settled"], "payout_tx": settled["payout_tx"],
                   "settlement_tx": settled["settlement_tx"], "recipient": settled["recipient"], "receipt_url": settled["receipt_url"],
                   "receipt": {"schema": receipt["schemaId"], "status": se["status"], "channel_id": se["channelId"],
                               "claim_id": se["claimId"], "amount_rlusd": rlusd(se["amount"]),
                               "payout_tx": vault["transactionHash"], "cumulative_disbursed_rlusd": rlusd(vault["cumulativeDisbursed"]),
                               "settlement_tx": receipt["settlementTransaction"]["transactionHash"],
                               "venue": se["venueId"]}},
}
assert proof["settlement"]["receipt"]["channel_id"] == channel and proof["settlement"]["receipt"]["payout_tx"] == settled["payout_tx"]
out = ROOT / "site/public/ap4m-proof.json"
out.write_text(json.dumps(proof, indent=1))
print(out, len(purchases), "purchases")

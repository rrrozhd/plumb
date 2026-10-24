# Check 2: does t54's TESTNET facilitator /verify accept a multisig payer? Single-sig control vs multisig. Verify only, no settle.
import hashlib, json, httpx
from xrpl.clients import JsonRpcClient
from xrpl.wallet import generate_faucet_wallet, Wallet
from xrpl.models.transactions import Payment, SignerListSet, SignerEntry, AccountSet, AccountSetAsfFlag
from xrpl.transaction import autofill, sign, multisign, submit_and_wait
from xrpl.core.binarycodec import encode
c = JsonRpcClient("https://s.altnet.rippletest.net:51234"); FAC = "https://xrpl-facilitator-testnet.t54.ai"
TAG, INV = 804681468, "M1-CHECK-001"
merchant, single, multi = (generate_faucet_wallet(c) for _ in range(3))
agent, cosigner = Wallet.create(), Wallet.create()
submit_and_wait(SignerListSet(account=multi.address, signer_quorum=2, signer_entries=[SignerEntry(account=agent.address, signer_weight=1), SignerEntry(account=cosigner.address, signer_weight=1)]), c, multi)
submit_and_wait(AccountSet(account=multi.address, set_flag=AccountSetAsfFlag.ASF_DISABLE_MASTER), c, multi)
req = {"scheme": "exact", "network": "xrpl:1", "asset": "XRP", "payTo": merchant.address, "amount": "100000", "maxTimeoutSeconds": 600,
       "extra": {"areFeesSponsored": False, "assetTransferMethod": "sequence", "invoiceId": INV, "sourceTag": TAG}}
def pay(acct):
    return Payment(account=acct, destination=merchant.address, amount="100000", source_tag=TAG,
                   invoice_id=hashlib.sha256(INV.encode()).hexdigest().upper())
def ask(blob, label):
    body = {"x402Version": 2, "paymentPayload": {"x402Version": 2, "accepted": req, "payload": {"signedTxBlob": blob, "invoiceId": INV}}, "paymentRequirements": req}
    r = httpx.post(FAC + "/verify", json=body, timeout=30)
    print(f"{label:28s} HTTP {r.status_code} {r.text[:220]}")
s = sign(autofill(pay(single.address), c), single); ask(s.blob(), "single-sig payer")
t = autofill(pay(multi.address), c, signers_count=2)
m = multisign(t, [sign(t, agent, multisign=True), sign(t, cosigner, multisign=True)]); ask(m.blob(), "multisig payer (agent+cosigner)")

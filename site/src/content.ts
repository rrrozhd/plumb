// Every number here comes from the evaluation data in data/ under the id shown next to it (locked by tests/test_evidence_numbers.py).
// `notes` is the speaker script: shown in the notes drawer and used as the backup video's narration.

export const DEMO = {
  problemNeed: "Current BTC perpetual futures funding rate on major exchanges",
  mandateNeed: "Current weather and 3-day forecast for New York City",
  personalNeed: "Verify XRPL transaction 65A456656B9479457C0995E2FC770319C7636C39550DF4A4E127D265ADB90795: was it validated and what amount did it deliver?",
  rlusdAccount: "r4w68TArDZjivtcFMNL7PvKf7uPg14Vev8",
  xrpOnlyAccount: "rNperfygoY9USDAfYeXh9itC2TnydbycMY",
  agentNeeds: ["Current weather and 3-day forecast for New York City", "Current weather and 3-day forecast for New York City", "Current XRP price in USD"],
  agentCap: "0.005",
  openMandate: "0.05",
  tightMandate: "0.002",
}

export const E = {
  e1: { id: "E1", text: "Bazaar call counts run 5–300× the payments that actually settled" },
  e2: { id: "E2", text: "64 of 202 real XRPL x402 purchases (32%) returned a usable answer" },
  edge: { id: "E2", text: "pay.edge-agents.ai: 0 of 88 real purchases settled" },
  e3: { id: "E3", text: "of 17,684 real x402 purchase attempts across chains got no usable answer" },
  e29: { id: "E29", text: "paid APIs listed in the Coinbase x402 Bazaar, across chains" },
  e4: { id: "E4", text: "46 payer accounts created within 4 minutes, each with 1,196+ payments" },
  l4: { id: "E11", text: "3,207 XRPL listings, but only 15 payout accounts" },
  e18: { id: "E18", text: "AP4M end to end on testnet: capped channel, paid shortlists, over-cap refusal, settled receipt" },
  e25: { id: "E25", text: "0.13 ms worst-5% per shortlist, no LLM on the request path" },
}

export const E21 = [
  { arm: "Coinbase Bazaar #1", good: 7, cost: "0.0133" },
  { arm: "Plumb #1 (fee incl.)", good: 11, cost: "0.0068" },
  { arm: "fizzl (buys any chain)", good: 13, cost: "0.0277" },
]

export const POOLED = {
  needs: 30, plumb: 19, bazaar: 14, won: 6, lost: 1, p: "0.125",
  costPlumb: "0.0060", costBazaar: "0.0080", ratioCi: "0.69–2.33", fizzlCi: "2.6–6×",
  heldOut: { plumb: 8, bazaar: 7, of: 10 },
}

export type SlideMeta = { id: string; kicker: string; title: string; notes: string; auto: boolean; cues: string[] }

// cues: what the presenter reads out, one short line each (presenter window, `n` drawer)
export const SLIDES: SlideMeta[] = [
  { id: "title", kicker: "Agentic Finance · XRPL", title: "Whom should your agent pay?", auto: false,
    cues: [
      "AI agents can now pay for things themselves, per call, with no human checking.",
      "Paying is solved. Knowing WHOM to pay is not.",
      "Plumb answers that: three merchants with proof they deliver, inside the agent's budget.",
    ],
    notes: "AI agents can now pay for things on their own. The hard part is no longer paying. It is knowing whom to pay. Plumb answers that question, for each agent, with evidence from the ledger." },
  { id: "why", kicker: "Why it matters", title: "When software pays, nobody checks the seller", auto: false,
    cues: [
      "There are over 42 thousand paid APIs an agent can buy from today. (E29)",
      "Public data from vet402: of 17,684 real purchase attempts across chains, 44% got no usable answer. (E3)",
      "Mostly the payment never went through; and 1 in 7 paid calls returned an error or the wrong data.",
      "On the XRP Ledger it was worse: 2 out of 3 attempts got nothing usable. (E2)",
      "Payment rails now decide HOW an agent may pay. Nothing decides WHOM. That's the gap.",
    ],
    notes: "There are over forty-two thousand paid APIs an agent can buy from. Of seventeen thousand real purchase attempts, forty-four percent got nothing usable; on the XRP Ledger, two in three. Payment rails decide how an agent may pay. Nothing decides whom." },
  { id: "problem", kicker: "The problem", title: "The market's #1 has never delivered", auto: true,
    cues: [
      "This is Coinbase's x402 Bazaar, live: the catalogue agents use to find merchants.",
      "I ask it for a bitcoin funding rate on XRPL. Look at its number one.",
      "pay.edge-agents.ai: 0 successful purchases out of 88 real attempts.",
      "It ranks first because the Bazaar counts activity, and failed purchases still count.",
      "Call counts run 5 to 300 times the payments that actually went through. (E1)",
    ],
    notes: "This is Coinbase's x402 Bazaar, live. Its number one result failed eighty-eight out of eighty-eight real purchases. It ranks first because the Bazaar counts activity, and failed purchases still count as activity." },
  { id: "router", kicker: "Plumb", title: "One call, three merchants with evidence", auto: true,
    cues: [
      "Same question, asked to Plumb.",
      "Three merchants, one per company, each with price and proof of past payments.",
      "Trust is PAR: does the payment go through, and was the answer Paid, Answered, Right?",
      "The red bar: the Bazaar's #1 is left out, because it never gets paid.",
      "Answer in milliseconds, no AI model on this path.",
    ],
    notes: "Same question, asked to Plumb. Three merchants, each with a price, a trust score and the payments behind it. The merchant that never settles is left out." },
  { id: "mandate", kicker: "Control", title: "The mandate decides what Plumb may recommend", auto: true,
    cues: [
      "The agent has a mandate: a limit on what it may spend per purchase.",
      "Open mandate, 0.05: the top pick costs 0.004.",
      "Tight mandate, 0.002: a cheaper merchant comes first. It's a partial match, and the card says so.",
      "Plumb never recommends a merchant the mandate can't pay.",
    ],
    notes: "With an open mandate, the top pick costs four thousandths. Tighten the mandate, and a cheaper merchant comes first. Plumb never recommends a merchant the mandate can't pay." },
  { id: "ap4m", kicker: "Mastercard AP4M · testnet · recorded run, 25 Oct 05:25 UTC", title: "The agent pays Plumb, within its cap", auto: false,
    cues: [
      "Mastercard's AP4M on testnet: a full run from this morning, every hash clickable.",
      "One: identities. Our agent wallet, Plumb as the merchant with its payout wallet, both PSPs, and a channel funded with a cap of 0.005.",
      "Two: Plumb answers HTTP 402 with its payment requirements. The agent signs a voucher, it's redeemed on-chain, and the resource is released.",
      "The second voucher is cumulative, 0.004. A third would pass the cap, so the agent refuses: no voucher, nothing paid.",
      "Three: settlement. Payout and settlement transactions, and Mastercard's receipt ties the channel, the claim and the payout together.",
    ],
    notes: "This is a full run on Mastercard's agent payment rail. First, identities: our agent wallet, Plumb as the merchant with its payout wallet, and a channel funded with a cap of five thousandths. Second, Plumb answers with HTTP four oh two and its payment requirements; the agent signs a voucher, it is redeemed on chain, and the resource is released. The second voucher brings the total to four thousandths, so a third would break the cap, and the agent refuses it without signing. Third, settlement: a payout and a settlement transaction, and Mastercard's receipt links the channel, the claim and the payout." },
  { id: "personal", kicker: "Per agent · Quicknode", title: "Same question, two real accounts, two answers", auto: true,
    cues: [
      "Plumb ranks for THIS agent, not the average one.",
      "We read two real XRP Ledger accounts live, through Quicknode.",
      "Left: holds RLUSD. Right: can only pay in XRP.",
      "Same question, different first pick: each only sees merchants it can actually pay.",
    ],
    notes: "We read two real accounts live through Quicknode. One holds RLUSD, the other only XRP. Same question, different top pick, because each only sees merchants it can actually pay." },
  { id: "evidence", kicker: "Evidence", title: "We tested, found our own bug, fixed it", auto: false,
    cues: [
      "We tested with real money: 100 new questions, decided in advance, with answers checked by code.",
      "Plumb got 77 right, the Bazaar 72. Honestly, that's basically a tie.",
      "So we looked at every miss. 28 times out of 72, the right merchant never even reached our shortlist.",
      "The reason: our search matched by meaning only. Adding plain keyword matching finds all 72.",
      "We fixed it and bought the failed questions again: 10 of 14 are now answered well.",
    ],
    notes: "We tested with real money on a hundred new questions: seventy-seven against seventy-two, basically a tie. We found that our search missed the right merchant twenty-eight times out of seventy-two, fixed it, and bought those failures again: ten of fourteen now work." },
  { id: "sponsors", kicker: "Built on", title: "How each sponsor is wired in", auto: false,
    cues: [
      "Pay, Read, Think, Spend.",
      "PAY, the XRP Ledger: merchants are paid there in RLUSD and XRP, and those payments are our trust evidence.",
      "READ, Quicknode: we read the ledger through it: payment history, every test purchase by its transaction, each agent's account live.",
      "THINK, AWS: Bedrock's Claude decides which merchant fits a new question; AgentCore Memory keeps each customer's feedback.",
      "SPEND, Mastercard AP4M: how the agent pays Plumb, inside its limit, with receipts.",
    ],
    notes: "Pay, read, think, spend. The XRP Ledger is where merchants are paid. Quicknode reads it. AWS Bedrock judges fit, and AgentCore keeps customer feedback. Mastercard's AP4M is how the agent pays Plumb, inside its limit." },
  { id: "gaps", kicker: "Honest gaps", title: "What isn't solved yet, and what we do next", auto: false,
    cues: [
      "Six gaps, each with its next step.",
      "Accuracy is a tie so far. Next: re-run all 100 questions with the fix.",
      "The Bazaar was cheaper, because of our flat fee. Next: a percentage of the purchase.",
      "Trust data is thin, and our own purchases aren't in it yet. Next: feed them in.",
      "There are no real buyers yet; per-customer learning is shown with simulated ones.",
      "XRPL is under a tenth of the market. Next: other chains, Base first. And AP4M is testnet only.",
    ],
    notes: "Six gaps. Accuracy is a tie so far; the Bazaar was cheaper because of our flat fee; trust data is thin; there are no real buyers yet; XRPL is under a tenth of the market; and AP4M is testnet only. Each has a next step." },
  { id: "transfer", kicker: "Beyond XRPL", title: "The core travels. Three inputs change.", auto: false,
    cues: [
      "What carries over unchanged: the trust score, the ranking by cost per good answer, one merchant per company, and the mandate.",
      "What each new market must give us: who gets paid, proof the payment cleared, and whether the answer was usable.",
      "AP4M has all three, and no merchant directory or ranking yet. That's our slot.",
      "Other chains have the volume: 39 thousand of the 42 thousand listings. x402 on Base first.",
      "Tool registries and card checkout fit less well, and we say why.",
    ],
    notes: "The trust score, the ranking and the mandate carry over. Each new market must give us three things: who gets paid, proof the payment cleared, and whether the answer was usable. AP4M has all three and no ranking yet. Other chains have the volume." },
  { id: "close", kicker: "Plumb", title: "AP4M decides how an agent may pay. Plumb decides whom.", auto: false,
    cues: [
      "AP4M decides HOW an agent may pay.",
      "Plumb decides WHOM it should pay: within its limit, with proof from the ledger.",
      "Thank you.",
    ],
    notes: "AP4M decides how an agent may pay. Plumb decides whom it should pay, within its mandate, with evidence from the ledger. Thank you." },
]

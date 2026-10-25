// Every number here is in docs/EVIDENCE.md under the id shown next to it (and locked by tests/test_evidence_numbers.py).
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
  e4: { id: "E4", text: "46 payer accounts created within 4 minutes, each with 1,196+ payments" },
  l4: { id: "L4", text: "3,207 XRPL listings, but only 13 payout accounts" },
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

export type SlideMeta = { id: string; kicker: string; title: string; notes: string; auto: boolean }

export const SLIDES: SlideMeta[] = [
  { id: "title", kicker: "Agentic Finance · XRPL", title: "Whom should your agent pay?", auto: false,
    notes: "AI agents can now pay for things on their own. Ask one for a bitcoin funding rate, and it can buy the answer from a merchant on the XRP Ledger in a few seconds. The hard part is no longer paying. It is knowing whom to pay. Plumb answers that question, for each agent, with evidence from the ledger." },
  { id: "problem", kicker: "The problem", title: "The market's #1 has never delivered", auto: true,
    notes: "This is Coinbase's x402 Bazaar, live, searching for a bitcoin funding rate on XRPL. Its number one result is pay.edge-agents.ai. That merchant failed eighty-eight out of eighty-eight real purchases. It ranks first because the Bazaar counts activity, and failed purchases still count as activity. Its call counts run five to three hundred times the payments that actually settled." },
  { id: "router", kicker: "Plumb", title: "One call, three merchants with evidence", auto: true,
    notes: "Same question, asked to Plumb. It returns three merchants, one per operator, each with a price, a trust score and the on-ledger payments behind it. The merchant that never settles is excluded. Trust is the chance a payment settles, times the chance the answer is good once it does. There is no language model on this path, so it answers in milliseconds." },
  { id: "mandate", kicker: "Control", title: "The mandate decides what Plumb may recommend", auto: true,
    notes: "Now the agent brings its mandate: how much it may spend on one purchase. With an open mandate, Plumb's top pick for New York weather costs four thousandths of an RLUSD. Tighten the mandate to two thousandths, and the top pick changes to a cheaper merchant, a partial match, and the card says so. Plumb never recommends a merchant the mandate can't pay, and every answer says so." },
  { id: "ap4m", kicker: "Mastercard AP4M", title: "The agent pays Plumb, inside a capped channel", auto: false,
    notes: "Here is a full run on Mastercard's agent payment rail, recorded this morning. The agent opens a channel with a five thousandths cap. It pays Plumb two thousandths per shortlist with a signed voucher, and each shortlist respects the budget left in the channel. The third request would break the cap, so the agent refuses it. Then the channel settles and Mastercard issues a receipt. Every step has a receipt you can click." },
  { id: "personal", kicker: "Per agent · Quicknode", title: "Same question, two real accounts, two answers", auto: true,
    notes: "Plumb ranks for this agent, not the average one. We read two real mainnet accounts live through Quicknode. One holds RLUSD. The other can only pay in XRP. Same question, different top pick, because Plumb only recommends merchants each account can actually pay. The ledger payments behind the trust scores are read through Quicknode too." },
  { id: "trust", kicker: "Trust", title: "Trust comes from settled payments, not activity", auto: false,
    notes: "Trust is built only from what happened: purchases that settled and answers that were good. Each customer's feedback is remembered for that customer, and a review will count for everyone only with a validated payment to that merchant. Listing text is untrusted data, never instructions. And the score uses only checks every merchant faces equally." },
  { id: "sponsors", kicker: "Built on", title: "What each sponsor does in Plumb", auto: false,
    notes: "Each sponsor does real work here. The XRP Ledger is where merchants are paid, and its settled payments are our trust evidence. Quicknode serves the full ledger history and the live account reads. AWS Bedrock runs the Claude judge and the embeddings, and AgentCore Memory backs up each customer's feedback. Mastercard's AP4M is how the agent pays Plumb, inside its mandate." },
  { id: "evidence", kicker: "Evidence", title: "Real money, graded by code, and we found our own bug", auto: false,
    notes: "We test with real money on mainnet, with needs and grading frozen in advance. On a hundred new needs, Plumb got seventy-seven good answers and the Bazaar seventy-two: no real edge. So we traced every miss. Our search for new needs used embeddings only, and missed the right merchant on twenty-eight of seventy-two needs. We fixed it, then bought those failures again: Plumb now answers ten of the fourteen." },
  { id: "production", kicker: "Path to production", title: "From hackathon to rail", auto: false,
    notes: "What's next. First, more rails: AP4M merchants, and x402 on Base, where most of fizzl's merchants live. Second, pricing: a percentage of the merchant price instead of a flat fee, and later a success fee for answers that pass independent checks. The blockers are honest ones: AP4M is testnet only and pays only our own merchant, and the XRPL AI Hub has no public API yet." },
  { id: "close", kicker: "Plumb", title: "AP4M decides how an agent may pay. Plumb decides whom.", auto: false,
    notes: "AP4M decides how an agent may pay. Plumb decides whom it should pay, within its mandate, with evidence from the ledger. Thank you." },
]

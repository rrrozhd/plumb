import { useEffect, useRef, useState } from "react"
import { Play, RotateCcw, ShieldCheck, Zap } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Busy, Cite, Ext, Kicker, PickCard, Stat, Trail, useTask } from "@/components/deck"
import { api, short, type TrailEvent } from "@/lib/api"
import { DEMO, E, SLIDES } from "@/content"
import { cn } from "@/lib/utils"

export type SlideProps = { active: boolean; auto: boolean }

function Head({ i }: { i: number }) {
  return (
    <div className="mb-8 space-y-3">
      <Kicker>{SLIDES[i].kicker}</Kicker>
      <h1 className="max-w-5xl font-heading text-5xl font-semibold leading-[1.05] tracking-tight">{SLIDES[i].title}</h1>
    </div>
  )
}

const NeedLine = ({ need }: { need: string }) => (
  <div className="mb-5 inline-flex max-w-full items-center gap-2 rounded-full border bg-card/60 px-4 py-2 text-sm">
    <span className="text-muted-foreground">need</span><span className="truncate font-medium">“{need}”</span>
  </div>
)

export function Title() {
  return (
    <div className="flex flex-col justify-center">
      <Kicker>{SLIDES[0].kicker}</Kicker>
      <h1 className="mt-4 font-heading text-8xl font-semibold leading-[0.95] tracking-tight">
        Whom should<br />your agent <span className="text-brand">pay?</span>
      </h1>
      <p className="mt-8 max-w-3xl text-2xl leading-snug text-muted-foreground">
        <b className="text-foreground">Plumb</b> is the trust and routing layer between AI agents and paid APIs on the XRP Ledger:
        three merchants with evidence, inside the agent's mandate, in milliseconds.
      </p>
      <div className="mt-12 flex flex-wrap gap-2">
        {["XRPL x402 · mainnet", "Mastercard AP4M · testnet", "Quicknode", "AWS Bedrock"].map((t) => (
          <Badge key={t} variant="outline" className="h-8 px-3 text-sm">{t}</Badge>
        ))}
      </div>
    </div>
  )
}

export function Why() {
  return (
    <div>
      <Head i={1} />
      <div className="grid grid-cols-3 gap-5">
        <Stat value="42,241" label={E.e29.text} cite={E.e29.id} />
        <Stat value="44%" label={E.e3.text} cite={E.e3.id} tone="bad" />
        <Stat value="2 in 3" label="real XRPL x402 purchase attempts got no usable answer" cite={E.e2.id} tone="bad" />
      </div>
      <div className="mt-10 grid grid-cols-2 gap-6 text-2xl leading-snug">
        <div className="rounded-xl border bg-card/60 p-6"><div className="text-sm uppercase tracking-[0.18em] text-muted-foreground">solved</div>Payment rails decide <b>how</b> an agent may pay: limits, vouchers, receipts.</div>
        <div className="rounded-xl border border-brand/50 bg-card/60 p-6"><div className="text-sm uppercase tracking-[0.18em] text-brand">missing</div>Nothing decides <b>whom</b> it should pay. The agent finds out after trying, at machine speed.</div>
      </div>
    </div>
  )
}

export function Problem({ active, auto }: SlideProps) {
  const t = useTask(() => api.bazaar(DEMO.problemNeed), active, auto)
  return (
    <div>
      <Head i={2} />
      <NeedLine need={DEMO.problemNeed} />
      <div className="grid grid-cols-[1.6fr_1fr] gap-8">
        <div>
          <div className="mb-2 flex items-center justify-between text-sm text-muted-foreground">
            <span>Coinbase x402 Bazaar · live search · XRPL</span>
            <Button size="sm" variant="ghost" onClick={t.run}><RotateCcw />search</Button>
          </div>
          <Busy loading={t.loading} error={t.error} onRetry={t.run} label="Searching the Bazaar…" />
          {t.data && (
            <Table>
              <TableHeader><TableRow><TableHead>#</TableHead><TableHead>merchant</TableHead><TableHead className="text-right">Bazaar calls 30d</TableHead><TableHead className="text-right">real purchases settled</TableHead></TableRow></TableHeader>
              <TableBody>
                {t.data.map((r) => {
                  const dead = r.vet402 && r.vet402.settled === 0
                  return (
                    <TableRow key={r.url} className={cn(dead && "bg-bad/10")}>
                      <TableCell className="font-mono">{r.rank}</TableCell>
                      <TableCell className="max-w-[360px] truncate font-mono text-sm">{short(r.url)}</TableCell>
                      <TableCell className="text-right tabular-nums">{r.calls_30d ?? "—"}</TableCell>
                      <TableCell className={cn("text-right font-semibold tabular-nums", dead && "text-bad")}>{r.vet402 ? `${r.vet402.settled} of ${r.vet402.attempts}` : "no record"}</TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
        <div className="space-y-4">
          <Stat value="0 / 88" label={E.edge.text} cite={E.edge.id} tone="bad" />
          <Stat value="5–300×" label={E.e1.text} cite={E.e1.id} />
          <Stat value="32%" label={E.e2.text} cite={E.e2.id} />
        </div>
      </div>
    </div>
  )
}

export function Router({ active, auto }: SlideProps) {
  const t = useTask(() => api.recommend({ need: DEMO.problemNeed }), active, auto)
  const bz = useTask(() => api.bazaar(DEMO.problemNeed), active, auto)
  const left = bz.data?.[0] && t.data && !t.data.results.some((p) => p.url === bz.data![0].url) ? bz.data[0] : undefined
  return (
    <div>
      <Head i={3} />
      <NeedLine need={DEMO.problemNeed} />
      <Busy loading={t.loading} error={t.error} onRetry={t.run} label="Asking Plumb…" />
      {t.data && (
        <>
          <div className="grid grid-cols-3 gap-4">{t.data.results.map((p, i) => <PickCard key={p.url} pick={p} highlight={i === 0} />)}</div>
          {left && (
            <div className="mt-5 flex items-center gap-3 rounded-xl border border-bad/40 bg-bad/10 px-5 py-3 text-lg">
              <span className="font-semibold text-bad">Left out:</span>
              <span className="font-mono">{short(left.url)}</span>
              <span className="text-muted-foreground">the Bazaar's #1 · {left.vet402 ? `${left.vet402.settled} of ${left.vet402.attempts} purchases settled` : "never settles"}</span>
            </div>
          )}
          <div className="mt-6 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <Badge className="h-7 gap-1 bg-brand px-3 text-sm text-brand-foreground"><Zap className="size-3.5" />{t.data.timing_ms.total.toFixed(2)} ms</Badge>
            <span>trust = does the payment go through × was the answer good · one merchant per operator</span>
            <span>· excluded: <b className="text-foreground">{t.data.excluded.settle ?? 0} that never settle</b>, {t.data.excluded.dead ?? 0} dead, {t.data.excluded.fit ?? 0} off-topic</span>
            <Button size="sm" variant="ghost" onClick={t.run}><RotateCcw />ask again</Button>
          </div>
        </>
      )}
    </div>
  )
}

export function Mandate({ active, auto }: SlideProps) {
  const open = useTask(() => api.recommend({ need: DEMO.mandateNeed, max_price: DEMO.openMandate }), active, auto)
  const tight = useTask(() => api.recommend({ need: DEMO.mandateNeed, max_price: DEMO.tightMandate }), active, auto)
  const col = (label: string, limit: string, t: typeof open, accent?: boolean) => (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <ShieldCheck className={cn("size-5", accent ? "text-brand" : "text-muted-foreground")} />
        <span className="text-lg font-medium">{label}</span>
        <Badge variant="outline" className="font-mono">per purchase ≤ {limit} RLUSD</Badge>
      </div>
      <Busy loading={t.loading} error={t.error} onRetry={t.run} label="Ranking within the mandate…" />
      {t.data?.results.slice(0, 1).map((p) => <PickCard key={p.url} pick={{ ...p, within_mandate: `per-purchase ≤ ${limit}` }} highlight={accent} />)}
      {t.data && <div className="text-sm text-muted-foreground">{t.data.excluded.constraints ?? 0} merchants excluded by the mandate</div>}
    </div>
  )
  return (
    <div>
      <Head i={4} />
      <NeedLine need={DEMO.mandateNeed} />
      {open.data?.results[0] && tight.data?.results[0] && (
        <div className="mb-5 text-2xl">
          Top pick <span className="font-mono text-muted-foreground">{Number(open.data.results[0].price.amount_rlusd).toFixed(4)}</span>
          {" → "}<span className="font-mono font-semibold text-brand">{Number(tight.data.results[0].price.amount_rlusd).toFixed(4)}</span>
          <span className="text-muted-foreground"> RLUSD: a different merchant, never one the mandate can't pay</span>
        </div>
      )}
      <div className="grid grid-cols-2 gap-8">
        {col("Open mandate", DEMO.openMandate, open)}
        {col("Tight mandate", DEMO.tightMandate, tight, true)}
      </div>
    </div>
  )
}

export function Ap4m({ active }: SlideProps) {
  const [events, setEvents] = useState<TrailEvent[]>([])
  const [run, setRun] = useState<string | null>(null)
  const [live, setLive] = useState(false)
  const [error, setError] = useState<string>()
  const source = useRef<EventSource | null>(null)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" }) }, [events.length])
  useEffect(() => {
    if (active && !events.length && !live) api.trail("latest").then((t) => { setEvents(t.events); setRun(t.run) }).catch(() => {})
  }, [active, events.length, live])
  useEffect(() => () => source.current?.close(), [])
  const start = async () => {
    setError(undefined)
    try {
      const { run: id } = await api.runAgent({ per_purchase: DEMO.openMandate, cap: DEMO.agentCap, needs: DEMO.agentNeeds })
      setRun(id); setEvents([]); setLive(true)
      const es = new EventSource(`/api/agent/stream?run=${id}`)
      source.current = es
      es.onmessage = (m) => setEvents((x) => [...x, JSON.parse(m.data)])
      es.addEventListener("end", () => { setLive(false); es.close() })
      es.onerror = () => { setLive(false); es.close() }
    } catch (e) { setError((e as Error).message) }
  }
  return (
    <div>
      <Head i={5} />
      <div className="grid grid-cols-[1fr_2fr] gap-8">
        <div className="space-y-4">
          <Stat value={`${DEMO.agentCap} RLUSD`} label="channel cap: the agent's spending mandate" />
          <Stat value="0.002" label="RLUSD per shortlist, paid with a signed AP4M voucher" />
          <div className="flex gap-2">
            <Button size="lg" onClick={start} disabled={live}><Play />{live ? "running on testnet…" : "Run live on AP4M testnet"}</Button>
          </div>
          {error && <div className="text-sm text-bad">{error}</div>}
          <div className="text-sm text-muted-foreground">{run && <>{live ? "live run" : "last completed run"} <span className="font-mono">{run}</span> · </>}every row links to its receipt<Cite id={E.e18.id} /></div>
        </div>
        <div ref={box} className="max-h-[54vh] overflow-y-auto pr-1">
          <Trail events={events} live={live} />
          {!events.length && !live && <div className="text-muted-foreground">No run yet: press Run.</div>}
        </div>
      </div>
    </div>
  )
}

function AccountColumn({ address, active, auto }: SlideProps & { address: string }) {
  const acct = useTask(() => api.account(address), active, auto)
  const list = useTask(async () => api.recommend({ need: DEMO.personalNeed, assets: acct.data!.assets, principal: address }), active && Boolean(acct.data), auto)
  return (
    <div className="space-y-3">
      <div className="rounded-xl border bg-card/60 p-4">
        <div className="font-mono text-sm">{address}</div>
        <Busy loading={acct.loading} error={acct.error} onRetry={acct.run} label="Reading the ledger via Quicknode…" />
        {acct.data && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
            <Badge variant={acct.data.rlusd_trust_line ? "default" : "secondary"}>{acct.data.rlusd_trust_line ? `RLUSD trust line · ${Number(acct.data.rlusd_balance).toFixed(2)}` : "no RLUSD trust line"}</Badge>
            <Badge variant="outline">{acct.data.xrp} XRP</Badge>
            <span className="text-muted-foreground">ledger {acct.data.ledger_index} · {acct.data.ms} ms · {acct.data.source}</span>
          </div>
        )}
      </div>
      <Busy loading={list.loading} error={list.error} onRetry={list.run} label="Ranking for this account…" />
      {list.data?.results.slice(0, 1).map((p) => <PickCard key={p.url} pick={p} highlight />)}
    </div>
  )
}

export function Personal(props: SlideProps) {
  return (
    <div>
      <Head i={6} />
      <NeedLine need="Verify XRPL transaction 65A4…0795: was it validated and what amount did it deliver?" />
      <div className="grid grid-cols-2 gap-8">
        <AccountColumn address={DEMO.rlusdAccount} {...props} />
        <AccountColumn address={DEMO.xrpOnlyAccount} {...props} />
      </div>
    </div>
  )
}

export function Evidence() {
  const steps = [
    { step: "1 · We tested", head: "77 vs 72", sub: "100 new questions, bought with real money. Plumb 77 good answers, the Bazaar 72: basically a tie.", cite: "E26", good: false },
    { step: "2 · We found why", head: "28 of 72", sub: "times the right merchant never reached our shortlist. Our search matched by meaning only; adding keyword matching finds all 72.", cite: "E27", good: false },
    { step: "3 · We fixed it and bought again", head: "10 of 14", sub: "of the questions we got wrong are now answered well (before the fix: 0).", cite: "E28", good: true },
  ]
  return (
    <div>
      <Head i={7} />
      <div className="grid grid-cols-3 gap-4">
        {steps.map((x) => (
          <div key={x.step} className={cn("rounded-xl border bg-card/60 p-6", x.good && "border-good/50")}>
            <div className="mb-3 text-base font-semibold text-brand">{x.step}</div>
            <div className={cn("font-heading text-6xl font-semibold tabular-nums tracking-tight", x.good && "text-good")}>{x.head}</div>
            <div className="mt-4 text-lg leading-snug text-muted-foreground">{x.sub}<Cite id={x.cite} /></div>
          </div>
        ))}
      </div>
      <div className="mt-8 text-xl text-muted-foreground">
        Every answer bought on the XRP Ledger with real RLUSD. Questions and grading were fixed <b className="text-foreground">before</b> buying, and answers were checked by code against public sources.
      </div>
    </div>
  )
}

export function Sponsors() {
  const rows: [string, string, string, string, string][] = [
    ["Pay", "XRP Ledger", "Merchants are paid in RLUSD and XRP on mainnet; settled payments are the trust evidence; trust lines decide what an agent can pay", "E26: 158 mainnet payments", "few real buyers yet (E13)"],
    ["Read", "Quicknode", "Full-history XRPL RPC: the payment history behind trust, each test purchase checked by its own tx hash, each agent's account read live", "accounts slide, live", "trust also uses vet402's public log"],
    ["Think", "AWS", "Bedrock: Claude judges which merchant fits a new question and fills in the call; Titan embeddings plus keyword search find candidates. AgentCore Memory keeps each customer's feedback across restarts", "E26–E28 · MEM2", "AgentCore shown with a simulated customer"],
    ["Spend", "Mastercard AP4M", "The agent pays Plumb per shortlist with signed vouchers in a capped channel; the mandate limits what Plumb may recommend; settlement receipts", "E18", "testnet; channel limit reached (L27)"],
  ]
  return (
    <div>
      <Head i={8} />
      <div className="space-y-3">
        {rows.map(([verb, name, what, proof, caveat]) => (
          <div key={name} className="grid grid-cols-[110px_230px_1fr_250px] items-center gap-6 rounded-xl border bg-card/60 px-6 py-4">
            <div className="text-lg font-semibold uppercase tracking-[0.18em] text-brand">{verb}</div>
            <div className="font-heading text-2xl font-semibold">{name}</div>
            <div className="text-lg leading-snug text-muted-foreground">{what}</div>
            <div className="text-right text-sm"><div className="font-mono text-good">{proof}</div><div className="mt-1 text-muted-foreground">{caveat}</div></div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function Gaps() {
  const rows: [string, string, string, string][] = [
    ["Accuracy is a tie so far", "77 vs 72 of 100; the 10 of 14 measures recovery, not overall accuracy", "Re-run all 100 questions with the fix, pre-registered", "E26 · E28"],
    ["The Bazaar was cheaper per good answer", "0.0032 vs our 0.0065 RLUSD, mostly our flat 0.002 fee", "Charge a percentage of the purchase, not a flat fee", "E26"],
    ["Trust data is thin", "9% of candidate endpoints have any past purchase on record; our own test purchases aren't in the scores yet", "Feed every graded purchase back into trust", "E15"],
    ["No real buyers yet", "0 of 100 live XRPL x402 payments reached a Bazaar merchant; per-customer learning shown with simulated customers", "Agents pay through AP4M or the MCP tool; reviews bound to receipts", "E13"],
    ["XRPL is a small slice", "3,207 of 42,241 listings; much of it resells free public data", "x402 on Base next; free keyless sources at cost 0", "E29 · L26"],
    ["AP4M is a sandbox", "Testnet, pays only our own merchant, channel limit reached", "Production access when Mastercard opens it", "L19 · L27"],
  ]
  return (
    <div>
      <Head i={9} />
      <div className="grid grid-cols-[1fr_1.4fr_1.2fr] gap-x-6 text-sm uppercase tracking-[0.18em] text-muted-foreground"><div>gap</div><div>what we measured</div><div className="text-brand">next step</div></div>
      <div className="mt-2 space-y-2">
        {rows.map(([gap, what, step, cite]) => (
            <div key={gap} className="grid grid-cols-[1fr_1.4fr_1.2fr] items-center gap-x-6 rounded-xl border bg-card/60 px-5 py-3">
              <div className="text-xl font-semibold">{gap}</div>
              <div className="text-base leading-snug text-muted-foreground">{what}<Cite id={cite} /></div>
              <div className="text-base leading-snug">{step}</div>
            </div>
        ))}
      </div>
    </div>
  )
}

export function Transfer() {
  const rows: [string, string, string, string, string, string][] = [
    ["XRPL x402", "payTo account", "validated payment + InvoiceID", "code-checked purchases", "built", "good"],
    ["Mastercard AP4M", "attested merchant registry", "voucher and settlement events", "reviews bound to receipts", "high · no ranking yet", "good"],
    ["x402 on other chains (Base first)", "payTo address", "token transfer events", "same purchases", "high · 39k listings", "good"],
    ["MCP tool registries", "publisher", "none: tools are mostly free", "needs signed agent identity", "medium", "mid"],
    ["Card checkout", "card merchant", "card network", "delivery and returns", "low · no goods data", "bad"],
  ]
  return (
    <div>
      <Head i={10} />
      <div className="mb-6 rounded-xl border border-brand/50 bg-card/60 px-6 py-4 text-xl leading-snug">
        <span className="text-sm uppercase tracking-[0.18em] text-brand">travels unchanged · </span>
        trust from settlement × verified answers · rank by cost per good answer · one merchant per company · the mandate gate
      </div>
      <Table className="text-lg">
        <TableHeader><TableRow><TableHead>market</TableHead><TableHead>who gets paid</TableHead><TableHead>did it clear</TableHead><TableHead>was it usable</TableHead><TableHead>fit</TableHead></TableRow></TableHeader>
        <TableBody>
          {rows.map(([m, who, clear, usable, fit, tone]) => (
            <TableRow key={m}>
              <TableCell className="font-semibold">{m}</TableCell>
              <TableCell className="text-muted-foreground">{who}</TableCell>
              <TableCell className="text-muted-foreground">{clear}</TableCell>
              <TableCell className="text-muted-foreground">{usable}</TableCell>
              <TableCell className={cn("font-medium", tone === "good" && "text-good", tone === "bad" && "text-bad")}>{fit}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <div className="mt-6 text-lg text-muted-foreground">Order: AP4M → x402 on Base → tool registries, once agent identity can stand in for payment.<Cite id="E29" /></div>
    </div>
  )
}

export function Close() {
  return (
    <div className="flex flex-col justify-center">
      <Kicker>Plumb</Kicker>
      <h1 className="mt-4 max-w-5xl font-heading text-7xl font-semibold leading-[1.02] tracking-tight">
        AP4M decides <span className="text-muted-foreground">how</span> an agent may pay.<br />Plumb decides <span className="text-brand">whom</span>.
      </h1>
      <div className="mt-10 grid max-w-4xl grid-cols-3 gap-4">
        <Stat value="0 / 88" label="the Bazaar's #1, never chosen by Plumb" cite="E2" tone="bad" />
        <Stat value="10 / 14" label="failures recovered after fixing our own bug, bought again" cite="E28" tone="good" />
        <Stat value="0.13 ms" label="worst-5% ranking time, in-process bench" cite="E25" />
      </div>
      <div className="mt-10 text-muted-foreground">Evidence: <Ext href="https://github.com/rrrozhd/plumb/blob/mock-personalized/docs/EVIDENCE.md">docs/EVIDENCE.md</Ext></div>
    </div>
  )
}

export const SLIDE_COMPONENTS = [Title, Why, Problem, Router, Mandate, Ap4m, Personal, Evidence, Sponsors, Gaps, Transfer, Close]

import { useEffect, useRef, useState } from "react"
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts"
import { Play, RotateCcw, ShieldCheck, Zap } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Busy, Cite, Ext, Kicker, PickCard, Stat, Trail, useTask } from "@/components/deck"
import { api, short, type TrailEvent } from "@/lib/api"
import { DEMO, E, E21, POOLED, SLIDES } from "@/content"
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
        three merchants with evidence, inside the agent's mandate, in under a millisecond.
      </p>
      <div className="mt-12 flex flex-wrap gap-2">
        {["XRPL x402 · mainnet", "Mastercard AP4M · testnet", "Quicknode", "AWS Bedrock"].map((t) => (
          <Badge key={t} variant="outline" className="h-8 px-3 text-sm">{t}</Badge>
        ))}
      </div>
    </div>
  )
}

export function Problem({ active, auto }: SlideProps) {
  const t = useTask(() => api.bazaar(DEMO.problemNeed), active, auto)
  return (
    <div>
      <Head i={1} />
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
  return (
    <div>
      <Head i={2} />
      <NeedLine need={DEMO.problemNeed} />
      <Busy loading={t.loading} error={t.error} onRetry={t.run} label="Asking Plumb…" />
      {t.data && (
        <>
          <div className="grid grid-cols-3 gap-4">{t.data.results.map((p, i) => <PickCard key={p.url} pick={p} highlight={i === 0} />)}</div>
          <div className="mt-6 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <Badge className="h-7 gap-1 bg-brand px-3 text-sm text-brand-foreground"><Zap className="size-3.5" />{t.data.timing_ms.total.toFixed(2)} ms</Badge>
            <span>relevance: {t.data.relevance} · one merchant per operator</span>
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
      <Head i={3} />
      <NeedLine need={DEMO.mandateNeed} />
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
      <Head i={4} />
      <div className="grid grid-cols-[1fr_2fr] gap-8">
        <div className="space-y-4">
          <Stat value={`${DEMO.agentCap} RLUSD`} label="channel cap: the agent's spending mandate" />
          <Stat value="0.002" label="RLUSD per shortlist, paid with a signed AP4M voucher" />
          <div className="flex gap-2">
            <Button size="lg" onClick={start} disabled={live}><Play />{live ? "running on testnet…" : "Run live on AP4M testnet"}</Button>
          </div>
          {error && <div className="text-sm text-bad">{error}</div>}
          <div className="text-sm text-muted-foreground">{run && <>trail <span className="font-mono">{run}</span> · </>}every row links to its receipt<Cite id={E.e18.id} /></div>
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
      <Head i={5} />
      <NeedLine need="Verify XRPL transaction 65A4…0795: was it validated and what amount did it deliver?" />
      <div className="grid grid-cols-2 gap-8">
        <AccountColumn address={DEMO.rlusdAccount} {...props} />
        <AccountColumn address={DEMO.xrpOnlyAccount} {...props} />
      </div>
    </div>
  )
}

export function Trust() {
  const items = [
    ["P(settle)", "per merchant account and payment rail, from real payments on the ledger"],
    ["× P(good | settled)", "per endpoint, from audited purchases, with an operator prior and an exact lower bound"],
    ["÷ cost", "rank by cost per good answer: price and time over fit × settle × quality"],
  ]
  const rules = [
    "A review moves global trust only with a validated payment to that merchant, after the shortlist",
    "Listing and response text are untrusted data, never instructions",
    "The score uses only checks every merchant faces equally; graders and LLMs are for evaluation only",
    "No LLM on the request path: new needs are judged once, offline, then cached",
  ]
  return (
    <div>
      <Head i={6} />
      <div className="grid grid-cols-2 gap-10">
        <div className="space-y-3">
          {items.map(([k, v]) => (
            <div key={k} className="rounded-xl border bg-card/60 p-5">
              <div className="font-mono text-2xl font-semibold text-brand">{k}</div>
              <div className="mt-1 text-muted-foreground">{v}</div>
            </div>
          ))}
        </div>
        <ul className="space-y-4 text-xl leading-snug">
          {rules.map((r) => <li key={r} className="flex gap-3"><ShieldCheck className="mt-1 size-5 shrink-0 text-good" />{r}</li>)}
          <li className="pt-2 text-base text-muted-foreground">{E.l4.text}<Cite id={E.l4.id} /> · {E.e4.text}<Cite id={E.e4.id} /></li>
        </ul>
      </div>
    </div>
  )
}

export function Evidence() {
  const bars = [{ arm: "Bazaar #1", good: POOLED.bazaar }, { arm: "Plumb #1", good: POOLED.plumb }]
  return (
    <div>
      <Head i={7} />
      <div className="grid grid-cols-[1fr_1.2fr] gap-10">
        <div>
          <div className="mb-1 text-sm text-muted-foreground">good answers, 30 paid needs on mainnet<Cite id="E24" /></div>
          <div className="h-64">
            <ResponsiveContainer>
              <BarChart data={bars} layout="vertical" margin={{ left: 10, right: 50 }}>
                <XAxis type="number" hide domain={[0, 30]} />
                <YAxis type="category" dataKey="arm" width={130} tick={{ fill: "var(--muted-foreground)", fontSize: 20 }} axisLine={false} tickLine={false} />
                <Bar dataKey="good" radius={6} barSize={44}>
                  {bars.map((b) => <Cell key={b.arm} fill={b.arm.startsWith("Plumb") ? "var(--brand)" : "var(--muted-foreground)"} />)}
                  <LabelList dataKey="good" position="right" fill="var(--foreground)" fontSize={26} fontWeight={600} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Stat value={`${POOLED.won}–${POOLED.lost}`} label={`needs where only one arm was right (p = ${POOLED.p}: suggestive, not proof)`} cite="E24" tone="good" />
            <Stat value={`${POOLED.heldOut.plumb} vs ${POOLED.heldOut.bazaar}`} label="10 held-out needs, pre-registered" cite="E23" />
          </div>
        </div>
        <div className="space-y-4">
          <Table>
            <TableHeader><TableRow><TableHead>E21 · 20 frozen needs</TableHead><TableHead className="text-right">good</TableHead><TableHead className="text-right">RLUSD per good answer</TableHead></TableRow></TableHeader>
            <TableBody>
              {E21.map((r) => (
                <TableRow key={r.arm} className={cn(r.arm.startsWith("Plumb") && "bg-brand/10 font-semibold")}>
                  <TableCell>{r.arm}</TableCell><TableCell className="text-right tabular-nums">{r.good} / 20</TableCell><TableCell className="text-right font-mono">{r.cost}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <ul className="space-y-2 text-base text-muted-foreground">
            <li>Pooled cost per good answer, fee included: Plumb {POOLED.costPlumb} vs Bazaar {POOLED.costBazaar}; interval {POOLED.ratioCi}× includes parity<Cite id="E24" /></li>
            <li>fizzl costs <b className="text-foreground">{POOLED.fizzlCi}</b> more per good answer than Plumb<Cite id="E24" /></li>
            <li>Bought with real RLUSD; needs and grading frozen before buying; graded mostly by code against public sources</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

export function Production() {
  const cols: [string, string[]][] = [
    ["Live today", ["Router + trust on real XRPL x402 data", "AP4M: mandate, capped channel, receipts", "Mainnet evals with frozen rubric", "MCP tool for any agent"]],
    ["Next", ["Adapters: AP4M merchants, x402 on Base", "Success fee: paid only for good answers, proven on-ledger", "Real audits folding into trust", "Customer memory per agent"]],
    ["Blockers we name", ["AP4M is testnet and pays only our own merchant (L19)", "XRPL AI Hub has no public API yet", "Few real buyers today (L2): the trust prior carries most weight", "Accuracy edge not yet significant (E24)"]],
  ]
  return (
    <div>
      <Head i={8} />
      <div className="grid grid-cols-3 gap-6">
        {cols.map(([h, xs], i) => (
          <div key={h} className={cn("rounded-xl border bg-card/60 p-6", i === 0 && "border-brand/50")}>
            <div className="mb-4 text-lg font-semibold">{h}</div>
            <ul className="space-y-3 text-lg leading-snug text-muted-foreground">{xs.map((x) => <li key={x}>{x}</li>)}</ul>
          </div>
        ))}
      </div>
      <div className="mt-8 text-xl">Business: <b>0.002 RLUSD per shortlist</b> through AP4M today; the channel cap is the agent's spending mandate.</div>
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
        <Stat value="19 vs 14" label="good answers over 30 paid needs" cite="E24" tone="good" />
        <Stat value="0.13 ms" label="worst-5% per shortlist" cite="E25" />
      </div>
      <div className="mt-10 text-muted-foreground">Evidence: <Ext href="https://github.com/rrrozhd/plumb/blob/mock-personalized/docs/EVIDENCE.md">docs/EVIDENCE.md</Ext></div>
    </div>
  )
}

export const SLIDE_COMPONENTS = [Title, Problem, Router, Mandate, Ap4m, Personal, Trust, Evidence, Production, Close]

import { useCallback, useEffect, useRef, useState } from "react"
import { ArrowUpRight, CheckCircle2, CircleDashed, Loader2, ShieldCheck, XCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { short, xrplTx, type Pick, type TrailEvent } from "@/lib/api"
import { cn } from "@/lib/utils"

/** Run `fn` when `active` turns on (and `auto` allows it); expose the result, error and a manual rerun. */
export function useTask<T>(fn: () => Promise<T>, active: boolean, auto: boolean) {
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: false })
  const fnRef = useRef(fn)
  fnRef.current = fn
  const run = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: undefined }))
    try { setState({ data: await fnRef.current(), loading: false }) } catch (e) { setState({ error: (e as Error).message, loading: false }) }
  }, [])
  const fired = useRef(false)
  useEffect(() => {
    if (active && auto && !fired.current) { fired.current = true; void run() }
    if (!active) fired.current = false
  }, [active, auto, run])
  return { ...state, run }
}

export function Kicker({ children }: { children: React.ReactNode }) {
  return <div className="text-sm font-semibold uppercase tracking-[0.18em] text-brand">{children}</div>
}

export function Cite({ id }: { id: string }) {
  return <span className="ml-1.5 rounded border border-border px-1 py-px align-middle font-mono text-xs text-muted-foreground">{id}</span>
}

export function Stat({ value, label, cite, tone = "default" }: { value: string; label: string; cite?: string; tone?: "default" | "bad" | "good" }) {
  return (
    <div className="rounded-xl border bg-card/60 p-5">
      <div className={cn("font-heading text-5xl font-semibold tabular-nums tracking-tight",
        tone === "bad" && "text-bad", tone === "good" && "text-good")}>{value}</div>
      <div className="mt-2 text-sm leading-snug text-muted-foreground">{label}{cite && <Cite id={cite} />}</div>
    </div>
  )
}

export function Busy({ loading, error, onRetry, label }: { loading: boolean; error?: string; onRetry?: () => void; label: string }) {
  if (loading) return <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />{label}</div>
  if (error) return (
    <div className="flex items-center gap-3 text-sm text-bad">
      <XCircle className="size-4" />{error}
      {onRetry && <button className="underline underline-offset-4" onClick={onRetry}>retry</button>}
    </div>
  )
  return null
}

export function Ext({ href, children, className }: { href: string; children: React.ReactNode; className?: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className={cn("inline-flex items-center gap-0.5 underline-offset-4 hover:underline", className)}>
      {children}<ArrowUpRight className="size-3" />
    </a>
  )
}

const pct = (x: number) => `${Math.round(x * 100)}%`

export function PickCard({ pick, highlight }: { pick: Pick; highlight?: boolean }) {
  const ledger = pick.evidence.filter((e) => e.tx)
  return (
    <Card className={cn("gap-3 py-4 transition-colors", highlight && "ring-2 ring-brand/70")}>
      <CardHeader className="px-4">
        <div className="flex items-center justify-between gap-2">
          <span className="font-mono text-xs text-muted-foreground">#{pick.rank}</span>
          <div className="flex gap-1.5">
            <Badge variant={pick.match === "exact" ? "default" : "secondary"}>{pick.match}</Badge>
            <Badge variant="outline" className="font-mono">{pick.price.asset} {Number(pick.price.amount_rlusd).toFixed(4)}</Badge>
          </div>
        </div>
        <CardTitle className="truncate font-mono text-sm" title={pick.url}>{short(pick.url)}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 px-4 text-sm">
        <div className="grid grid-cols-3 gap-2 text-center">
          <Meter label="settles" value={pick.trust.p_settle} />
          <Meter label="good" value={pick.trust.q_mean} />
          <Meter label="good (low)" value={pick.trust.q_lo} />
        </div>
        {pick.within_mandate && (
          <div className="flex items-center gap-1.5 text-xs text-good"><ShieldCheck className="size-3.5" />within mandate: {pick.within_mandate}</div>
        )}
        <div className="text-xs text-muted-foreground">
          {ledger.length ? <>on-ledger payments: {ledger.slice(0, 2).map((e) => (
            <Ext key={e.tx} href={e.explorer ?? xrplTx(e.tx!)} className="mr-2 font-mono">{e.tx!.slice(0, 8)}…</Ext>))}</>
            : <>{pick.trust.scope} trust · {pick.trust.n_obs} direct observations</>}
        </div>
      </CardContent>
    </Card>
  )
}

function Meter({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-muted/60 px-2 py-1.5">
      <div className="font-heading text-lg font-semibold tabular-nums">{pct(value)}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  )
}

const EVM = "https://explorer.testnet.xrplevm.org/tx/"

/** The control trail: one row per step, each with the receipt that proves it. */
export function Trail({ events, live }: { events: TrailEvent[]; live?: boolean }) {
  const rows = events.filter((e) => ["signed_in", "channel_open", "paid", "shortlist", "refused_over_cap", "refused", "settled", "error"].includes(e.event))
  return (
    <ol className="space-y-1.5">
      {rows.map((e, i) => <TrailRow key={`${e.at}-${i}`} e={e} />)}
      {live && <li className="flex items-center gap-2 pl-1 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" />waiting for the next step…</li>}
    </ol>
  )
}

function TrailRow({ e }: { e: TrailEvent }) {
  const s = (k: string) => String(e[k] ?? "")
  const time = new Date(e.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
  const icon = e.event === "refused_over_cap" || e.event === "refused" || e.event === "error"
    ? <XCircle className="size-4 text-bad" /> : e.event === "settled" ? <CheckCircle2 className="size-4 text-good" /> : <CircleDashed className="size-4 text-brand" />
  let title = e.event, body: React.ReactNode = null
  if (e.event === "signed_in") { title = "Agent signed in to AP4M"; body = <span className="font-mono">{s("agent").slice(0, 10)}… · team {s("team")}</span> }
  if (e.event === "channel_open") { title = `Channel opened · cap ${s("cap_rlusd")} RLUSD`; body = <span className="font-mono">{s("channel_id").slice(0, 14)}… · per-purchase limit {s("per_purchase_rlusd")}</span> }
  if (e.event === "paid") { title = "Paid Plumb 0.002 RLUSD · voucher redeemed"; body = <Ext href={EVM + s("voucher_redeemed_tx")} className="font-mono">{s("voucher_redeemed_tx").slice(0, 18)}…</Ext> }
  if (e.event === "shortlist") {
    const m = e.mandate as { limit_rlusd?: string; budget_left_rlusd?: string } | undefined
    const res = (e.results as Pick[] | undefined) ?? []
    title = `Shortlist · ${res.length} merchant${res.length === 1 ? "" : "s"} within mandate`
    body = <span>limit <b className="font-mono">{m?.limit_rlusd}</b> (budget left {m?.budget_left_rlusd}) → <span className="font-mono">{res[0] ? `${short(res[0].url)} @ ${Number(res[0].price.amount_rlusd).toFixed(4)}` : "none"}</span>
      {res[0]?.evidence?.find((x) => x.tx) && <> · ledger proof <Ext href={xrplTx(res[0].evidence.find((x) => x.tx)!.tx!)} className="font-mono">{res[0].evidence.find((x) => x.tx)!.tx!.slice(0, 8)}…</Ext></>}</span>
  }
  if (e.event === "refused_over_cap") { title = "Refused: would exceed the channel cap"; body = <span>spent {s("spent_rlusd")} + fee {s("fee_rlusd")} &gt; cap {s("cap_rlusd")} · no voucher signed</span> }
  if (e.event === "refused") { title = "Refused"; body = s("reason").slice(0, 140) }
  if (e.event === "settled") {
    title = `Settled · ${s("claims_settled") || "?"} claims paid out to Plumb's merchant`
    const ex = (e.explorer ?? {}) as { payout?: string; settlement?: string }
    body = <span className="space-x-3">{ex.payout && <Ext href={ex.payout}>payout tx</Ext>}{ex.settlement && <Ext href={ex.settlement}>settlement tx</Ext>}{s("receipt_url") && <Ext href={s("receipt_url").startsWith("http") ? s("receipt_url") : `https://hackathon.ap4m.build${s("receipt_url")}`}>Mastercard receipt</Ext>}</span>
  }
  if (e.event === "error") { title = "Run failed"; body = s("reason") }
  return (
    <li className="flex gap-3 rounded-lg border bg-card/60 px-3 py-1.5">
      <div className="pt-0.5">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3"><span className="font-medium">{title}</span><span className="font-mono text-xs text-muted-foreground">{time}</span></div>
        <div className="mt-0.5 truncate text-sm text-muted-foreground">{body}</div>
      </div>
    </li>
  )
}

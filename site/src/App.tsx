import { useCallback, useEffect, useState } from "react"
import { ChevronLeft, ChevronRight, Maximize, NotebookText, Play, Power } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Kbd } from "@/components/ui/kbd"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Busy, PickCard, useTask } from "@/components/deck"
import { api, short, type Health } from "@/lib/api"
import { cn } from "@/lib/utils"
import { DEMO, SLIDES } from "@/content"
import { Ap4m, SLIDE_COMPONENTS } from "@/slides"
import { Logs } from "@/components/logs"

const fromHash = () => Math.min(Math.max(Number(location.hash.replace(/^#\/?/, "")) || 1, 1), SLIDES.length) - 1

export default function App() {
  const [i, setI] = useState(fromHash)
  const [mode, setMode] = useState<"present" | "control" | "logs">("present")
  const [logs, setLogs] = useState(false)
  const [auto, setAuto] = useState(true)
  const [notes, setNotes] = useState(false)
  const health = useHealth()
  const go = useCallback((n: number) => setI(Math.min(Math.max(n, 0), SLIDES.length - 1)), [])

  useEffect(() => { history.replaceState(null, "", `#/${i + 1}`) }, [i])
  useEffect(() => {
    const onHash = () => setI(fromHash())
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.metaKey || e.ctrlKey) return
      if (["ArrowRight", "PageDown", " "].includes(e.key)) { e.preventDefault(); go(i + 1) }
      else if (["ArrowLeft", "PageUp"].includes(e.key)) { e.preventDefault(); go(i - 1) }
      else if (e.key === "a") setAuto((x) => !x)
      else if (e.key === "n") setNotes((x) => !x)
      else if (e.key === "c") setMode((m) => (m === "present" ? "control" : "present"))
      else if (e.key === "l") setLogs((x) => !x)
      else if (e.key === "f") void (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen())
      else if (/^[0-9]$/.test(e.key)) go(e.key === "0" ? 9 : Number(e.key) - 1)
    }
    window.addEventListener("hashchange", onHash)
    window.addEventListener("keydown", onKey)
    return () => { window.removeEventListener("hashchange", onHash); window.removeEventListener("keydown", onKey) }
  }, [i, go])

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background text-foreground">
      <header className="flex h-14 shrink-0 items-center gap-4 border-b px-6">
        <div className="flex items-center gap-2 font-heading text-lg font-semibold tracking-tight">
          <span className="inline-block size-3 rotate-45 rounded-[3px] bg-brand" />Plumb
        </div>
        <Tabs value={mode} onValueChange={(v) => setMode(v as "present" | "control" | "logs")}>
          <TabsList><TabsTrigger value="present">Present</TabsTrigger><TabsTrigger value="control">Control room</TabsTrigger><TabsTrigger value="logs">Logs</TabsTrigger></TabsList>
        </Tabs>
        <div className="ml-auto flex items-center gap-4 text-sm">
          <HealthDots health={health.data} onStart={health.start} starting={health.starting} />
          <label className="flex items-center gap-2 text-muted-foreground"><Switch checked={auto} onCheckedChange={setAuto} />auto-run</label>
          <Button size="icon-sm" variant="ghost" onClick={() => setNotes((x) => !x)} title="Speaker notes (n)"><NotebookText /></Button>
          <Button size="icon-sm" variant="ghost" onClick={() => document.documentElement.requestFullscreen()} title="Fullscreen (f)"><Maximize /></Button>
        </div>
      </header>

      {mode === "present" ? (
        <>
          <main className="relative min-h-0 flex-1">
            {SLIDE_COMPONENTS.map((Slide, n) => (
              <section key={SLIDES[n].id} aria-hidden={n !== i}
                className={cn("absolute inset-0 overflow-y-auto px-16 py-12 transition-opacity duration-300",
                  n === i ? "opacity-100" : "pointer-events-none opacity-0")}>
                <div className="mx-auto flex min-h-full max-w-[1480px] flex-col justify-center"><Slide active={n === i} auto={auto && SLIDES[n].auto} /></div>
              </section>
            ))}
          </main>
          {logs && <div className="h-[34vh] shrink-0 border-t bg-card px-6 py-3"><Logs compact /></div>}
          {notes && <div className="max-h-40 shrink-0 overflow-y-auto border-t bg-card px-16 py-4 text-lg leading-relaxed text-muted-foreground">{SLIDES[i].notes}</div>}
          <footer className="flex h-14 shrink-0 items-center gap-4 border-t px-6">
            <Button size="icon-sm" variant="ghost" onClick={() => go(i - 1)} disabled={i === 0}><ChevronLeft /></Button>
            <div className="flex flex-1 gap-1.5">
              {SLIDES.map((s, n) => (
                <button key={s.id} onClick={() => go(n)} title={s.title}
                  className={cn("h-1.5 flex-1 rounded-full transition-colors", n <= i ? "bg-brand" : "bg-muted")} />
              ))}
            </div>
            <span className="w-48 truncate text-right text-sm text-muted-foreground">{i + 1} / {SLIDES.length} · {SLIDES[i].kicker}</span>
            <Button size="icon-sm" variant="ghost" onClick={() => go(i + 1)} disabled={i === SLIDES.length - 1}><ChevronRight /></Button>
            <div className="hidden gap-1 text-xs text-muted-foreground xl:flex"><Kbd>←</Kbd><Kbd>→</Kbd> slides <Kbd>a</Kbd> auto <Kbd>n</Kbd> notes <Kbd>l</Kbd> logs <Kbd>c</Kbd> control</div>
          </footer>
        </>
      ) : mode === "control" ? (
        <main className="min-h-0 flex-1 overflow-y-auto px-8 py-6"><ControlRoom /></main>
      ) : (
        <main className="min-h-0 flex-1 px-8 py-6"><Logs /></main>
      )}
    </div>
  )
}

function useHealth() {
  const [data, setData] = useState<Health>()
  const [starting, setStarting] = useState(false)
  useEffect(() => {
    const poll = () => api.health().then(setData).catch(() => setData(undefined))
    poll()
    const t = setInterval(poll, 5000)
    return () => clearInterval(t)
  }, [])
  const start = async () => { setStarting(true); try { setData(await api.startServices()) } finally { setStarting(false) } }
  return { data, start, starting }
}

function HealthDots({ health, onStart, starting }: { health?: Health; onStart: () => void; starting: boolean }) {
  const items: [string, boolean | undefined][] = [
    ["Plumb API", health?.plumb_api], ["AP4M merchant", health?.ap4m_merchant], ["AP4M gateway", health?.ap4m_gateway], ["Quicknode", health?.quicknode]]
  const down = !health || items.some(([, ok]) => !ok)
  return (
    <div className="flex items-center gap-3">
      {items.map(([name, ok]) => (
        <span key={name} className="flex items-center gap-1.5 text-muted-foreground" title={name}>
          <span className={cn("size-2 rounded-full", ok ? "bg-good" : "bg-bad")} />{name}
        </span>
      ))}
      {down && <Button size="sm" variant="outline" onClick={onStart} disabled={starting}><Power />{starting ? "starting…" : "start"}</Button>}
    </div>
  )
}

/** Everything live in one place: ask Plumb anything, read any account, search the Bazaar, run the AP4M agent. */
function ControlRoom() {
  const [need, setNeed] = useState(DEMO.problemNeed)
  const [maxPrice, setMaxPrice] = useState("")
  const [address, setAddress] = useState(DEMO.rlusdAccount)
  const plumb = useTask(async () => {
    const acct = address ? await api.account(address) : undefined
    return { acct, list: await api.recommend({ need, max_price: maxPrice || undefined, assets: acct?.assets, principal: address || undefined }) }
  }, false, false)
  const bazaar = useTask(() => api.bazaar(need), false, false)
  return (
    <div className="mx-auto grid max-w-[1500px] grid-cols-[1.4fr_1fr] gap-8">
      <div className="space-y-5">
        <div className="space-y-3 rounded-xl border bg-card/60 p-5">
          <div className="text-sm font-semibold uppercase tracking-[0.18em] text-brand">Ask</div>
          <Input value={need} onChange={(e) => setNeed(e.target.value)} placeholder="What does the agent need?" className="h-11 text-base" />
          <div className="flex gap-3">
            <Input value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} placeholder="mandate: max RLUSD per purchase" className="font-mono" />
            <Input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="agent's XRPL account (optional)" className="font-mono" />
          </div>
          <div className="flex gap-2">
            <Button onClick={plumb.run}><Play />Ask Plumb</Button>
            <Button variant="outline" onClick={bazaar.run}>Search the Bazaar</Button>
          </div>
        </div>
        <Busy loading={plumb.loading} error={plumb.error} onRetry={plumb.run} label="Ranking…" />
        {plumb.data && (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2 text-sm text-muted-foreground">
              {plumb.data.acct && <Badge variant="outline">{plumb.data.acct.rlusd_trust_line ? "RLUSD + XRP" : "XRP only"} · Quicknode {plumb.data.acct.ms} ms</Badge>}
              <Badge variant="outline">{plumb.data.list.relevance}</Badge>
              <Badge variant="outline">{plumb.data.list.timing_ms.total.toFixed(2)} ms</Badge>
              <span>excluded {Object.entries(plumb.data.list.excluded).map(([k, v]) => `${v} ${k}`).join(", ")}</span>
            </div>
            <div className="grid grid-cols-3 gap-3">{plumb.data.list.results.map((p, n) => <PickCard key={p.url} pick={p} highlight={n === 0} />)}</div>
            {!plumb.data.list.results.length && <div className="text-muted-foreground">No merchant fits this need inside the mandate.</div>}
          </div>
        )}
        <Busy loading={bazaar.loading} error={bazaar.error} onRetry={bazaar.run} label="Searching the Bazaar…" />
        {bazaar.data && (
          <div className="rounded-xl border bg-card/60 p-4 text-sm">
            <div className="mb-2 text-muted-foreground">Bazaar's own ranking</div>
            {bazaar.data.map((r) => (
              <div key={r.url} className="flex justify-between gap-4 py-1">
                <span className="truncate font-mono">{r.rank}. {short(r.url)}</span>
                <span className={cn("shrink-0 tabular-nums", r.vet402?.settled === 0 && "font-semibold text-bad")}>{r.vet402 ? `${r.vet402.settled}/${r.vet402.attempts} settled` : "no record"}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="rounded-xl border bg-card/40 p-5"><Ap4m active auto={false} /></div>
    </div>
  )
}

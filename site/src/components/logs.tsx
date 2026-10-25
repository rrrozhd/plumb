import { useEffect, useMemo, useRef, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

type Line = { source: string; at: string | null; event: string; data: string }

const TONE: Record<string, string> = {
  control: "bg-muted text-foreground", "plumb-api": "bg-brand/20 text-brand", "ap4m-gateway": "bg-sky-500/20 text-sky-300",
  agent: "bg-violet-500/20 text-violet-300", "eval E26": "bg-good/15 text-good", "eval E28": "bg-good/15 text-good",
}

/** Turn transaction hashes into explorer links: 0x… is AP4M on XRPL EVM testnet, 64 hex is XRPL mainnet. */
function Linked({ text }: { text: string }) {
  const parts = text.split(/(0x[0-9a-fA-F]{64}|\b[0-9A-F]{64}\b|https?:\/\/[^\s",]+)/g)
  return <>{parts.map((p, i) => {
    if (/^0x[0-9a-fA-F]{64}$/.test(p)) return <a key={i} className="text-sky-300 underline-offset-2 hover:underline" target="_blank" rel="noreferrer" href={`https://explorer.testnet.xrplevm.org/tx/${p}`}>{p.slice(0, 12)}…</a>
    if (/^[0-9A-F]{64}$/.test(p)) return <a key={i} className="text-good underline-offset-2 hover:underline" target="_blank" rel="noreferrer" href={`https://livenet.xrpl.org/transactions/${p}`}>{p.slice(0, 10)}…</a>
    if (/^https?:\/\//.test(p)) return <a key={i} className="underline-offset-2 hover:underline" target="_blank" rel="noreferrer" href={p}>{p.replace(/^https?:\/\//, "").slice(0, 60)}</a>
    return <span key={i}>{p}</span>
  })}</>
}

function summary(l: Line): string {
  try {
    const d = JSON.parse(l.data)
    const { at: _a, event: _e, run: _r, ...rest } = d
    return Object.entries(rest).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join("  ")
  } catch { return l.data }
}

/** Every demo-relevant log in one stream: control server, Plumb API, AP4M gateway, agent trails, eval purchases. */
export function Logs({ compact }: { compact?: boolean }) {
  const [lines, setLines] = useState<Line[]>([])
  const [off, setOff] = useState<Set<string>>(new Set(compact ? ["eval E26"] : []))
  const [q, setQ] = useState("")
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    let alive = true
    const poll = () => fetch("/api/logs").then((r) => r.json()).then((d) => alive && setLines(d)).catch(() => {})
    poll()
    const t = setInterval(poll, 2000)
    return () => { alive = false; clearInterval(t) }
  }, [])
  const sources = useMemo(() => [...new Set(lines.map((l) => l.source))], [lines])
  const shown = lines.filter((l) => !off.has(l.source) && (!q || (l.event + l.data).toLowerCase().includes(q.toLowerCase())))
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight }) }, [shown.length])
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {sources.map((s) => (
          <button key={s} onClick={() => setOff((o) => { const n = new Set(o); if (n.has(s)) n.delete(s); else n.add(s); return n })}
            className={cn("rounded-md px-2 py-0.5 text-xs font-medium transition-opacity", TONE[s] ?? "bg-muted", off.has(s) && "opacity-30")}>
            {s} · {lines.filter((l) => l.source === s).length}
          </button>
        ))}
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="filter: need, tx, merchant…" className="ml-auto h-7 w-64 text-xs" />
      </div>
      <div ref={box} className="min-h-0 flex-1 overflow-y-auto rounded-lg border bg-black/30 p-2 font-mono text-xs leading-relaxed">
        {shown.map((l, i) => (
          <div key={i} className="flex gap-2 border-b border-border/40 py-0.5">
            <span className="w-20 shrink-0 text-muted-foreground">{l.at ? new Date(l.at).toLocaleTimeString([], { hour12: false }) : "—"}</span>
            <Badge className={cn("h-5 shrink-0 rounded px-1.5 text-[0.7rem]", TONE[l.source])}>{l.source}</Badge>
            <span className="shrink-0 font-semibold">{l.event}</span>
            <span className="min-w-0 break-all text-muted-foreground"><Linked text={summary(l)} /></span>
          </div>
        ))}
        {!shown.length && <div className="p-4 text-muted-foreground">No log lines yet.</div>}
      </div>
    </div>
  )
}

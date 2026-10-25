import { useEffect, useRef, useState } from "react"
import { ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import { SLIDES } from "@/content"

/** The speaker's window: big read-aloud cues for the current slide, the next slide, and a timer. Synced with the deck. */
export function Presenter() {
  const [i, setI] = useState(0)
  const [t0] = useState(() => Date.now())
  const [now, setNow] = useState(Date.now())
  const ch = useRef<BroadcastChannel | null>(null)
  useEffect(() => {
    const c = new BroadcastChannel("plumb-deck")
    ch.current = c
    c.onmessage = (m) => { if (typeof m.data?.i === "number") setI(m.data.i) }
    c.postMessage({ hello: true })
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => { c.close(); clearInterval(t) }
  }, [])
  const go = (n: number) => ch.current?.postMessage({ go: Math.min(Math.max(n, 0), SLIDES.length - 1) })
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (["ArrowRight", "PageDown", " "].includes(e.key)) { e.preventDefault(); go(i + 1) }
      else if (["ArrowLeft", "PageUp"].includes(e.key)) { e.preventDefault(); go(i - 1) }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [i])
  const s = SLIDES[i], next = SLIDES[i + 1]
  const secs = Math.floor((now - t0) / 1000)
  return (
    <div className="flex h-screen flex-col bg-background p-8 text-foreground">
      <div className="flex items-center gap-4 text-lg text-muted-foreground">
        <span className="font-mono text-2xl text-foreground">{i + 1} / {SLIDES.length}</span>
        <span className="text-brand">{s.kicker}</span>
        <span className="ml-auto font-mono text-2xl text-foreground">{Math.floor(secs / 60)}:{String(secs % 60).padStart(2, "0")}</span>
        <Button variant="outline" onClick={() => go(i - 1)}><ChevronLeft />back</Button>
        <Button onClick={() => go(i + 1)}>next<ChevronRight /></Button>
      </div>
      <h1 className="mt-6 font-heading text-4xl font-semibold leading-tight">{s.title}</h1>
      <ol className="mt-8 flex-1 space-y-5 overflow-y-auto">
        {s.cues.map((c, n) => (
          <li key={n} className="flex gap-4 text-[2.1rem] leading-snug">
            <span className="mt-1 font-mono text-xl text-brand">{n + 1}</span><span>{c}</span>
          </li>
        ))}
      </ol>
      {next && <div className="mt-4 border-t pt-4 text-xl text-muted-foreground">next → <b className="text-foreground">{next.title}</b> · {next.cues[0]}</div>}
    </div>
  )
}

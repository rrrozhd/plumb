// The deck's only data source: the local control server (site/server.mjs) behind Vite's /api proxy.
export type Health = { plumb_api: boolean; ap4m_merchant: boolean; ap4m_gateway: boolean; quicknode: boolean; agent_running: boolean }

export type BazaarRow = {
  rank: number; url: string; host: string; service: string; pay_to?: string; asset: string; amount?: string
  calls_30d: number | null; vet402: { attempts: number; settled: number } | null
}

export type Evidence = { source: string; tx?: string; at?: string; explorer?: string }
export type Pick = {
  rank: number; url: string; method: string; operator: string; match: string; p_fit: number
  price: { asset: string; amount_rlusd: string }
  call: { method: string; url: string; args: Record<string, unknown> }
  trust: { scope: string; p_settle: number; q_mean: number; q_lo: number; n_obs: number; n_personal: number }
  cost_per_good_rlusd: string; why: string; evidence: Evidence[]; within_mandate?: string
}
export type Shortlist = {
  shortlist_id: string; need_template: string; relevance: string; results: Pick[]
  excluded: Record<string, number>; timing_ms: { candidates: number; total: number }
}
export type Account = { address: string; ledger_index: number; ms: number; source: string; xrp: string
  rlusd_trust_line: boolean; rlusd_balance: string | null; assets: string[] }
export type TrailEvent = { at: string; run: string; event: string; [k: string]: unknown }

async function call<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api/${path}`, body === undefined ? undefined
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  const data = await r.json()
  if (!r.ok) throw new Error(data.error ?? `HTTP ${r.status}`)
  return data as T
}

export const api = {
  health: () => call<Health>("health"),
  startServices: () => call<Health>("services/start", {}),
  bazaar: (need: string) => call<BazaarRow[]>("bazaar", { need }),
  recommend: (b: { need: string; max_price?: string; assets?: string[]; principal?: string; k?: number }) => call<Shortlist>("recommend", b),
  account: (address: string) => call<Account>("ledger/account", { address }),
  runAgent: (b: { per_purchase: string; cap: string; needs: string[] }) => call<{ run: string }>("agent/run", b),
  trail: (run = "latest") => call<{ run: string | null; events: TrailEvent[] }>(`trail?run=${encodeURIComponent(run)}`),
}

export const short = (url: string) => url.replace(/^https?:\/\//, "")
export const xrplTx = (tx: string) => `https://livenet.xrpl.org/transactions/${tx}`

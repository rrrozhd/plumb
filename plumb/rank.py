"""The request path (RECOMMENDER §2): template -> candidates -> gates -> recommender -> cost key -> operator slots.

No LLM. The only possible network call is one cached Titan embedding for a need template never seen before.
"""
import json
import copy
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal

import numpy as np

from plumb import db, relevance
from plumb.models import Profile
from plumb.recommender import HybridRecommender, Principal


@dataclass
class Ranker:
    rec: HybridRecommender
    fit: dict                      # template -> {need_id, need, labels: {eid: {label, p_fit, reason}}}
    vectors: relevance.Vectors
    lexical: relevance.Lexical
    embed: Callable[[str], list[float]] | None = None  # used only on a template cache miss
    dead: set = field(default_factory=set)   # endpoints that failed the offline liveness preflight
    calibration: relevance.Calibration | None = None  # new-need p_fit, learned from the judge's labels
    judge: Callable[[str, list[dict]], dict] | None = None  # cold path: judge a never-seen need once, then cache it
    cold_cache: object = None  # Path where cold-path labels persist (data/fit.json stays frozen)
    log: list = field(default_factory=list)
    memory_conn: sqlite3.Connection | None = None
    _memory_base: dict[str, Principal] = field(default_factory=dict)

    @db.serialized
    def bind_memory(self, conn: sqlite3.Connection) -> None:
        """Keep snapshot/simulated history separate so reloading durable reports cannot add them twice."""
        if self.memory_conn is None:
            self._memory_base = copy.deepcopy(self.rec.principals)
        self.memory_conn = conn
        for row in conn.execute("SELECT addr FROM principal"):
            self.refresh_principal(row["addr"])

    @db.serialized
    def refresh_principal(self, addr: str) -> None:
        from plumb import memory
        if self.memory_conn is not None:
            p = memory.load_principal(self.memory_conn, addr, self._memory_base.get(addr))
            if p is not None:
                # Retired endpoints remain in durable history, not today's scoring view.
                p.outcomes = {e: counts for e, counts in p.outcomes.items() if e in self.rec.endpoints}
                self.rec.principals[addr] = p

    def candidates(self, t: str, need_text: str = "") -> tuple[dict[str, float], str]:
        cfg = self.rec.cfg["rank"]
        judged = self.fit.get(t)
        if judged:
            return {e: x["p_fit"] for e, x in judged["labels"].items()}, ("judge_cached" if judged.get("cold") else "judge")
        vec = self.vectors.needs.get(t)
        if vec is None:
            if self.embed is None:
                return {}, "lexical"
            vec = self.vectors.needs[t] = self.embed(t)
        q = relevance.tokens(t)
        top = self.vectors.top(np.array(vec), cfg["embed_top"])
        top.sort(key=lambda es: -self.lexical.bm25(q, es[0]))
        if self.judge is not None:
            return self._cold(t, need_text, [e for e, _ in top])
        if self.calibration is None:
            return {e: self.lexical.coverage(q, e) for e, _ in top}, "lexical"
        return {e: self.calibration.p(sim, self.lexical.coverage(q, e)) for e, sim in top}, "lexical"

    def _cold(self, t: str, need: str, cands: list[str]) -> tuple[dict[str, float], str]:
        """Judge a never-seen need once (one call per operator, in parallel), cache it; repeats take the judged path."""
        from concurrent.futures import ThreadPoolExecutor
        groups: dict[str, list[dict]] = {}
        for e in cands:
            ep = self.rec.endpoints[e]
            groups.setdefault(ep.payto, []).append({"id": e, "service": ep.service_name, "url": ep.url,
                                                    "tags": ", ".join(ep.tags), "input": ep.input_example, "description": ep.description})
        labels: dict = {}
        assert self.judge is not None
        with ThreadPoolExecutor(8) as pool:
            for part in pool.map(lambda g: self.judge(need, g), groups.values()):  # type: ignore[misc]
                labels.update(part)
        self.fit[t] = {"need_id": None, "need": need, "labels": labels, "cold": True}
        if self.cold_cache is not None:
            cached = {k: v for k, v in self.fit.items() if v.get("cold")}
            self.cold_cache.write_text(json.dumps(cached, indent=1))  # type: ignore[attr-defined]
        return {e: x["p_fit"] for e, x in labels.items()}, "judge_cold"


    @db.serialized
    def shortlist(self, need: str, k: int | None = None, principal: str | None = None, constraints: dict | None = None) -> dict:
        t0 = time.perf_counter()
        cfg = self.rec.cfg["rank"]
        k = max(1, min(k or cfg["k_default"], cfg["k_max"]))
        if principal:
            self.refresh_principal(principal)
        p: Principal | None = self.rec.principals.get(principal) if principal else None
        prof = _merge(p.profile if p else Profile(), constraints or {})
        t = relevance.template(need)
        cands, how = self.candidates(t, need)
        t_cand = time.perf_counter()

        fit_min = float(cfg["fit_min"])
        excluded = {"constraints": 0, "settle": 0, "fit": 0, "dead": 0}
        keep: dict[str, float] = {}
        prices: dict[str, tuple[Decimal, str]] = {}
        for e, f in cands.items():
            ep, tr = self.rec.endpoints[e], self.rec.trust[e]
            price = self.rec.price_rlusd(ep, prof)
            if f < fit_min:
                excluded["fit"] += 1
            elif e in self.dead:
                excluded["dead"] += 1
            elif price is None or (prof.max_price_rlusd is not None and price[0] > prof.max_price_rlusd) \
                    or (prof.require_output_schema and not ep.has_output_schema):
                excluded["constraints"] += 1
            elif not tr.settle_ok:
                excluded["settle"] += 1
            else:
                keep[e], prices[e] = f, price

        p_good = self.rec.score(p, keep)
        tv = Decimal(str((constraints or {}).get("time_value_rlusd_per_s", cfg["default_time_value_rlusd_per_s"])))
        labels = (self.fit.get(t) or {}).get("labels", {})
        tier = {"exact": 0, "partial": 1}  # exact first: a near-miss is never ranked above a real match
        rows = []
        for e, pg in p_good.items():
            tr, ep = self.rec.trust[e], self.rec.endpoints[e]
            secs = Decimal((tr.latency_ms or 5000) / 1000)  # shortcut: 5 s when no good-attempt latency is known
            cost = (Decimal(str(tr.p_settle)) * prices[e][0] + tv * secs) / Decimal(str(max(pg, 1e-9)))
            rows.append((tier.get((labels.get(e) or {}).get("label"), 0), cost, e))
        rows.sort()
        rows = [(cost, e) for _, cost, e in rows]

        picked, ops = [], set()
        for cost, e in rows:  # one result per operator first, then fill if fewer operators qualify
            if self.rec.endpoints[e].payto not in ops:
                picked.append((cost, e))
                ops.add(self.rec.endpoints[e].payto)
            if len(picked) == k:
                break
        for cost, e in rows:
            if len(picked) >= k:
                break
            if (cost, e) not in picked:
                picked.append((cost, e))
        picked.sort(key=lambda x: rows.index(x))  # diversity picks the set; exact-first still orders it

        judged_need = (self.fit.get(t) or {}).get("need", need)
        results = [self._result(i + 1, e, cost, cands[e], how, p, prices[e], labels.get(e), need, judged_need)
                   for i, (cost, e) in enumerate(picked)]
        done = time.perf_counter()
        out = {"shortlist_id": str(uuid.uuid4()), "need_template": t, "relevance": how, "principal": principal,
               "personalized": p is not None, "results": results, "excluded": excluded,
               "timing_ms": {"candidates": round((t_cand - t0) * 1000, 2), "total": round((done - t0) * 1000, 2)}}
        self.log.append(json.dumps({"need_template": t, "n": len(results), "ms": out["timing_ms"]["total"]}))
        return out

    def _result(self, rank, e, cost, p_fit, how, p, price, judged=None, need="", judged_need="") -> dict:
        ep, tr = self.rec.endpoints[e], self.rec.trust[e]
        q_mean, q_lo, n_personal = self.rec.personal_q(p, e)
        return {
            "rank": rank, "endpoint_id": e, "url": ep.url, "method": ep.method, "operator": ep.payto,
            "price": {"asset": price[1], "amount_rlusd": str(price[0].quantize(Decimal("0.000001")))},
            "p_fit": round(p_fit, 3), "relevance": how, "match": (judged or {}).get("label", "lexical"),
            "call": {"method": ep.method, "url": ep.url, "args": relevance.rebind((judged or {}).get("args", {}), judged_need, need)},
            "trust": {"scope": "principal" if n_personal else "global", "p_settle": round(tr.p_settle, 3),
                      "q_mean": round(q_mean, 3), "q_lo": round(q_lo, 3), "n_obs": tr.n_obs, "n_personal": n_personal},
            "cost_per_good_rlusd": str(cost.quantize(Decimal("0.000001"))),
            "why": f"{(judged or {}).get('label', how)} fit; settles {tr.p_settle:.0%}; good {q_mean:.0%} "
                   f"({tr.n_obs} direct obs); {price[1]} {price[0]:.4f}",
            "evidence": self.rec.evidence.get(e, [])[:3]
                        + [{"source": "ledger", "tx": x["tx_hash"], "at": x["close_time"]} for x in self.rec.payments.get(ep.payto, [])[:2]],
            "listing": {"untrusted": True, "service": ep.service_name[:80], "description": ep.description[:300]},
        }


def _merge(prof: Profile, c: dict) -> Profile:
    upd = {}
    if "max_price" in c:
        upd["max_price_rlusd"] = Decimal(str(c["max_price"]))
    if "assets" in c:
        upd["assets"] = tuple(c["assets"])
    if "require_output_schema" in c:
        upd["require_output_schema"] = bool(c["require_output_schema"])
    return replace(prof, **upd)


def load(cfg: dict, root, embed=None, with_principals: bool = True, judge=None, conn: sqlite3.Connection | None = None) -> Ranker:
    """Fit the recommender from data/: real ledger principals and simulated personas (outcomes labelled simulated)."""
    from plumb import config, principals as P, recommender
    fit_path = config.path(cfg, "fit")
    fit = json.loads(fit_path.read_text()) if fit_path.exists() else {}
    cold_path = config.path(cfg, "fit_cold")
    if cold_path.exists():
        fit.update({k: v for k, v in json.loads(cold_path.read_text()).items() if k not in fit})
    ps = {}
    if with_principals:
        personas = P.load_personas(config.path(cfg, "personas"))
        ps = {**P.load_ledger_principals(root / "principals.json"), **personas}
        P.simulate(recommender.fit(cfg, root, ps), fit, personas, cfg["demo"]["simulated_purchases_per_persona"], cfg["demo"]["seed"])
    rec = recommender.fit(cfg, root, ps)  # second fit folds simulated outcomes into the co-occurrence signal
    docs = {i: relevance.doc_text(e, cfg["judge"]["max_listing_chars"]) for i, e in rec.endpoints.items()}
    live_path = root / "liveness.json"
    dead = {e for e, v in json.loads(live_path.read_text())["endpoints"].items() if not v["alive"]} if live_path.exists() else set()
    vectors, lexical = relevance.Vectors.load(root), relevance.Lexical(docs)
    X, y, _ = relevance.Calibration.features(fit, vectors, lexical)
    cal = relevance.Calibration.fit(X, y) if len(set(y.tolist())) == 2 else None
    rk = Ranker(rec, fit, vectors, lexical, embed, dead, cal, judge, cold_path)
    if conn is not None:
        rk.bind_memory(conn)
    return rk

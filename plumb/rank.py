"""The request path (RECOMMENDER §2): template -> candidates -> gates -> recommender -> cost key -> operator slots.

No LLM. The only possible network call is one cached Titan embedding for a need template never seen before.
"""
import json
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal

import numpy as np

from plumb import relevance
from plumb.models import Profile
from plumb.recommender import HybridRecommender, Principal


@dataclass
class Ranker:
    rec: HybridRecommender
    fit: dict                      # template -> {need_id, need, labels: {eid: {label, p_fit, reason}}}
    vectors: relevance.Vectors
    lexical: relevance.Lexical
    embed: Callable[[str], list[float]] | None = None  # used only on a template cache miss
    log: list = field(default_factory=list)

    def candidates(self, t: str) -> tuple[dict[str, float], str]:
        cfg = self.rec.cfg["rank"]
        judged = self.fit.get(t)
        if judged:
            return {e: x["p_fit"] for e, x in judged["labels"].items()}, "judge"
        vec = self.vectors.needs.get(t)
        if vec is None:
            if self.embed is None:
                return {}, "lexical"
            vec = self.vectors.needs[t] = self.embed(t)
        q = relevance.tokens(t)
        top = [e for e, _ in self.vectors.top(np.array(vec), cfg["embed_top"])]
        top.sort(key=lambda e: -self.lexical.bm25(q, e))
        return {e: self.lexical.coverage(q, e) for e in top}, "lexical"

    def shortlist(self, need: str, k: int | None = None, principal: str | None = None, constraints: dict | None = None) -> dict:
        t0 = time.perf_counter()
        cfg = self.rec.cfg["rank"]
        k = max(1, min(k or cfg["k_default"], cfg["k_max"]))
        p: Principal | None = self.rec.principals.get(principal) if principal else None
        prof = _merge(p.profile if p else Profile(), constraints or {})
        t = relevance.template(need)
        cands, how = self.candidates(t)
        t_cand = time.perf_counter()

        fit_min = float(cfg["fit_min"])
        excluded = {"constraints": 0, "settle": 0, "fit": 0}
        keep: dict[str, float] = {}
        prices: dict[str, tuple[Decimal, str]] = {}
        for e, f in cands.items():
            ep, tr = self.rec.endpoints[e], self.rec.trust[e]
            price = self.rec.price_rlusd(ep, prof)
            if f < fit_min:
                excluded["fit"] += 1
            elif price is None or (prof.max_price_rlusd is not None and price[0] > prof.max_price_rlusd) \
                    or (prof.require_output_schema and not ep.has_output_schema):
                excluded["constraints"] += 1
            elif not tr.settle_ok:
                excluded["settle"] += 1
            else:
                keep[e], prices[e] = f, price

        p_good = self.rec.score(p, keep)
        tv = Decimal(str((constraints or {}).get("time_value_rlusd_per_s", cfg["default_time_value_rlusd_per_s"])))
        rows = []
        for e, pg in p_good.items():
            tr, ep = self.rec.trust[e], self.rec.endpoints[e]
            secs = Decimal((tr.latency_ms or 5000) / 1000)  # shortcut: 5 s when no good-attempt latency is known
            cost = (Decimal(str(tr.p_settle)) * prices[e][0] + tv * secs) / Decimal(str(max(pg, 1e-9)))
            rows.append((cost, e))
        rows.sort()

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

        results = [self._result(i + 1, e, cost, cands[e], how, p, prices[e]) for i, (cost, e) in enumerate(picked)]
        done = time.perf_counter()
        out = {"shortlist_id": str(uuid.uuid4()), "need_template": t, "relevance": how, "principal": principal,
               "personalized": p is not None, "results": results, "excluded": excluded,
               "timing_ms": {"candidates": round((t_cand - t0) * 1000, 2), "total": round((done - t0) * 1000, 2)}}
        self.log.append(json.dumps({"need_template": t, "n": len(results), "ms": out["timing_ms"]["total"]}))
        return out

    def _result(self, rank, e, cost, p_fit, how, p, price) -> dict:
        ep, tr = self.rec.endpoints[e], self.rec.trust[e]
        q_mean, q_lo, n_personal = self.rec.personal_q(p, e)
        judged = next((x["labels"].get(e) for x in self.fit.values() if e in x["labels"]), None)
        return {
            "rank": rank, "endpoint_id": e, "url": ep.url, "method": ep.method, "operator": ep.payto,
            "price": {"asset": price[1], "amount_rlusd": str(price[0].quantize(Decimal("0.000001")))},
            "p_fit": round(p_fit, 3), "relevance": how,
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


def load(cfg: dict, root, embed=None, with_principals: bool = True) -> Ranker:
    """Fit the recommender from data/: real ledger principals and simulated personas (outcomes labelled simulated)."""
    from plumb import config, principals as P, recommender
    fit_path = root / "fit.json"
    fit = json.loads(fit_path.read_text()) if fit_path.exists() else {}
    ps = {}
    if with_principals:
        personas = P.load_personas(config.path(cfg, "personas"))
        ps = {**P.load_ledger_principals(root / "principals.json"), **personas}
        P.simulate(recommender.fit(cfg, root, ps), fit, personas, cfg["demo"]["simulated_purchases_per_persona"], cfg["demo"]["seed"])
    rec = recommender.fit(cfg, root, ps)  # second fit folds simulated outcomes into the co-occurrence signal
    docs = {i: relevance.doc_text(e, cfg["judge"]["max_listing_chars"]) for i, e in rec.endpoints.items()}
    return Ranker(rec, fit, relevance.Vectors.load(root), relevance.Lexical(docs), embed)

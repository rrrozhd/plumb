"""The pre-registered E26 analysis (eval/e26_prereg.md §Analysis), shared by the report and the evidence-lock tests."""
import random
from collections import defaultdict
from decimal import Decimal
from math import comb

FEE = Decimal("0.002")


def sign_test(won: int, lost: int) -> float:
    """Exact two-sided sign test."""
    n = won + lost
    return min(1.0, 2 * sum(comb(n, k) for k in range(max(won, lost), n + 1)) / 2 ** n) if n else 1.0


def good(row: dict, arm: str) -> bool:
    return (row.get(arm) or {}).get("verdict") == "good"


def paired(rows: list[dict]) -> tuple[int, int]:
    won = sum(good(r, "plumb") and not good(r, "bazaar") for r in rows)
    lost = sum(good(r, "bazaar") and not good(r, "plumb") for r in rows)
    return won, lost


def clustered(rows: list[dict]) -> tuple[int, int]:
    """Discordant needs collapsed to distinct (Bazaar URL, Plumb URL) pairs; each pair counts once, by majority."""
    by_pair = defaultdict(list)
    for r in rows:
        p, b = good(r, "plumb"), good(r, "bazaar")
        if p != b:
            by_pair[((r.get("bazaar") or {}).get("url"), (r.get("plumb") or {}).get("url"))].append(1 if p else -1)
    votes = [sum(v) for v in by_pair.values()]
    return sum(v > 0 for v in votes), sum(v < 0 for v in votes)


def cost_per_good(rows: list[dict], arm: str, fee: Decimal = Decimal(0)) -> Decimal | None:
    g = sum(good(r, arm) for r in rows)
    spent = sum((Decimal((r.get(arm) or {}).get("spent", "0")) for r in rows), Decimal(0))  # shared spend on both arms
    return (spent + fee * len(rows)) / g if g else None


def bootstrap_ratio(rows: list[dict], fee: Decimal = FEE, n: int = 10_000, seed: int = 0) -> tuple[float, float]:
    """95% interval of Bazaar/Plumb cost per good answer, resampling needs."""
    rng, out = random.Random(seed), []
    for _ in range(n):
        s = [rng.choice(rows) for _ in rows]
        b, p = cost_per_good(s, "bazaar"), cost_per_good(s, "plumb", fee)
        if b and p:
            out.append(float(b / p))
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out))]


def report(rows: list[dict], family: dict[str, str]) -> dict:
    won, lost = paired(rows)
    cw, cl = clustered(rows)
    fams = defaultdict(list)
    for r in rows:
        fams[family[r["id"]]].append(r)
    method = defaultdict(int)
    for r in rows:
        for arm in ("bazaar", "plumb"):
            g = (r.get(arm) or {}).get("grade_v2")
            if isinstance(g, dict) and not (r[arm].get("shared")):
                method[(g.get("method") or {}).get("g4", "none")] += 1
    return {
        "n": len(rows), "good": {"plumb": sum(good(r, "plumb") for r in rows), "bazaar": sum(good(r, "bazaar") for r in rows)},
        "primary": {"won": won, "lost": lost, "p": sign_test(won, lost)},
        "cluster": {"won": cw, "lost": cl, "p": sign_test(cw, cl)},
        "cost_per_good": {"bazaar": str(cost_per_good(rows, "bazaar")), "plumb_fee": str(cost_per_good(rows, "plumb", FEE)),
                          "plumb_no_fee": str(cost_per_good(rows, "plumb"))},
        "ratio_ci_95": bootstrap_ratio(rows),
        "families": {f: {"n": len(rs), "plumb": sum(good(r, "plumb") for r in rs), "bazaar": sum(good(r, "bazaar") for r in rs)}
                     for f, rs in sorted(fams.items())},
        "g4_method": dict(method),
    }

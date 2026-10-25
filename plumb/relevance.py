"""Candidate retrieval and relevance (RECOMMENDER §3): need templates, cached Titan embeddings, BM25 rerank, coverage.

Listing text is untrusted: it is only ever tokenised or embedded here, never interpreted.
"""
import json
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import numpy as np

from plumb.models import Endpoint

MASKS = [
    (re.compile(r"https?://\S+"), " <url> "),
    (re.compile(r"\b[0-9a-f]{64}\b"), " <hash> "),
    (re.compile(r"\b0x[0-9a-f]{40}\b"), " <evm> "),
    (re.compile(r"\br[1-9a-hj-np-z]{24,34}\b"), " <xrpl> "),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), " <date> "),
    (re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com|org|net|io|dev|ai|eu|xyz|app|co)\b"), " <domain> "),
    (re.compile(r"\b\d+(?:[.,]\d+)?\b"), " <num> "),
]
STOP = set("a an and are as at be by for from in is it of on or the to with what was did does do its this that latest current today today's".split())
WORD = re.compile(r"<[a-z]+>|[a-z0-9]+")


def template(need: str) -> str:
    """Mask entities (addresses, hashes, numbers, dates, URLs, domains) but keep tickers: BTC price != XRP price."""
    t = need.lower()
    for rx, sub in MASKS:
        t = rx.sub(sub, t)
    return " ".join(t.split())


def tokens(text: str) -> list[str]:
    return [w for w in WORD.findall(text.lower()) if w not in STOP and not w.startswith("<")]


def doc_text(e: Endpoint, cap: int) -> str:
    path = " ".join(re.split(r"[/\-_.]+", urlparse(e.url).path))
    return f"{e.service_name}. {path}. {' '.join(e.tags)}. {e.description[:cap]}"


class Lexical:
    """BM25 with binary term frequency, so repeating a word in a listing gains nothing."""

    def __init__(self, docs: dict[str, str], k1: float = 1.2, b: float = 0.75):
        self.terms = {i: set(tokens(t)) for i, t in docs.items()}
        n = len(self.terms)
        df = Counter(w for ts in self.terms.values() for w in ts)
        self.idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
        self.avg = sum(map(len, self.terms.values())) / max(n, 1)
        self.k1, self.b = k1, b

    def bm25(self, query: list[str], doc_id: str) -> float:
        ts = self.terms.get(doc_id, set())
        norm = self.k1 * (1 - self.b + self.b * len(ts) / self.avg)
        return sum(self.idf.get(w, 0) * (1 + self.k1) / (1 + norm) for w in set(query) if w in ts)

    def coverage(self, query: list[str], doc_id: str) -> float:
        """IDF-weighted share of the need's words present in the listing: absolute, so nonsense needs score low."""
        q = set(query)
        total = sum(self.idf.get(w, max(self.idf.values(), default=1)) for w in q)
        if not total:
            return 0.0
        return sum(self.idf.get(w, 0) for w in q if w in self.terms.get(doc_id, set())) / total


class Vectors:
    """Unit vectors for listings and need templates; the cosine search is a single matrix product."""

    def __init__(self, ids: list[str], matrix: np.ndarray, needs: dict[str, list[float]] | None = None):
        self.ids, self.m = ids, matrix.astype(np.float32)
        self.needs = needs or {}

    def top(self, vec: np.ndarray, k: int) -> list[tuple[str, float]]:
        sims = self.m @ vec.astype(np.float32)
        idx = np.argsort(-sims)[:k]
        return [(self.ids[i], float(sims[i])) for i in idx]

    @classmethod
    def load(cls, root) -> "Vectors":
        ids = json.loads((root / "listing_ids.json").read_text())
        needs_path = root / "need_vectors.json"
        needs = json.loads(needs_path.read_text()) if needs_path.exists() else {}
        return cls(ids, np.load(root / "listing_vectors.npy"), needs)


class Calibration:
    """P(exact fit) for a need nobody judged, from (embedding similarity, keyword coverage).

    A logistic model fitted on the offline judge's labels for the known needs (RECOMMENDER §3), so a new need's
    p_fit is learned from data instead of being raw coverage. Refitted at load; a few milliseconds."""

    def __init__(self, w: np.ndarray):
        self.w = w

    def p(self, sim: float, cov: float) -> float:
        return float(1 / (1 + np.exp(-(self.w[0] + self.w[1] * sim + self.w[2] * cov))))

    @staticmethod
    def features(fit: dict, vectors: "Vectors", lexical: "Lexical", skip: str | None = None):
        idx = {e: i for i, e in enumerate(vectors.ids)}
        X, y, groups = [], [], []
        for t, v in fit.items():
            vec = vectors.needs.get(t)
            if t == skip or vec is None:
                continue
            q, nv = tokens(t), np.array(vec, dtype=np.float32)
            for e, lab in v["labels"].items():
                if e in idx:
                    X.append([1.0, float(vectors.m[idx[e]] @ nv), lexical.coverage(q, e)])
                    y.append(1.0 if lab["label"] == "exact" else 0.0)
                    groups.append(t)
        return np.array(X), np.array(y), groups

    @classmethod
    def fit(cls, X: np.ndarray, y: np.ndarray, steps: int = 3000, lr: float = 0.5, l2: float = 1e-3) -> "Calibration":
        w = np.zeros(X.shape[1])
        for _ in range(steps):
            p = 1 / (1 + np.exp(-(X @ w)))
            w -= lr * (X.T @ (p - y) / len(y) + l2 * w)
        return cls(w)


def auc(scores: list[float], labels: list[float]) -> float:
    pos = [s for s, l in zip(scores, labels) if l == 1]
    neg = [s for s, l in zip(scores, labels) if l == 0]
    if not pos or not neg:
        return float("nan")
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


class Titan:
    """Amazon Titan text embeddings on Bedrock. Used offline, and online only for a need template not yet cached."""

    def __init__(self, cfg: dict, client=None):
        import boto3  # loaded only when embeddings are actually computed
        self.model, self.dims = cfg["embed"]["model"], cfg["embed"]["dims"]
        self.client = client or boto3.client("bedrock-runtime", region_name=cfg["embed"]["region"])

    def embed(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text[:8000], "dimensions": self.dims, "normalize": True})
        return json.loads(self.client.invoke_model(modelId=self.model, body=body)["body"].read())["embedding"]

    def embed_many(self, texts: list[str], workers: int = 8) -> list[list[float]]:
        with ThreadPoolExecutor(workers) as pool:
            return list(pool.map(self.embed, texts))

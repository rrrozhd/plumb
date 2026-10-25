"""Catalog adapter for the Coinbase x402 Bazaar (RECOMMENDER §1b): who sells what, at what price, on XRPL."""
import hashlib
import json

import httpx

from plumb import money
from plumb.models import Endpoint


def endpoint_id(url: str, method: str) -> str:
    return hashlib.sha256(f"{url}{method.upper()}".encode()).hexdigest()


def _leaves(obj) -> int:
    if isinstance(obj, dict):
        return sum(_leaves(v) for v in obj.values()) or 1
    if isinstance(obj, list):
        return _leaves(obj[0]) if obj else 1
    return 1


def parse_listing(res: dict, cfg: dict) -> Endpoint | None:
    """One Bazaar resource -> Endpoint, or None when it has no usable XRPL payment option."""
    x = cfg["xrpl"]
    xrpl = [a for a in res.get("accepts", []) if a.get("network") == x["network"]]
    rlusd = next((a for a in xrpl if a.get("asset") == x["rlusd_currency"]
                  and (a.get("extra") or {}).get("issuer", a.get("issuer")) == x["rlusd_issuer"]), None)
    xrp = next((a for a in xrpl if a.get("asset") == "XRP"), None)
    pay = rlusd or xrp
    if not pay or not pay.get("payTo"):
        return None
    info = ((res.get("extensions") or {}).get("bazaar") or {}).get("info") or {}
    schema = ((res.get("extensions") or {}).get("bazaar") or {}).get("schema") or {}
    method = ((info.get("input") or {}).get("method") or "GET").upper()
    example = (info.get("output") or {}).get("example")
    quality = res.get("quality") or {}
    try:
        price_rlusd = money.rlusd(rlusd["amount"]) if rlusd else None
        price_drops = money.xrp_drops(xrp["amount"]) if xrp else None
    except (TypeError, ValueError):
        return None
    if not price_rlusd and not price_drops:
        return None
    url = res["resource"]
    return Endpoint(
        id=endpoint_id(url, method), url=url, method=method, payto=pay["payTo"],
        service_name=res.get("serviceName") or "", description=res.get("description") or "",
        tags=tuple(res.get("tags") or ()), price_rlusd=price_rlusd or None, price_xrp_drops=price_drops or None,
        source_tag=(pay.get("extra") or {}).get("sourceTag", pay.get("source_tag")),
        output_fields=_leaves(example) if example is not None else 0,
        has_output_schema="output" in (schema.get("properties") or {}),
        bazaar_calls_30d=quality.get("l30DaysTotalCalls"), bazaar_payers_30d=quality.get("l30DaysUniquePayers"),
    )


def load_endpoints(cfg: dict, root) -> dict[str, Endpoint]:
    """Endpoints from the committed snapshot (data/catalog.json.gz), keyed by id."""
    import gzip
    with gzip.open(root / "catalog.json.gz", "rt") as fh:
        eps = (parse_listing(r, cfg) for r in json.load(fh))
    return {e.id: e for e in eps if e}


class Bazaar:
    def __init__(self, cfg: dict, client: httpx.Client | None = None):
        self.base = cfg["bazaar"]["base"]
        self.network = cfg["xrpl"]["network"]
        self.top_n = cfg["bazaar"]["top_n"]
        self.http = client or httpx.Client(timeout=30)

    def _get(self, path: str, **params) -> dict:
        for attempt in range(3):
            try:
                r = self.http.get(f"{self.base}{path}", params=params)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, json.JSONDecodeError):
                if attempt == 2:
                    raise
        raise AssertionError("unreachable")

    def search(self, need: str) -> list[dict]:
        """The Bazaar's own ranking for a need (<= 20 XRPL results, SPEC §11 Q3)."""
        return self._get("/search", query=need, network=self.network, limit=self.top_n).get("resources", [])

    def merchant(self, payto: str) -> list[dict]:
        """Every listing paid to one account, paged."""
        out, offset = [], 0
        while True:
            page = self._get("/merchant", payTo=payto, limit=100, offset=offset)
            items = page.get("resources", [])
            out += items
            total = (page.get("pagination") or {}).get("total", 0)
            offset += len(items)
            if not items or offset >= total:
                return out

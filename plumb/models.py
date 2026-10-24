"""Shared value types. Probabilities are floats; money is Decimal or int drops (plumb.money)."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

VERDICTS = ("good", "bad", "unsettled")


@dataclass(frozen=True)
class Endpoint:
    id: str                      # sha256(url + method), SPEC §2
    url: str
    method: str
    payto: str                   # XRPL account = operator
    service_name: str
    description: str             # untrusted listing text
    tags: tuple[str, ...]
    price_rlusd: Decimal | None  # None when the listing is XRP-only
    price_xrp_drops: int | None  # None when the listing is RLUSD-only
    source_tag: int | None
    output_fields: int           # leaf fields in the listing's output example
    has_output_schema: bool
    bazaar_calls_30d: int | None = None
    bazaar_payers_30d: int | None = None


@dataclass(frozen=True)
class Observation:
    """One purchase attempt of an endpoint: an audit (ours or vet402's) or a principal's outcome."""
    endpoint_id: str
    at: datetime                 # timezone-aware UTC
    verdict: str                 # good | bad | unsettled
    latency_ms: int | None
    source: str                  # plumb | vet402 | report | simulated
    tx_hash: str | None = None


@dataclass(frozen=True)
class Score:
    alpha: float
    beta: float
    mean: float
    lower80: float
    n_audits: int
    n_reports: int
    settle_ok: bool
    price_honest: bool = True


@dataclass(frozen=True)
class Profile:
    """A principal's hard constraints (SPEC §3.5)."""
    max_price_rlusd: Decimal | None = None
    assets: tuple[str, ...] = ("RLUSD", "XRP")
    max_latency_ms: int | None = None
    require_output_schema: bool = False


@dataclass(frozen=True)
class Persona:
    """A simulated customer agent (SPEC §10b). `prefs` drive only the simulator, never the ranker."""
    principal: str               # "sim:<name>"; a real principal is an XRPL r-address
    label: str
    profile: Profile
    prefs: dict = field(default_factory=dict)

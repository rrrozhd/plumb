"""Load config/plumb.toml. Refuses to run without every money cap (BUILD_PLAN U1)."""
import tomllib
from pathlib import Path

from plumb import money

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_CAPS = ("audit_max_per_purchase", "audit_max_per_day", "audit_max_total", "eval_max_total")


class ConfigError(ValueError):
    pass


def load(path: str | Path | None = None) -> dict:
    cfg = tomllib.loads(Path(path or ROOT / "config" / "plumb.toml").read_text())
    caps = cfg.get("caps", {})
    missing = [name for name in REQUIRED_CAPS if name not in caps]
    if missing:
        raise ConfigError(f"missing money caps in [caps]: {', '.join(missing)}")
    for name in REQUIRED_CAPS:
        try:
            money.rlusd(caps[name])
        except (TypeError, ValueError) as e:
            raise ConfigError(f"cap {name}: {e}") from None
    return cfg


def path(cfg: dict, key: str) -> Path:
    """Resolve a [paths] entry against the repository root."""
    return ROOT / cfg["paths"][key]

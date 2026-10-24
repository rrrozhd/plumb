# U0 probe 5 (read-only part): GET /supported on t54's mainnet and testnet facilitators. The /verify half of the probe
# needs a funded mainnet seed to sign a blob, so it is BLOCKED_EXTERNAL here (SPEC §11 Q4).
# usage: uv run --no-project --with httpx --with xrpl-py python research/u0/p5_t54_supported.py [research/u0/p5.json]
import json, sys, time, tomllib
from pathlib import Path
import httpx

CFG = tomllib.loads((Path(__file__).parent / "u0.toml").read_text())["t54"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "research/u0/p5.json"
out = dict(at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
for net in ("mainnet", "testnet"):
    r = httpx.get(CFG[net] + "/supported", timeout=30)
    out[net] = dict(url=CFG[net] + "/supported", status=r.status_code, body=r.json() if r.status_code == 200 else r.text[:300])
Path(OUT).write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))

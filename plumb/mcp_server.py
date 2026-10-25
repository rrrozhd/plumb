"""Plumb as an MCP server (stdio): `recommend` and `report_outcome` for any MCP-capable agent.

Run: uv run python -m plumb.mcp_server. In demo mode the tools are unpaid; the paid route is HTTP behind AP4M (U6b).
"""
from datetime import datetime, timezone

from mcp.server.mcpserver import MCPServer

from plumb import config, db, ledger, outcomes, rank

CFG = config.load()
RANKER = rank.load(CFG, config.ROOT / "data")
CONN = db.connect(config.path(CFG, "db"))
LEDGER = ledger.Ledger(CFG)
mcp = MCPServer("plumb")


@mcp.tool()
def recommend(need: str, k: int = 3, principal: str | None = None, max_price: str | None = None,
              assets: list[str] | None = None) -> dict:
    """Top-k trusted XRPL x402 endpoints for a need, ranked by expected cost per good answer for this principal.

    need: what the agent needs, in plain words. principal: the paying XRPL account (r...) or a demo persona (sim:...).
    max_price: RLUSD cap per purchase. assets: payment assets the agent can use, e.g. ["RLUSD"]."""
    c = {k_: v for k_, v in {"max_price": max_price, "assets": assets}.items() if v}
    out = RANKER.shortlist(need[:1000], k=k, principal=principal, constraints=c)
    outcomes.save_shortlist(CONN, out, need, datetime.now(timezone.utc))
    return out


@mcp.tool()
def report_outcome(shortlist_id: str, endpoint_id: str, verdict: str, principal: str | None = None,
                   payment_tx: str | None = None, invoice_id: str | None = None) -> dict:
    """Report how a recommended endpoint did: verdict good | bad | wrong_answer.

    Every report updates the principal's own ranking. With payment_tx (and invoice_id for nonce sellers) it is checked
    on the XRP Ledger and, if every check passes, also updates global trust."""
    return outcomes.report(CONN, RANKER, LEDGER, CFG, shortlist_id=shortlist_id, endpoint_id=endpoint_id,
                           verdict=verdict, principal=principal, payment_tx=payment_tx, invoice_id=invoice_id)


if __name__ == "__main__":
    mcp.run()

"""Plumb's local HTTP API (SPEC §5): POST /v1/shortlist, bound to 127.0.0.1 behind the AP4M merchant shim.

The shim proves payment (it redeemed the voucher on-chain itself) and passes the redemption tx as `paid_tx`;
shortlist.paid_tx is UNIQUE, so a replayed payment returns the stored result instead of a second answer.
"""
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from plumb.core import config, db
from plumb.customer import outcomes
from plumb.recommendation import rank

CFG = config.load()
CONN = db.connect(config.path(CFG, "db"))
RANKER = rank.load(CFG, config.ROOT / "data", conn=CONN)


@db.serialized
def shortlist(req: dict, need: str) -> dict:
    """Keep payment replay and shared state atomic; socket IO stays outside the lock."""
    paid = req.get("paid_tx")
    if paid:
        row = CONN.execute("SELECT results, id FROM shortlist WHERE paid_tx = ?", (paid,)).fetchone()
        if row:
            return {"shortlist_id": row["id"], "results": json.loads(row["results"]), "replayed": True}
    out = RANKER.shortlist(need, k=req.get("k"), principal=req.get("principal"), constraints=req.get("constraints") or {})
    outcomes.save_shortlist(CONN, out, need, datetime.now(timezone.utc))
    if paid:
        CONN.execute("UPDATE shortlist SET paid_tx = ? WHERE id = ?", (paid, out["shortlist_id"]))
        CONN.commit()
    out["paid_tx"] = paid
    return out


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802 (http.server API)
        if self.path != "/v1/shortlist":
            return self._send(404, {"error": {"code": "not_found", "message": self.path}})
        try:
            req = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 16_384)))
            need = str(req["need"])[:1000]
        except (ValueError, KeyError):
            return self._send(400, {"error": {"code": "bad_request", "message": "need is required"}})
        self._send(200, shortlist(req, need))

    def log_message(self, format, *args):  # noqa: A002 (base-class signature); one JSON line per request, no bodies
        print(json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "req": format % args}))


def main(port: int = 8402) -> None:
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

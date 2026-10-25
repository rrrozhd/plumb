"""Local stage demo: real catalog, historical purchase, simulated customer memory.

Run ``uv run python -m plumb.memory_demo``. A separate persistent worker owns
the ranker; reload actually exits that process and reopens the same SQLite file.
Only the explicit verify action uses the network, through read-only Quicknode RPC.
"""
import argparse
import json
import os
import select
import subprocess
import sys
import threading
import tomllib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from plumb.core import config
from plumb.sources import ledger


def settings() -> dict:
    return tomllib.loads((config.ROOT / "config/memory_demo.toml").read_text())


def verify_payment(historical: dict, cfg: dict) -> dict:
    """Verify a historical payment, never infer answer quality or satisfaction."""
    try:
        url = ledger.rpc_url(cfg)  # loads only ledger.env; do not expose the URL
        host = urlparse(url).hostname or ""
        if not os.environ.get("QUICKNODE_HTTP_URL") or url != os.environ["QUICKNODE_HTTP_URL"] \
                or urlparse(url).scheme != "https" or not host.endswith((".quiknode.pro", ".quicknode.com")):
            return {"verified": False, "error": "Quicknode is not configured. The public RPC fallback is disabled for this demo."}
        lg = ledger.Ledger(cfg)
        try:
            entry = lg.tx(historical["tx"])
        finally:
            if hasattr(lg, "http"):
                lg.http.close()
        payment = ledger.parse_payment(entry, cfg)
        matches = bool(payment) and payment["tx_hash"] == historical["tx"] \
            and payment["payto"] == historical["payto"] and payment["asset"] == "RLUSD" \
            and Decimal(payment["amount"]) == Decimal(historical["spent"])
        return {"verified": matches, "provider": "Quicknode", "checked_at": datetime.now(timezone.utc).isoformat(),
                "validated": entry.get("validated", False), "result": entry.get("meta", {}).get("TransactionResult"),
                "payment": payment, "error": None if matches else "Payment does not match the historical merchant and delivered RLUSD amount."}
    except Exception:
        # Provider exceptions can contain the credential-bearing URL.
        return {"verified": False, "error": "Quicknode verification failed. Historical evidence is still available; no payment was made."}


class Demo:
    def __init__(self, path: Path):
        from plumb.core import db
        from plumb.recommendation import rank
        self.cfg, self.options = config.load(), settings()
        if path.resolve() == config.path(self.cfg, "db").resolve():
            raise ValueError("The demo must not use the production database")
        self.conn = db.connect(path)
        self.ranker = rank.load(self.cfg, config.ROOT / "data", with_principals=False, conn=self.conn)
        row = self.conn.execute("SELECT value FROM meta WHERE key = 'memory_demo'").fetchone()
        self.session = json.loads(row["value"]) if row else self.fresh()

    def fresh(self) -> dict:
        from plumb.customer import memory, outcomes
        from plumb.core.models import Profile
        from plumb.recommendation.recommender import Principal
        token = uuid.uuid4().hex
        session = {"id": token, "need": self.options["need"], "principals": {}, "baseline": {}, "global": self.rows(None)}
        for role, label in (("shopper", "Fast shopper (simulated)"), ("control", "Research shopper (simulated control)")):
            who = f"sim:memory-demo-{token}-{role}"
            memory.save_principal(self.conn, Principal(who, label, Profile(), "simulated"))
            session["principals"][role] = who
            out = self.ranker.shortlist(session["need"], principal=who)
            outcomes.save_shortlist(self.conn, out, session["need"], datetime.now(timezone.utc))
            session["baseline"][role] = out
        self.session = session
        self.conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('memory_demo', ?)", (json.dumps(session),))
        self.conn.commit()
        return session

    def rows(self, who: str | None) -> list[dict]:
        return self.ranker.shortlist(self.options["need"], principal=who)["results"]

    def historical(self) -> dict:
        baseline = self.session["baseline"]["shopper"]["results"]
        if not baseline:
            return {"available": False, "error": "This snapshot has no eligible candidates."}
        top = baseline[0]
        history = json.loads((config.ROOT / self.options["history"]).read_text())
        for row in history["rows"]:
            if row["need"] != self.session["need"]:
                continue
            for arm in ("plumb", "bazaar"):
                record = row.get(arm) or {}
                if record.get("url") == top["url"] and record.get("tx"):
                    # Stored runs use absolute paths; keep this portable and confined to out/.
                    body_path = Path(record["body_file"])
                    local = config.ROOT / "out" / body_path.parent.name / body_path.name
                    body = local.read_text()[:self.options["max_response_chars"]] if local.is_file() else None
                    return {"available": True, "url": record["url"], "tx": record["tx"], "spent": record["spent"],
                            "ms": record["ms"], "verdict": record["verdict"], "body": body,
                            "payto": top["operator"], "at": history["at"], "source": f"{self.options['history']} · {row['id']}/{arm}",
                            "body_source": str(local.relative_to(config.ROOT))}
        return {"available": False, "error": "No historical purchase matches this snapshot's first choice. Feedback is disabled."}

    def state(self) -> dict:
        who = self.session["principals"]
        counts = {role: self.conn.execute("SELECT COUNT(*) FROM principal_outcome WHERE principal = ?", (p,)).fetchone()[0]
                  for role, p in who.items()}
        current = {role: self.rows(p) for role, p in who.items()}
        original = self.session["baseline"]["shopper"]["results"]
        learned = None
        if original:
            first = original[0]
            quality, _, n = self.ranker.rec.personal_q(self.ranker.rec.principals.get(who["shopper"]), first["endpoint_id"])
            learned = {"url": first["url"], "before_q_mean": first["trust"]["q_mean"], "q_mean": round(quality, 3), "n_personal": n}
        return {"worker_pid": os.getpid(), "session": self.session["id"], "need": self.session["need"],
                "principals": who, "max_latency_ms": self.options["max_latency_ms"], "counts": counts,
                "baseline": {role: out["results"] for role, out in self.session["baseline"].items()},
                "current": current, "historical": self.historical(), "learned": learned,
                "global_unchanged": self.rows(None) == self.session["global"], "feedback_source": "simulated"}

    def act(self, action: str) -> dict:
        from plumb.customer import outcomes
        feedback = None
        if action == "fresh":
            self.fresh()
        elif action == "teach":
            historical = self.historical()
            if not historical.get("available") or historical["ms"] <= self.options["max_latency_ms"]:
                raise ValueError("Historical latency does not support this simulated preference demonstration")
            original = self.session["baseline"]["shopper"]
            feedback = outcomes.report(self.conn, self.ranker, None, self.cfg,
                                       shortlist_id=original["shortlist_id"], endpoint_id=original["results"][0]["endpoint_id"],
                                       verdict="bad", principal=self.session["principals"]["shopper"])
            if not feedback.get("accepted"):
                raise ValueError("Feedback was rejected")
        elif action == "verify":
            return verify_payment(self.historical(), self.cfg)
        elif action != "state":
            raise ValueError("Unknown demo action")
        state = self.state()
        if feedback:
            state["feedback"] = feedback
        return state


class Controller:
    """Serializes worker requests; each reload creates a new OS process."""
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        if self.path == config.path(config.load(), "db").resolve():
            raise ValueError("The demo must not use the production database")
        self.lock = threading.RLock()
        self.worker = None
        self.start()

    def start(self):
        self.worker = subprocess.Popen([sys.executable, "-m", "plumb.memory_demo", "--worker", "--db", str(self.path)],
                                       cwd=config.ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def request(self, action: str) -> dict:
        with self.lock:
            assert self.worker and self.worker.stdin and self.worker.stdout
            self.worker.stdin.write(json.dumps({"action": action}) + "\n")
            self.worker.stdin.flush()
            timeout = 100 if action == "verify" else settings()["worker_timeout_s"]
            if not select.select([self.worker.stdout], [], [], timeout)[0]:
                raise RuntimeError("Demo worker timed out; reload the worker to retry")
            line = self.worker.stdout.readline()
            if not line:
                raise RuntimeError("Demo worker stopped; check the local setup")
            result = json.loads(line)
            if "worker_error" in result:
                raise RuntimeError(result["worker_error"])
            return result

    def close(self):
        with self.lock:
            if self.worker:
                self.worker.terminate()
                try:
                    self.worker.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.worker.kill()
                    self.worker.wait()
                for stream in (self.worker.stdin, self.worker.stdout):
                    if stream:
                        stream.close()
                self.worker = None

    def reload(self) -> dict:
        with self.lock:
            self.close()
            self.start()
            return self.request("state")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def main(port: int | None = None, db_path: str | Path | None = None) -> None:
    opts = settings()
    port = opts["port"] if port is None else port
    with Controller(Path(db_path) if db_path else config.ROOT / opts["db"]) as controller:
        controller.request("state")  # fail startup before opening a broken page

        class Handler(BaseHTTPRequestHandler):
            def send(self, status, body, mime="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)

            def local(self):
                host = self.headers.get("Host", "")
                return host in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}") \
                    and self.headers.get("Origin", f"http://{host}") == f"http://{host}"

            def do_GET(self):  # noqa: N802
                if not self.local():
                    return self.send(403, {"error": "Local requests only"})
                if self.path == "/":
                    return self.send(200, Path(__file__).with_suffix(".html").read_bytes(), "text/html; charset=utf-8")
                if self.path == "/favicon.ico":
                    return self.send(204, b"")
                if self.path == "/state":
                    return self.action("state")
                self.send(404, {"error": "Not found"})

            def do_POST(self):  # noqa: N802
                if not self.local() or self.headers.get("X-Plumb-Demo") != "1":
                    return self.send(403, {"error": "Local demo action only"})
                action = self.path.removeprefix("/")
                if action not in ("teach", "reload", "fresh", "verify"):
                    return self.send(404, {"error": "Not found"})
                self.action(action)

            def action(self, action):
                try:
                    self.send(200, controller.reload() if action == "reload" else controller.request(action))
                except (RuntimeError, ValueError, OSError):
                    self.send(500, {"error": "The demo worker could not finish this action. Reload it to retry."})

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        print(f"Plumb memory demo: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        finally:
            server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        demo = Demo(args.db)
        for line in sys.stdin:
            try:
                print(json.dumps(demo.act(json.loads(line)["action"])), flush=True)
            except Exception as exc:
                print(json.dumps({"worker_error": f"Demo operation failed ({type(exc).__name__})"}), flush=True)
    else:
        main(args.port, args.db)

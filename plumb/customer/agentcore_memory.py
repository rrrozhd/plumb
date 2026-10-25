"""Optional AgentCore backup/restore of exact, explicitly simulated customer events.

No model extraction or AWS calls on the ranking path. Run as a separate process:
``uv run python -m plumb.agentcore_memory --help``. Credentials come only from
env/agentcore.env; cloud errors are printed without response bodies or secrets.
"""
import argparse
import hashlib
import json
import re
import sqlite3
import tomllib
from datetime import datetime
from pathlib import Path

from plumb.core import config, money


def require_simulated(principal: str) -> None:
    if not isinstance(principal, str) or not re.fullmatch(r"sim:[A-Za-z0-9][A-Za-z0-9_-]*", principal):
        raise ValueError("an explicit sim: principal is required")


def validate_event(raw: dict, actor: str, max_bytes: int) -> None:
    """Validate cloud data before any write; ledger proof is never imported here."""
    require_simulated(actor)
    if not isinstance(raw, dict) or set(raw) != {"principal", "shortlist_id", "endpoint_id", "verdict", "at", "source"}:
        raise ValueError("invalid customer event fields")
    p = raw["principal"]
    if not isinstance(p, dict) or set(p) != {"addr", "label", "profile", "source"}:
        raise ValueError("invalid principal fields")
    if p["addr"] != actor or p["source"] != "simulated":
        raise ValueError("customer event is outside the simulated actor scope")
    for value in (p["label"], raw["shortlist_id"], raw["endpoint_id"], raw["at"]):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("customer event requires nonempty text fields")
    if raw["verdict"] not in ("good", "bad") or raw["source"] != "simulated":
        raise ValueError("invalid customer event verdict or source")
    try:
        at = datetime.fromisoformat(raw["at"])
    except ValueError:
        raise ValueError("invalid customer event timestamp") from None
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("customer event timestamp must include a time zone")
    profile = p["profile"]
    if not isinstance(profile, dict) or set(profile) != {"max_price_rlusd", "assets", "max_latency_ms", "require_output_schema"}:
        raise ValueError("invalid customer profile fields")
    if profile["max_price_rlusd"] is not None:
        try:
            money.rlusd(profile["max_price_rlusd"])
        except (TypeError, ValueError):
            raise ValueError("profile money must be an exact nonnegative decimal string") from None
    assets, latency = profile["assets"], profile["max_latency_ms"]
    if not isinstance(assets, list) or not assets or any(a not in ("RLUSD", "XRP") for a in assets):
        raise ValueError("invalid customer profile assets")
    if latency is not None and (type(latency) is not int or latency < 0):
        raise ValueError("invalid customer profile latency")
    if type(profile["require_output_schema"]) is not bool:
        raise ValueError("invalid customer profile schema requirement")
    if len(json.dumps(raw, allow_nan=False).encode()) > max_bytes:
        raise ValueError("customer event exceeds configured payload limit")


def event_token(raw: dict) -> str:
    """Stable identity: re-sending a report must never create another vote."""
    identity = ["json-v1", raw["principal"]["addr"], raw["shortlist_id"], raw["endpoint_id"]]
    return hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()


def validated_events(actor: str, events: list[dict], cfg: dict) -> list[dict]:
    require_simulated(actor)
    if len(events) > cfg["max_events_per_run"]:
        raise ValueError("customer events exceed configured run limit")
    unique = {}
    for raw in events:
        validate_event(raw, actor, cfg["max_payload_bytes"])
        key = event_token(raw)
        if key in unique and unique[key] != raw:
            raise ValueError("conflicting duplicate customer event")
        unique[key] = raw
    return list(unique.values())


class EventStore:
    def __init__(self, client, cfg: dict, memory_id: str):
        if not memory_id:
            raise ValueError("--memory-id is required until config contains a managed resource ID")
        self.client, self.cfg, self.memory_id = client, cfg, memory_id

    def push(self, actor: str, events: list[dict]) -> list[str]:
        events = validated_events(actor, events, self.cfg)
        receipts = []
        for raw in events:
            # A document-valued blob is accepted by the SDK but the service can
            # return lossy map text. Encode explicitly so strings and decimals survive.
            blob = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)
            response = self.client.create_event(
                memoryId=self.memory_id, actorId=actor, sessionId=self.cfg["session_id"],
                eventTimestamp=datetime.fromisoformat(raw["at"]), payload=[{"blob": blob}],
                clientToken=event_token(raw))
            receipts.append(response["event"]["eventId"])
        return receipts

    def read(self, actor: str) -> list[dict]:
        require_simulated(actor)
        events, seen_tokens, token = [], set(), None
        # Even an empty or malformed paginated response cannot cause an endless read.
        for _ in range(self.cfg["max_read_pages"]):
            response = self.client.list_events(
                memoryId=self.memory_id, actorId=actor, sessionId=self.cfg["session_id"],
                includePayloads=True, maxResults=self.cfg["page_size"],
                **({"nextToken": token} if token else {}))
            for event in response.get("events", []):
                if (event.get("memoryId"), event.get("actorId"), event.get("sessionId")) != (
                        self.memory_id, actor, self.cfg["session_id"]):
                    raise ValueError("AWS event envelope is outside the requested scope")
                payload = event.get("payload")
                if (not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict)
                        or set(payload[0]) != {"blob"}):
                    raise ValueError("AWS event must contain exactly one customer event blob")
                blob = payload[0]["blob"]
                if not isinstance(blob, str) or len(blob.encode()) > self.cfg["max_payload_bytes"]:
                    raise ValueError("AWS customer event blob must be bounded JSON text")
                try:
                    events.append(json.loads(blob))
                except ValueError:
                    raise ValueError("AWS customer event blob is not valid JSON") from None
            if len(events) > self.cfg["max_events_per_run"]:
                raise ValueError("customer events exceed configured run limit")
            token = response.get("nextToken")
            if not token:
                return validated_events(actor, events, self.cfg)
            if token in seen_tokens:
                raise ValueError("AWS event pagination repeated a token")
            seen_tokens.add(token)
        raise ValueError("AWS event pagination exceeds configured page limit")


def create_memory(client, cfg: dict, request_id: str) -> dict:
    """Explicit managed mutation; caller retains request_id for an uncertain retry."""
    response = client.create_memory(name=cfg["resource_name"], eventExpiryDuration=cfg["event_retention_days"],
                                    clientToken=request_id)
    m = response["memory"]
    return {"id": m["id"], "status": m["status"], "retention_days": m["eventExpiryDuration"]}


def aws_session(cfg: dict, path: Path | None = None):
    """Use this process's dedicated credentials; never the SDK fallback chain."""
    import boto3
    path = path or config.ROOT / "env" / "agentcore.env"
    if not path.exists():
        raise ValueError("env/agentcore.env is required; credentials have not been configured for this process")
    values = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    if not all(values.get(key) for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")):
        raise ValueError("env/agentcore.env is missing AWS credential fields")
    return boto3.Session(aws_access_key_id=values["AWS_ACCESS_KEY_ID"],
                         aws_secret_access_key=values["AWS_SECRET_ACCESS_KEY"],
                         aws_session_token=values.get("AWS_SESSION_TOKEN"), region_name=cfg["region"])


def load_config(path: Path | None = None) -> dict:
    cfg = tomllib.loads((path or config.ROOT / "config" / "agentcore.toml").read_text())
    for key in ("event_retention_days", "max_events_per_run", "max_payload_bytes", "page_size", "max_read_pages",
                "connect_timeout_seconds", "read_timeout_seconds"):
        if type(cfg.get(key)) is not int or cfg[key] <= 0:
            raise ValueError("AgentCore config requires positive integer limits")
    return cfg


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="read-only resource listing or resource status")
    status.add_argument("--memory-id")
    create = sub.add_parser("create", help="create a managed AWS resource; incurs AWS usage charges")
    create.add_argument("--request-id", required=True, help="retain this idempotency token for any retry")
    for command in ("push", "restore"):
        cmd = sub.add_parser(command, help="write simulated customer events to AWS" if command == "push" else
                             "read AWS events into a new local SQLite database")
        cmd.add_argument("--principal", required=True)
        cmd.add_argument("--db", required=True, type=Path)
        cmd.add_argument("--memory-id")
    args = parser.parse_args(argv)
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError
    try:
        cfg = load_config(args.config)
        if args.command in ("push", "restore"):
            require_simulated(args.principal)
            if args.command == "restore" and args.db.exists():
                raise ValueError("restore requires a new database path; existing customer data is never overwritten")
            if args.command == "push" and not args.db.is_file():
                raise ValueError("push requires an existing customer database")
        session = aws_session(cfg)
        options = Config(connect_timeout=cfg["connect_timeout_seconds"], read_timeout=cfg["read_timeout_seconds"],
                         retries={"max_attempts": 0})
        memory_id = getattr(args, "memory_id", None) or cfg.get("memory_id")
        if args.command in ("create", "status"):
            control = session.client("bedrock-agentcore-control", config=options)
            if args.command == "create":
                result = create_memory(control, cfg, args.request_id)
            elif memory_id:
                m = control.get_memory(memoryId=memory_id)["memory"]
                result = {"id": m["id"], "status": m["status"], "retention_days": m["eventExpiryDuration"]}
            else:
                response = control.list_memories(maxResults=cfg["page_size"])
                result = {"memories": [{"id": m["id"], "status": m["status"]} for m in response.get("memories", [])],
                          "more_available": bool(response.get("nextToken"))}
        else:
            from plumb.core import db
            from plumb.customer import memory
            from plumb.recommendation import rank
            store = EventStore(session.client("bedrock-agentcore", config=options), cfg, memory_id)
            if args.command == "push":
                conn = sqlite3.connect(f"{args.db.resolve().as_uri()}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                try:
                    receipts = store.push(args.principal, memory.export_events(conn, args.principal))
                finally:
                    conn.close()
                result = {"principal": args.principal, "data": "simulated", "event_ids": receipts, "count": len(receipts)}
            else:
                events = store.read(args.principal)
                app_cfg = config.load()
                rec = rank.load(app_cfg, config.ROOT / "data", with_principals=False).rec
                if any(raw["endpoint_id"] not in rec.endpoints for raw in events):
                    raise ValueError("cloud event references an endpoint outside the current catalogue")
                conn = db.connect(args.db)
                try:
                    restored = sum(memory.restore_event(conn, rec, raw) for raw in events)
                finally:
                    conn.close()
                result = {"principal": args.principal, "data": "simulated", "restored": restored,
                          "database": str(args.db.resolve())}
        print(json.dumps(result))
        return 0
    except ClientError as exc:
        print(json.dumps({"error": "AWS request failed", "code": exc.response.get("Error", {}).get("Code", "unknown")}))
    except BotoCoreError as exc:
        print(json.dumps({"error": "AWS connection or credentials failed", "code": type(exc).__name__}))
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

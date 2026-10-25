"""Offline contract checks for the optional AWS event adapter; no cloud claims."""
import copy
import json
from datetime import datetime, timezone

import boto3
from botocore.stub import Stubber
import pytest

pytestmark = pytest.mark.p0
ACTOR = "sim:memory-test"
MEMORY = "plumb_demo_customer_memory-1234567890"
SESSION = "customer-memory-v1"
AT = datetime(2026, 10, 25, tzinfo=timezone.utc)
CFG = {"region": "us-west-2", "resource_name": "plumb_demo_customer_memory",
       "event_retention_days": 7, "session_id": SESSION, "max_events_per_run": 5,
       "page_size": 2, "max_payload_bytes": 16384, "max_read_pages": 4, "memory_id": ""}


def event(shortlist="shortlist-one"):
    return {"principal": {"addr": ACTOR, "label": "Test customer (simulated)", "source": "simulated",
                          "profile": {"max_price_rlusd": "0.01000000000000000001", "assets": ["RLUSD"],
                                      "max_latency_ms": None, "require_output_schema": False}},
            "shortlist_id": shortlist, "endpoint_id": "endpoint-one", "verdict": "bad",
            "at": AT.isoformat(), "source": "simulated"}


def client(service="bedrock-agentcore"):
    return boto3.client(service, region_name=CFG["region"], aws_access_key_id="test",
                        aws_secret_access_key="test")


def wire_event(raw):
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False)


def cloud_event(raw, actor=ACTOR):
    return {"memoryId": MEMORY, "actorId": actor, "sessionId": SESSION, "eventId": "event-1234567890",
            "eventTimestamp": AT, "payload": [{"blob": wire_event(raw)}]}


def test_write_preserves_exact_money_and_scopes_actor():
    from plumb.agentcore_memory import EventStore, event_token
    raw = event()
    api = client()
    with Stubber(api) as stub:
        stub.add_response("create_event", {"event": cloud_event(raw)},
                          {"memoryId": MEMORY, "actorId": ACTOR, "sessionId": SESSION,
                           "eventTimestamp": AT, "payload": [{"blob": wire_event(raw)}], "clientToken": event_token(raw)})
        receipts = EventStore(api, CFG, MEMORY).push(ACTOR, [raw])
        assert receipts == ["event-1234567890"]
        stub.assert_no_pending_responses()
    changed = copy.deepcopy(raw)
    changed["verdict"] = "good"
    assert event_token(raw) == event_token(changed)  # same report identity cannot become a second vote


def test_read_paginates_only_requested_actor_and_preserves_event_data():
    from plumb.agentcore_memory import EventStore
    first, second = event(), event("shortlist-two")
    api = client()
    expected = {"memoryId": MEMORY, "actorId": ACTOR, "sessionId": SESSION,
                "includePayloads": True, "maxResults": 2}
    with Stubber(api) as stub:
        stub.add_response("list_events", {"events": [cloud_event(first)], "nextToken": "next"}, expected)
        stub.add_response("list_events", {"events": [cloud_event(second)]}, {**expected, "nextToken": "next"})
        assert EventStore(api, CFG, MEMORY).read(ACTOR) == [first, second]
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("damage", ["other_actor", "real_principal", "money_float", "missing_key", "unknown_key",
                                   "bad_verdict", "missing_time_zone", "wrong_profile_type", "empty_shortlist", "wrong_provenance"])
def test_rejects_malformed_or_cross_actor_payload_before_any_write(damage):
    from plumb.agentcore_memory import EventStore
    raw = event()
    if damage == "other_actor":
        raw["principal"]["addr"] = "sim:other"
    elif damage == "real_principal":
        raw["principal"]["source"] = "ledger"
    elif damage == "money_float":
        raw["principal"]["profile"]["max_price_rlusd"] = 0.01
    elif damage == "missing_key":
        raw.pop("endpoint_id")
    elif damage == "unknown_key":
        raw["payment_tx"] = "untrusted-ledger-claim"
    elif damage == "bad_verdict":
        raw["verdict"] = "wrong_answer"
    elif damage == "missing_time_zone":
        raw["at"] = "2026-10-25T00:00:00"
    elif damage == "wrong_profile_type":
        raw["principal"]["profile"]["require_output_schema"] = "false"
    elif damage == "empty_shortlist":
        raw["shortlist_id"] = ""
    elif damage == "wrong_provenance":
        raw["source"] = "report"
    api = client()
    with Stubber(api), pytest.raises(ValueError):
        EventStore(api, CFG, MEMORY).push(ACTOR, [event("valid-first"), raw])


def test_read_rejects_mismatched_aws_actor_envelope():
    from plumb.agentcore_memory import EventStore
    api = client()
    with Stubber(api) as stub:
        stub.add_response("list_events", {"events": [cloud_event(event(), "sim:other")]})
        with pytest.raises(ValueError, match="scope"):
            EventStore(api, CFG, MEMORY).read(ACTOR)


def test_rejects_real_wallet_before_aws_request():
    from plumb.agentcore_memory import EventStore
    api = client()
    with Stubber(api), pytest.raises(ValueError, match="sim:"):
        EventStore(api, CFG, MEMORY).read("rRealWallet")


def test_conflicting_duplicate_event_rejected_before_aws_request():
    from plumb.agentcore_memory import EventStore
    raw, conflict = event(), event()
    conflict["verdict"] = "good"
    api = client()
    with Stubber(api), pytest.raises(ValueError, match="conflicting"):
        EventStore(api, CFG, MEMORY).push(ACTOR, [raw, conflict])


def test_read_has_a_hard_event_bound():
    from plumb.agentcore_memory import EventStore
    api = client()
    with Stubber(api) as stub:
        stub.add_response("list_events", {"events": [cloud_event(event(str(i))) for i in range(6)]})
        with pytest.raises(ValueError, match="limit"):
            EventStore(api, CFG, MEMORY).read(ACTOR)


def test_create_uses_basic_memory_without_extraction_or_role():
    from plumb.agentcore_memory import create_memory
    api = client("bedrock-agentcore-control")
    with Stubber(api) as stub:
        stub.add_response("create_memory", {"memory": {"arn": "arn:aws:bedrock-agentcore:us-west-2:123456789012:memory/" + MEMORY,
                          "id": MEMORY, "name": CFG["resource_name"], "eventExpiryDuration": 7,
                          "status": "CREATING", "createdAt": AT, "updatedAt": AT}},
                          {"name": CFG["resource_name"], "eventExpiryDuration": 7,
                           "clientToken": "test-create-id"})
        assert create_memory(api, CFG, "test-create-id")["id"] == MEMORY
        stub.assert_no_pending_responses()


def test_credentials_require_only_the_agentcore_file(tmp_path, monkeypatch):
    from plumb.agentcore_memory import aws_session
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "unrelated-process")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "unrelated-secret")
    path = tmp_path / "agentcore.env"
    with pytest.raises(ValueError, match="agentcore.env"):
        aws_session(CFG, path)
    path.write_text("AWS_ACCESS_KEY_ID=dedicated\nAWS_SECRET_ACCESS_KEY=dedicated-secret\nAWS_SESSION_TOKEN=temporary\n")
    creds = aws_session(CFG, path).get_credentials().get_frozen_credentials()
    assert (creds.access_key, creds.secret_key, creds.token) == ("dedicated", "dedicated-secret", "temporary")


@pytest.fixture(scope="module")
def real_ranker():
    from plumb import config, rank
    return rank.load(config.load(), config.ROOT / "data", with_principals=False)


def test_cloud_roundtrip_restores_real_store_once_and_preserves_global_trust(real_ranker, tmp_path):
    from decimal import Decimal
    from plumb import db, memory
    from plumb.agentcore_memory import EventStore, event_token
    raw = event()
    raw["endpoint_id"] = next(iter(real_ranker.rec.endpoints))
    before = copy.deepcopy(real_ranker.rec.trust)
    source = db.connect(tmp_path / "source.sqlite")
    target = db.connect(tmp_path / "target.sqlite")
    try:
        assert memory.restore_event(source, real_ranker.rec, raw)
        exported = memory.export_events(source, ACTOR)
        assert exported == [raw]
        api = client()
        with Stubber(api) as stub:
            stub.add_response("create_event", {"event": cloud_event(raw)},
                              {"memoryId": MEMORY, "actorId": ACTOR, "sessionId": SESSION,
                               "eventTimestamp": AT, "payload": [{"blob": wire_event(raw)}], "clientToken": event_token(raw)})
            stub.add_response("list_events", {"events": [cloud_event(raw), cloud_event(raw)]})
            store = EventStore(api, CFG, MEMORY)
            store.push(ACTOR, exported)
            restored = store.read(ACTOR)
        assert len(restored) == 1
        assert memory.restore_event(target, real_ranker.rec, restored[0])
        assert not memory.restore_event(target, real_ranker.rec, restored[0])
        customer = memory.load_principal(target, ACTOR)
        assert customer.profile.max_price_rlusd == Decimal("0.01000000000000000001")
        assert customer.outcomes[raw["endpoint_id"]] == [0, 1]
        assert memory.load_principal(target, "sim:other") is None
        assert real_ranker.rec.trust == before
        conflict = copy.deepcopy(raw)
        conflict["verdict"] = "good"
        with pytest.raises(ValueError):
            memory.restore_event(target, real_ranker.rec, conflict)
        assert target.execute("SELECT COUNT(*) FROM principal_outcome").fetchone()[0] == 1
    finally:
        source.close()
        target.close()


def test_restore_command_reads_cloud_into_fresh_database(real_ranker, tmp_path, monkeypatch, capsys):
    from plumb import agentcore_memory as ac, db, memory, rank
    raw = event()
    raw["endpoint_id"] = next(iter(real_ranker.rec.endpoints))
    api = client()
    class Session:
        def client(self, *args, **kwargs):
            return api
    monkeypatch.setattr(ac, "aws_session", lambda cfg: Session())
    monkeypatch.setattr(rank, "load", lambda *args, **kwargs: real_ranker)
    target = tmp_path / "new.sqlite"
    with Stubber(api) as stub:
        stub.add_response("list_events", {"events": [cloud_event(raw)]})
        assert ac.main(["restore", "--db", str(target), "--principal", ACTOR, "--memory-id", MEMORY]) == 0
        stub.assert_no_pending_responses()
    assert '"restored": 1' in capsys.readouterr().out
    conn = db.connect(target)
    try:
        assert memory.export_events(conn, ACTOR) == [raw]
    finally:
        conn.close()
    with Stubber(api):
        assert ac.main(["restore", "--db", str(target), "--principal", ACTOR, "--memory-id", MEMORY]) == 1
    assert "new database path" in capsys.readouterr().out


def test_cli_aws_errors_never_print_service_response_message(monkeypatch, capsys):
    from plumb import agentcore_memory as ac
    api = client("bedrock-agentcore-control")
    class Session:
        def client(self, *args, **kwargs):
            return api
    monkeypatch.setattr(ac, "aws_session", lambda cfg: Session())
    with Stubber(api) as stub:
        stub.add_client_error("list_memories", service_error_code="AccessDeniedException",
                              service_message="never print this private service detail")
        assert ac.main(["status"]) == 1
    output = capsys.readouterr().out
    assert "AccessDeniedException" in output
    assert "private service detail" not in output


def test_push_command_exports_only_named_simulated_customer(real_ranker, tmp_path, monkeypatch, capsys):
    from plumb import agentcore_memory as ac, db, memory
    raw = event()
    raw["endpoint_id"] = next(iter(real_ranker.rec.endpoints))
    other = copy.deepcopy(raw)
    other["principal"]["addr"] = "sim:other"
    path = tmp_path / "source.sqlite"
    conn = db.connect(path)
    try:
        assert memory.restore_event(conn, real_ranker.rec, raw)
        assert memory.restore_event(conn, real_ranker.rec, other)
    finally:
        conn.close()
    api = client()
    class Session:
        def client(self, *args, **kwargs):
            return api
    monkeypatch.setattr(ac, "aws_session", lambda cfg: Session())
    with Stubber(api) as stub:
        stub.add_response("create_event", {"event": cloud_event(raw)},
                          {"memoryId": MEMORY, "actorId": ACTOR, "sessionId": SESSION,
                           "eventTimestamp": AT, "payload": [{"blob": wire_event(raw)}], "clientToken": ac.event_token(raw)})
        assert ac.main(["push", "--db", str(path), "--principal", ACTOR, "--memory-id", MEMORY]) == 0
        stub.assert_no_pending_responses()
    assert '"count": 1' in capsys.readouterr().out


def test_repeated_page_token_fails_instead_of_looping():
    from plumb.agentcore_memory import EventStore
    api = client()
    with Stubber(api) as stub:
        stub.add_response("list_events", {"events": [], "nextToken": "same"})
        stub.add_response("list_events", {"events": [], "nextToken": "same"})
        with pytest.raises(ValueError, match="repeated"):
            EventStore(api, CFG, MEMORY).read(ACTOR)
        stub.assert_no_pending_responses()


def test_json_blob_preserves_punctuation_and_unicode():
    from plumb.agentcore_memory import EventStore
    raw = event()
    raw["principal"]["label"] = 'Customer, {label=not data}, "quoted" ☃'
    api = client()
    with Stubber(api) as stub:
        stub.add_response("list_events", {"events": [cloud_event(raw)]})
        assert EventStore(api, CFG, MEMORY).read(ACTOR) == [raw]


@pytest.mark.parametrize("blob", ['{principal={addr=sim:memory-test}, verdict=bad}', '{"principal":', '"just a string"'])
def test_rejects_lossy_or_malformed_blob_without_echoing_content(blob):
    from plumb.agentcore_memory import EventStore
    envelope = cloud_event(event())
    envelope["payload"] = [{"blob": blob}]
    api = client()
    with Stubber(api) as stub:
        stub.add_response("list_events", {"events": [envelope]})
        with pytest.raises(ValueError) as caught:
            EventStore(api, CFG, MEMORY).read(ACTOR)
    assert blob not in str(caught.value)

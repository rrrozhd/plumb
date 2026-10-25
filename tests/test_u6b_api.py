import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

pytestmark = pytest.mark.p0


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    from plumb.interfaces import api
    from plumb.core import config, db
    from plumb.recommendation import rank
    api.CONN = db.connect(tmp_path_factory.mktemp("db") / "t.db")
    api.RANKER = rank.load(api.CFG, config.ROOT / "data", with_principals=False, conn=api.CONN)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), api.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1/shortlist"
    srv.shutdown()


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_paid_shortlist_replays_instead_of_answering_twice(base):
    tx = "0x" + "ab" * 32
    s1, a = post(base, {"need": "Current XRP price in USD", "paid_tx": tx})
    s2, b = post(base, {"need": "Something else entirely", "paid_tx": tx})
    assert s1 == s2 == 200
    assert b["replayed"] and b["shortlist_id"] == a["shortlist_id"] and b["results"] == a["results"]


def test_missing_need_is_400(base):
    assert post(base, {"k": 3})[0] == 400


def test_http_recommendations_restore_customer_feedback(base):
    from plumb.interfaces import api
    from plumb.core import config
    from plumb.customer import outcomes
    from plumb.recommendation import rank
    need = "Current BTC perpetual futures funding rate on major exchanges"
    req = {"need": need, "principal": "sim:http"}
    _, before = post(base, req)
    first = before["results"][0]["endpoint_id"]
    result = outcomes.report(api.CONN, api.RANKER, None, api.CFG, shortlist_id=before["shortlist_id"],
                             endpoint_id=first, verdict="bad")
    assert result["persisted"]
    api.RANKER = rank.load(api.CFG, config.ROOT / "data", with_principals=False, conn=api.CONN)
    _, after = post(base, req)
    _, control = post(base, {"need": need, "principal": "sim:unaffected"})
    assert after["results"][0]["endpoint_id"] != first
    assert control["results"][0]["endpoint_id"] == first

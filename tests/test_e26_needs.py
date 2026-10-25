"""E26's needs are independent ranking decisions: no shared template, none seen before (prereg eval/e26_prereg.md)."""
import json
from collections import Counter

import pytest
import yaml

from plumb.core import config
from plumb.evaluation import grader
from plumb.recommendation import relevance

pytestmark = pytest.mark.p0
EVAL = config.ROOT / "eval"


def test_e26_templates_are_distinct_and_unseen():
    q = yaml.safe_load((EVAL / "queries_e26.yaml").read_text())["queries"]
    ts = [relevance.template(x["need"]) for x in q]
    assert len(q) == 100 and len(set(ts)) == 100
    seen = {relevance.template(x["need"]) for f in ("queries.yaml", "queries_e22.yaml") for x in yaml.safe_load((EVAL / f).read_text())["queries"]}
    seen |= set(json.loads((config.ROOT / "data" / "fit_v2.json").read_text()))
    assert not seen & set(ts)
    assert Counter(x["family"] for x in q) == {"crypto_usd": 25, "fx": 25, "weather": 15, "holiday": 15, "crypto_eur": 10, "block": 10}
    assert all(x["oracle"]["kind"] in grader.FAMILY for x in q)

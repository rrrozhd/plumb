from decimal import Decimal

import pytest

from plumb import stats

pytestmark = pytest.mark.p0


def row(i, b, p, bu="B", pu="P", spent="0.001"):
    return {"id": i, "bazaar": {"url": bu, "verdict": "good" if b else "bad", "spent": spent},
            "plumb": {"url": pu, "verdict": "good" if p else "bad", "spent": spent}}


def test_sign_test_matches_known_values():
    assert stats.sign_test(4, 0) == 0.125 and stats.sign_test(6, 1) == 0.125 and stats.sign_test(0, 0) == 1.0


def test_cluster_collapses_needs_that_share_both_endpoints():
    rows = [row(f"a{i}", False, True) for i in range(5)] + [row("b", True, False, "B2", "P2")]
    assert stats.paired(rows) == (5, 1) and stats.clustered(rows) == (1, 1)


def test_cost_per_good_counts_fee_per_need():
    rows = [row("a", True, True), row("b", False, True)]
    assert stats.cost_per_good(rows, "plumb", Decimal("0.002")) == Decimal("0.003")
    assert stats.cost_per_good(rows, "bazaar") == Decimal("0.002")

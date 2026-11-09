"""The eval gate: tests that score the system on the eval set.

Tests marked `eval` call models and use API quota, so `make test` skips them
and `make eval` runs them. Later this file loads evals/data, runs the system,
and fails when a metric drops below its threshold (the CI gate).
"""

import pytest


@pytest.mark.eval
def test_eval_set_exists() -> None:
    pytest.skip("No eval set yet. Add one, then assert on its metrics here.")

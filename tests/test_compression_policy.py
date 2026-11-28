import os
import sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from compression_policy import DEFAULT_LEVEL, POLICIES, get_policy, needs_compaction


def test_default_level_is_safe():
    assert DEFAULT_LEVEL == "safe" and get_policy(None).level == "safe"


def test_known_levels_exist():
    assert set(POLICIES) == {"safe", "balanced", "aggressive"}


def test_triggers_at():
    assert get_policy("safe").triggers_at(1000) == 700
    assert get_policy("balanced").triggers_at(1000) == 800
    assert get_policy("aggressive").triggers_at(1000) == 880


def test_needs_compaction_threshold():
    assert needs_compaction(701, 1000, "safe") and not needs_compaction(699, 1000, "safe")


def test_unknown_level_and_bad_num_ctx_raise():
    with pytest.raises(ValueError):
        get_policy("frugal")
    with pytest.raises(ValueError):
        get_policy("safe").triggers_at(0)

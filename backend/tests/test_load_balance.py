"""Tests for GLM-5.1 load balancing (R2 feature)."""

from __future__ import annotations

import pytest

from app.core.model_routing import (
    get_load_balance_group,
    select_service_by_weight,
    LOAD_BALANCE_GROUPS,
)


class TestGetLoadBalanceGroup:
    def test_glm51_has_group(self) -> None:
        group = get_load_balance_group("GLM-5.1")
        assert group is not None
        assert len(group) == 1
        services = [s["service"] for s in group]
        assert services == ["llm.glm51.enterprise"]

    def test_other_model_no_group(self) -> None:
        assert get_load_balance_group("astron-code-latest") is None
        assert get_load_balance_group("MiniMax-M3") is None
        assert get_load_balance_group("qwen3-coder-plus") is None

    def test_unknown_model_no_group(self) -> None:
        assert get_load_balance_group("nonexistent-model") is None


class TestSelectServiceByWeight:
    def test_glm51_single_enterprise_source(self) -> None:
        services = LOAD_BALANCE_GROUPS["GLM-5.1"]
        for _ in range(100):
            assert select_service_by_weight(services) == "llm.glm51.enterprise"

    def test_single_service_always_selected(self) -> None:
        result = select_service_by_weight([{"service": "only-one", "weight": 1}])
        assert result == "only-one"

    def test_equal_weights(self) -> None:
        services = [
            {"service": "a", "weight": 1},
            {"service": "b", "weight": 1},
        ]
        counts: dict[str, int] = {}
        for _ in range(1000):
            s = select_service_by_weight(services)
            counts[s] = counts.get(s, 0) + 1
        # Should be roughly 50/50
        assert 0.40 < counts["a"] / 1000 < 0.60
        assert 0.40 < counts["b"] / 1000 < 0.60

"""
單元測試 — validate_config()
============================
測試 config_schema.py 中的驗證規則，
涵蓋原有規則和新增的 NPU/KG/SelfEvolution/CapabilityACL 驗證。
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config_schema import (  # noqa: E402
    AgentOSConfig,
    BudgetConfig,
    SandboxConfig,
    TruncationConfig,
    NPUConfig,
    KGConfig,
    SelfEvolutionConfig,
    CapabilityACLConfig,
    RolePermissions,
    validate_config,
)


# ============================================================
# 預設配置應全部通過（唯一例外: 無 API Key 警告）
# ============================================================

class TestDefaultConfig:
    def test_default_has_api_key_warning(self):
        """預設配置沒有 API Key，應產生一條警告"""
        config = AgentOSConfig()
        warnings = validate_config(config)
        assert any("API Key" in w for w in warnings)

    def test_warnings_count(self):
        """預設配置除了 API Key 外不應有其他警告"""
        config = AgentOSConfig()
        warnings = validate_config(config)
        # 只有 API Key 警告
        assert len(warnings) == 1


# ============================================================
# Budget 驗證
# ============================================================

class TestBudgetValidation:
    def test_zero_budget(self):
        config = AgentOSConfig(budget=BudgetConfig(daily_limit_m=0))
        warnings = validate_config(config)
        assert any("daily_limit_m" in w for w in warnings)

    def test_negative_budget(self):
        config = AgentOSConfig(budget=BudgetConfig(daily_limit_m=-1))
        warnings = validate_config(config)
        assert any("daily_limit_m" in w for w in warnings)


# ============================================================
# Sandbox 驗證
# ============================================================

class TestSandboxValidation:
    def test_short_timeout(self):
        config = AgentOSConfig(sandbox=SandboxConfig(timeout_seconds=2))
        warnings = validate_config(config)
        assert any("timeout_seconds" in w for w in warnings)

    def test_truncation_ratio_overflow(self):
        config = AgentOSConfig(
            sandbox=SandboxConfig(
                truncation=TruncationConfig(head_ratio=0.6, tail_ratio=0.6)
            )
        )
        warnings = validate_config(config)
        assert any("head_ratio" in w for w in warnings)


# ============================================================
# NPU 驗證
# ============================================================

class TestNPUValidation:
    def test_valid_backend(self):
        config = AgentOSConfig(npu=NPUConfig(force_backend="cuda"))
        warnings = validate_config(config)
        assert not any("npu.force_backend" in w for w in warnings)

    def test_invalid_backend(self):
        config = AgentOSConfig(npu=NPUConfig(force_backend="quantum_chip"))
        warnings = validate_config(config)
        assert any("npu.force_backend" in w for w in warnings)

    def test_empty_backend_ok(self):
        config = AgentOSConfig(npu=NPUConfig(force_backend=""))
        warnings = validate_config(config)
        assert not any("npu.force_backend" in w for w in warnings)


# ============================================================
# KG 驗證
# ============================================================

class TestKGValidation:
    def test_neo4j_without_uri(self):
        config = AgentOSConfig(kg=KGConfig(backend="neo4j", neo4j_uri=""))
        warnings = validate_config(config)
        assert any("neo4j_uri" in w for w in warnings)

    def test_neo4j_with_uri(self):
        config = AgentOSConfig(
            kg=KGConfig(backend="neo4j", neo4j_uri="bolt://localhost:7687")
        )
        warnings = validate_config(config)
        assert not any("neo4j_uri" in w for w in warnings)

    def test_zero_decay(self):
        config = AgentOSConfig(kg=KGConfig(decay_half_life_days=0))
        warnings = validate_config(config)
        assert any("decay_half_life_days" in w for w in warnings)

    def test_negative_decay(self):
        config = AgentOSConfig(kg=KGConfig(decay_half_life_days=-1))
        warnings = validate_config(config)
        assert any("decay_half_life_days" in w for w in warnings)


# ============================================================
# Self-Evolution 驗證
# ============================================================

class TestSelfEvolutionValidation:
    def test_disabled_skips_validation(self):
        """disabled 時不檢查子項"""
        config = AgentOSConfig(
            self_evolution=SelfEvolutionConfig(enabled=False, interval_hours=0)
        )
        warnings = validate_config(config)
        assert not any("interval_hours" in w for w in warnings)

    def test_short_interval(self):
        config = AgentOSConfig(
            self_evolution=SelfEvolutionConfig(enabled=True, interval_hours=0)
        )
        warnings = validate_config(config)
        assert any("interval_hours" in w for w in warnings)

    def test_too_few_samples(self):
        config = AgentOSConfig(
            self_evolution=SelfEvolutionConfig(enabled=True, min_samples=5)
        )
        warnings = validate_config(config)
        assert any("min_samples" in w for w in warnings)

    def test_zero_lora_rank(self):
        config = AgentOSConfig(
            self_evolution=SelfEvolutionConfig(enabled=True, lora_rank=0)
        )
        warnings = validate_config(config)
        assert any("lora_rank" in w for w in warnings)


# ============================================================
# Capability ACL 驗證
# ============================================================

class TestCapabilityACLValidation:
    def test_default_role_exists(self):
        """預設配置的 default role 在 roles 中"""
        config = AgentOSConfig()
        warnings = validate_config(config)
        assert not any("default_role" in w for w in warnings)

    def test_missing_default_role(self):
        config = AgentOSConfig(
            capability_acl=CapabilityACLConfig(
                default_role="nonexistent",
                roles={"admin": RolePermissions()},
            )
        )
        warnings = validate_config(config)
        assert any("default_role" in w for w in warnings)

"""
AgentOS Config Schema
=====================
config.yaml 的驗證 schema + 載入器。
Onboarding Wizard 生成此檔案，使用者也可手動編輯。
所有欄位都有安全的預設值——即使 config.yaml 只有一行 API Key，OS 也能跑。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


# ============================================================
# Dataclass 定義 (每個區塊對應 config.yaml 的一個頂層 key)
# ============================================================

@dataclass
class ProviderConfig:
    """單一 API Provider 設定"""
    name: str = "openai"
    api_key: str = ""
    base_url: Optional[str] = None  # Ollama 等自訂 endpoint
    models: list[str] = field(default_factory=lambda: ["gpt-4o"])


@dataclass
class GatewayConfig:
    """API Gateway 設定"""
    providers: list[ProviderConfig] = field(default_factory=lambda: [ProviderConfig()])
    agents: dict[str, str] = field(default_factory=lambda: {"default": "openai/gpt-4o"})
    # agents 格式: { "agent_id": "provider/model" }


@dataclass
class KernelConfig:
    """靈魂載入設定"""
    soul_path: str = "./SOUL.md"


@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_multiplier: int = 2
    retryable_codes: list[int] = field(default_factory=lambda: [429, 500, 502, 503])


@dataclass
class RateLimitConfig:
    rpm: int = 30
    tpm: int = 100_000


@dataclass
class WatchdogConfig:
    max_steps: int = 50
    timeout_per_step: int = 300  # 秒


@dataclass
class ContextConfig:
    compression_trigger: float = 0.8
    keep_recent_turns: int = 3
    summary_model: str = "auto"  # auto = 使用最便宜的可用模型


@dataclass
class EngineConfig:
    """引擎設定"""
    streaming: bool = True
    retry: RetryConfig = field(default_factory=RetryConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
    context: ContextConfig = field(default_factory=ContextConfig)


@dataclass
class BudgetConfig:
    """預算守衛設定 (單位: M = 百萬 Token)"""
    daily_limit_m: float = 1.0
    warn_before_task: bool = True
    track_input_output: bool = True


@dataclass
class TruncationConfig:
    threshold: int = 2000
    head_ratio: float = 0.1
    tail_ratio: float = 0.2
    disabled: bool = False


@dataclass
class SandboxConfig:
    """沙盒設定"""
    default_network: str = "deny"  # "deny" | "allow"
    timeout_seconds: int = 60
    truncation: TruncationConfig = field(default_factory=TruncationConfig)


@dataclass
class MessengerChannelConfig:
    bot_token: str = ""
    enabled: bool = False


@dataclass
class MessengerConfig:
    """通訊軟體設定"""
    telegram: MessengerChannelConfig = field(default_factory=MessengerChannelConfig)
    discord: MessengerChannelConfig = field(default_factory=MessengerChannelConfig)


@dataclass
class DashboardConfig:
    """面板設定"""
    port: int = 8080
    enabled: bool = True


@dataclass
class AgentOSConfig:
    """AgentOS 完整設定 — config.yaml 的根"""
    kernel: KernelConfig = field(default_factory=KernelConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    engine: EngineConfig = field(default_factory=EngineConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    messenger: MessengerConfig = field(default_factory=MessengerConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)


# ============================================================
# 載入器
# ============================================================

def _merge_dict(target: dict, source: dict) -> dict:
    """遞歸合併 source 到 target (source 覆蓋 target)"""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _merge_dict(target[key], value)
        else:
            target[key] = value
    return target


def _dict_to_dataclass(cls, data: dict) -> Any:
    """將 dict 遞歸轉換為 dataclass"""
    if not isinstance(data, dict):
        return data

    import dataclasses
    kwargs = {}
    fields = {f.name: f for f in dataclasses.fields(cls)}

    for key, value in data.items():
        if key not in fields:
            continue  # 忽略未知欄位

        f = fields[key]
        # 取得實際的 type (解析 string annotation)
        field_type = f.type if not isinstance(f.type, str) else eval(f.type)

        # 處理巢狀 dataclass
        if dataclasses.is_dataclass(field_type) and isinstance(value, dict):
            kwargs[key] = _dict_to_dataclass(field_type, value)
        # 處理 list[ProviderConfig]
        elif key == "providers" and isinstance(value, list):
            kwargs[key] = [_dict_to_dataclass(ProviderConfig, v) if isinstance(v, dict) else v for v in value]
        else:
            kwargs[key] = value

    return cls(**kwargs)


def load_config(config_path: str = "./config.yaml") -> AgentOSConfig:
    """
    載入 config.yaml 並回傳 AgentOSConfig。
    缺少的欄位自動填入安全預設值。
    檔案不存在時回傳全預設設定。
    """
    path = Path(config_path)

    if not path.exists():
        return AgentOSConfig()

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    return _dict_to_dataclass(AgentOSConfig, raw)


def save_config(config: AgentOSConfig, config_path: str = "./config.yaml") -> None:
    """將 AgentOSConfig 序列化並寫入 config.yaml"""
    import dataclasses

    def _to_dict(obj: Any) -> Any:
        if dataclasses.is_dataclass(obj):
            return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
        return obj

    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(_to_dict(config), f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def validate_config(config: AgentOSConfig) -> list[str]:
    """驗證設定的合理性，回傳警告訊息列表 (空 = 全部通過)"""
    warnings = []

    # 檢查至少有一個 Provider 設定了 API Key
    has_key = any(p.api_key for p in config.gateway.providers)
    has_ollama = any(p.base_url for p in config.gateway.providers)
    if not has_key and not has_ollama:
        warnings.append("⚠️ 沒有設定任何 API Key 或 Ollama。Agent 無法呼叫模型。")

    # 檢查預算上限
    if config.budget.daily_limit_m <= 0:
        warnings.append("⚠️ daily_limit_m <= 0，Agent 將無法執行任何任務。")

    # 檢查沙盒超時
    if config.sandbox.timeout_seconds < 5:
        warnings.append("⚠️ sandbox.timeout_seconds < 5 秒，大部分任務會超時失敗。")

    # 檢查截斷比例
    t = config.sandbox.truncation
    if not t.disabled and (t.head_ratio + t.tail_ratio) > 1.0:
        warnings.append("⚠️ head_ratio + tail_ratio > 1.0，截斷設定不合理。")

    return warnings

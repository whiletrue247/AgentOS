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

from paths import get_soul_path, get_config_path


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
    soul_path: str = field(default_factory=lambda: str(get_soul_path()))


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
    docker_runtime: str = ""  # e.g., "runsc" for gVisor
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


# ============================================================
# NPU 偵測配置
# ============================================================

@dataclass
class NPUConfig:
    """NPU / 硬體加速器偵測設定"""
    enabled: bool = True                           # 是否在啟動時偵測硬體
    prefer_local_inference: bool = False            # 優先使用本地推論（有 NPU 時自動路由到 Ollama）
    force_backend: str = ""                         # 強制指定 backend: cpu, mps, cuda, rocm, xpu, ""
    fallback_to_cpu: bool = True                   # 指定的 backend 不可用時是否退回 CPU
    ollama_auto_offload: bool = True               # 偵測到 GPU/NPU 時自動啟用 Ollama offload


# ============================================================
# KG (Knowledge Graph) 後端配置
# ============================================================

@dataclass
class KGConfig:
    """Personal Knowledge Graph 後端設定"""
    enabled: bool = True
    backend: str = "auto"                           # "auto" | "neo4j" | "networkx"
    neo4j_uri: str = ""                             # e.g., "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    data_path: str = "data/pkg/graph.json"          # NetworkX fallback 的 JSON 路徑
    decay_half_life_days: float = 7.0               # 邊權重衰減半衰期（天）
    decay_min_weight: float = 0.05                  # 低於此權重的邊會被刪除
    max_subgraph_depth: int = 2                     # get_subgraph 最大深度


# ============================================================
# Self-Evolution (LoRA 自我進化) 配置
# ============================================================

@dataclass
class SelfEvolutionConfig:
    """LoRA / PEFT 自我進化（個人化微調）設定"""
    enabled: bool = False                           # 預設關閉，需要使用者主動開啟
    interval_hours: int = 24                        # 微調排程間隔（小時）
    data_dir: str = "data/lora"                     # 訓練資料與模型輸出目錄
    base_model: str = "unsloth/llama-3.2-3b-instruct-bnb-4bit"  # 基礎模型
    train_backend: str = "auto"                     # "auto" | "unsloth" | "peft"
    min_samples: int = 50                           # 最少訓練樣本數，不足則跳過
    lora_rank: int = 16                             # LoRA rank
    lora_alpha: int = 32                            # LoRA alpha
    learning_rate: float = 2e-4
    max_steps: int = 100


# ============================================================
# Capability ACL (Zero Trust) 配置
# ============================================================

@dataclass
class RolePermissions:
    """單一角色的權限定義"""
    can_execute_shell: bool = False
    can_access_network: bool = False
    can_read_files: bool = True
    can_write_files: bool = False
    can_install_packages: bool = False


@dataclass
class CapabilityACLConfig:
    """Zero Trust 能力控制列表設定"""
    permissions_path: str = "config/permissions.yaml"   # YAML 權限檔路徑（向後相容）
    default_role: str = "default"                        # 未指定角色時的預設角色
    auto_deny_no_tty: bool = True                       # 無 TTY 時自動拒絕危險操作
    destructive_patterns: list[str] = field(
        default_factory=lambda: [r"rm\s+-rf\s+/", r"mkfs", r"dd\s+if="]
    )  # 高危指令正規表示式
    roles: dict[str, RolePermissions] = field(
        default_factory=lambda: {
            "default": RolePermissions(
                can_execute_shell=False,
                can_access_network=False,
            ),
            "orchestrator": RolePermissions(
                can_execute_shell=True,
                can_access_network=True,
                can_write_files=True,
            ),
            "coder": RolePermissions(
                can_execute_shell=True,
                can_access_network=False,
                can_write_files=True,
            ),
        }
    )


@dataclass
class MCPServerConfig:
    """單一 MCP Server 設定檔"""
    command: str = ""       
    args: list[str] = field(default_factory=list) 
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class MCPConfig:
    """全域 MCP Server 設定"""
    servers: dict[str, MCPServerConfig] = field(default_factory=dict)


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
    npu: NPUConfig = field(default_factory=NPUConfig)
    kg: KGConfig = field(default_factory=KGConfig)
    self_evolution: SelfEvolutionConfig = field(default_factory=SelfEvolutionConfig)
    capability_acl: CapabilityACLConfig = field(default_factory=CapabilityACLConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)


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
        # 處理 dict[str, MCPServerConfig]
        elif key == "servers" and isinstance(value, dict):
            kwargs[key] = {k: _dict_to_dataclass(MCPServerConfig, v) if isinstance(v, dict) else v for k, v in value.items()}
        else:
            kwargs[key] = value

    return cls(**kwargs)


def load_config(config_path: Optional[str] = None) -> AgentOSConfig:
    """
    載入 config.yaml 並回傳 AgentOSConfig。
    缺少的欄位自動填入安全預設值。
    檔案不存在時回傳全預設設定。
    支援 Fernet 加密 (ENC[...]) 自動解密。
    """
    if config_path is None:
        path = get_config_path()
    else:
        path = Path(config_path)

    # 載入專案根目錄的 .env 檔案
    try:
        from dotenv import load_dotenv
        load_dotenv(path.parent / ".env")
    except ImportError:
        pass

    if not path.exists():
        return AgentOSConfig()

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = _dict_to_dataclass(AgentOSConfig, raw)
    
    # 嘗試載入解密模組
    try:
        from utils.secret_manager import decrypt_value, is_encrypted
    except ImportError:
        decrypt_value = lambda x: x
        is_encrypted = lambda x: False

    # -- 解密與環境變數覆寫 (Environment Variable Overrides) --
    for provider in config.gateway.providers:
        # 1. 如果設定檔內是加密的，先解密
        if is_encrypted(provider.api_key):
            provider.api_key = decrypt_value(provider.api_key)
            
        # 2. 如果宣告了環境變數，最高優先級覆寫
        env_key = f"AGENTOS_{provider.name.upper()}_API_KEY"
        if env_val := os.environ.get(env_key):
            provider.api_key = env_val
            
    # Telegram Bot Token 解密與覆寫
    tg = config.messenger.telegram
    if is_encrypted(tg.bot_token):
        tg.bot_token = decrypt_value(tg.bot_token)
    if env_tg := os.environ.get("AGENTOS_TELEGRAM_BOT_TOKEN"):
        tg.bot_token = env_tg
        
    return config


def save_config(config: AgentOSConfig, config_path: Optional[str] = None) -> None:
    """將 AgentOSConfig 序列化並寫入 config.yaml"""
    import dataclasses

    def _to_dict(obj: Any) -> Any:
        if dataclasses.is_dataclass(obj):
            return {k: _to_dict(v) for k, v in dataclasses.asdict(obj).items()}
        return obj

    if config_path is None:
        path = get_config_path()
    else:
        path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(_to_dict(config), f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


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

    # 檢查沙箱超時
    if config.sandbox.timeout_seconds < 5:
        warnings.append("⚠️ sandbox.timeout_seconds < 5 秒，大部分任務會超時失敗。")

    # 檢查截斷比例
    t = config.sandbox.truncation
    if not t.disabled and (t.head_ratio + t.tail_ratio) > 1.0:
        warnings.append("⚠️ head_ratio + tail_ratio > 1.0，截斷設定不合理。")

    # NPU 配置檢查
    if config.npu.force_backend and config.npu.force_backend not in (
        "cpu", "mps", "cuda", "rocm", "xpu", "coreml", "tensorrt", "directml", "openvino"
    ):
        warnings.append(f"⚠️ npu.force_backend='{config.npu.force_backend}' 不是已知的 backend。")

    # KG 配置檢查
    if config.kg.enabled and config.kg.backend == "neo4j" and not config.kg.neo4j_uri:
        warnings.append("⚠️ kg.backend='neo4j' 但未設定 neo4j_uri。")
    if config.kg.decay_half_life_days <= 0:
        warnings.append("⚠️ kg.decay_half_life_days <= 0，知識圖譜衰減設定不合理。")

    # Self-Evolution 配置檢查
    if config.self_evolution.enabled:
        if config.self_evolution.interval_hours < 1:
            warnings.append("⚠️ self_evolution.interval_hours < 1，微調間隔過短。")
        if config.self_evolution.min_samples < 10:
            warnings.append("⚠️ self_evolution.min_samples < 10，訓練樣本過少可能導致過擬合。")
        if config.self_evolution.lora_rank < 1:
            warnings.append("⚠️ self_evolution.lora_rank < 1，LoRA rank 不合理。")

    # Capability ACL 檢查
    if config.capability_acl.default_role not in config.capability_acl.roles:
        warnings.append(
            f"⚠️ capability_acl.default_role='{config.capability_acl.default_role}' "
            f"不在 roles 中，未知角色將使用最嚴格權限。"
        )

    return warnings

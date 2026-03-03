"""
04_Engine — Model Router (NPU-Aware Hybrid Routing)
=====================================================
整合 SmartRouter + NPUDetector + EnsembleRouter 的統一入口。

路由邏輯：
  1. 偵測本機硬體 (NPU/GPU)
  2. 判斷任務複雜度
  3. 決定路由策略：
     - 簡單任務 + 有 NPU → 本地 Ollama
     - 複雜任務 → Cloud API
     - 高重要性 → Ensemble (多模型投票)
  4. 離線模式 → 強制本地

此模組取代直接使用 SmartRouter，提供更智慧的路由決策。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from .npu_detector import NPUDetector, HardwareProfile
except ImportError:
    try:
        from npu_detector import NPUDetector, HardwareProfile
    except ImportError:
        NPUDetector = None
        HardwareProfile = None

try:
    from .router import SmartRouter
except ImportError:
    from router import SmartRouter

try:
    from .ensemble_router import EnsembleRouter
except ImportError:
    try:
        from ensemble_router import EnsembleRouter
    except ImportError:
        EnsembleRouter = None


@dataclass
class RoutingDecision:
    """路由決策結果"""
    provider: str
    model: str
    base_url: Optional[str] = None
    strategy: str = "direct"     # "direct" | "local" | "ensemble"
    reason: str = ""
    hardware: str = "cloud"      # "cloud" | "mps" | "cuda" | "cpu"


class ModelRouter:
    """
    NPU-Aware Hybrid Model Router。
    
    整合硬體偵測、任務複雜度分析和成本優化，
    提供智慧的模型路由決策。
    
    Args:
        config: AgentOSConfig 實例
        gateway: APIGateway 實例 (用於 Ensemble)
    """

    def __init__(self, config: Any, gateway: Any = None):
        self._config = config
        self._smart_router = SmartRouter(config)
        self._hardware: Optional[Any] = None
        self._ensemble: Optional[Any] = None

        # 偵測硬體
        if NPUDetector:
            try:
                self._hardware = NPUDetector.detect()
                logger.info(
                    f"🔧 ModelRouter: 硬體={self._hardware.recommended_local_backend}, "
                    f"accelerators={self._hardware.accelerators}"
                )
            except Exception as e:
                logger.warning(f"⚠️ NPU 偵測失敗: {e}")

        # 初始化 Ensemble
        if EnsembleRouter and gateway:
            self._ensemble = EnsembleRouter(gateway)
            logger.info("🎯 ModelRouter: Ensemble 可用")

        # 本地 Ollama 端點快取
        self._local_provider = self._find_local_provider()

    def route(
        self,
        agent_id: str = "default",
        messages: Optional[List[Dict]] = None,
        tools: Optional[List[Dict]] = None,
        importance: float = 0.5,
    ) -> RoutingDecision:
        """
        智慧路由決策。
        
        Args:
            agent_id: Agent ID
            messages: 對話訊息
            tools: 工具定義
            importance: 任務重要性 (0.0~1.0)
            
        Returns:
            RoutingDecision
        """
        messages = messages or []
        
        # 1. 離線模式 → 強制本地
        if self._smart_router._offline_mode:
            return self._route_local("offline mode — 強制本地推論")

        # 2. 判斷複雜度
        complexity = self._smart_router.determine_complexity(messages, tools)

        # 3. 高重要性 + Ensemble 可用 → 多模型投票
        if importance >= 0.8 and self._ensemble:
            provider, model, base_url = self._smart_router.route(agent_id, messages, tools)
            return RoutingDecision(
                provider=provider,
                model=model,
                base_url=base_url,
                strategy="ensemble",
                reason=f"importance={importance:.1f} → Ensemble 多模型投票",
                hardware="cloud",
            )

        # 4. 簡單任務 + 有本地 NPU → Ollama
        npu_available = (
            self._hardware
            and self._hardware.recommended_local_backend != "cpu"
            and self._local_provider
        )
        
        npu_config = getattr(self._config, 'npu', None)
        prefer_local = npu_config and npu_config.prefer_local_inference

        if complexity == "simple" and npu_available and prefer_local:
            return self._route_local(
                f"simple task + NPU ({self._hardware.recommended_local_backend}) → 本地推論"
            )

        # 5. 預設：Cloud API (由 SmartRouter 決定)
        provider, model, base_url = self._smart_router.route(agent_id, messages, tools)
        return RoutingDecision(
            provider=provider,
            model=model,
            base_url=base_url,
            strategy="direct",
            reason=f"complexity={complexity} → Cloud API",
            hardware="cloud",
        )

    def _route_local(self, reason: str) -> RoutingDecision:
        """路由到本地 Ollama"""
        if self._local_provider:
            return RoutingDecision(
                provider=self._local_provider["name"],
                model=self._local_provider["model"],
                base_url=self._local_provider["base_url"],
                strategy="local",
                reason=reason,
                hardware=self._hardware.recommended_local_backend if self._hardware else "cpu",
            )
        # Fallback: 預設 Ollama
        return RoutingDecision(
            provider="ollama",
            model="llama3.2:3b",
            base_url="http://localhost:11434",
            strategy="local",
            reason=reason + " (default ollama)",
            hardware=self._hardware.recommended_local_backend if self._hardware else "cpu",
        )

    def _find_local_provider(self) -> Optional[Dict[str, str]]:
        """從 config 中找到本地推論 provider (Ollama/LMStudio)"""
        try:
            for p in self._config.gateway.providers:
                if p.name.lower() in ("ollama", "lmstudio", "local"):
                    return {
                        "name": p.name,
                        "model": p.models[0] if p.models else "llama3.2:3b",
                        "base_url": p.base_url or "http://localhost:11434",
                    }
        except Exception:
            pass
        return None

    @property
    def hardware_profile(self) -> Optional[Any]:
        """取得硬體偵測結果"""
        return self._hardware

    def set_offline_mode(self, offline: bool = True) -> None:
        """設定離線模式"""
        self._smart_router.set_offline_mode(offline)

import os
from typing import Dict

class FeatureFlags:
    """
    企業版功能切換閥 (Feature Flags)。
    提供開源與商業雙軌制的靈活切換，預設所有進階功能為關閉，需透過環境變數或 License 啟用。
    """

    _flags: Dict[str, bool] = {
        "ENABLE_SSO_OIDC": False,              # SSO 登入
        "ENABLE_ENTERPRISE_AUDIT": False,      # 企業級稽核日誌 (對接 Datadog/Splunk)
        "ENABLE_MULTI_TENANT": False,          # 多租戶隔離
        "ENABLE_REMOTE_DEBUGGER": False,       # 遠端單步除錯器
    }

    @classmethod
    def is_enabled(cls, feature_name: str) -> bool:
        """
        檢查某項企業功能是否啟用。
        會先讀取環境變數 `AGENTOS_FF_<FEATURE_NAME>`，若無則依賴預設值。
        """
        if feature_name not in cls._flags:
            return False
            
        env_val = os.getenv(f"AGENTOS_FF_{feature_name}")
        if env_val is not None:
            return env_val.lower() in ("true", "1", "yes")
            
        return cls._flags[feature_name]

    @classmethod
    def enable(cls, feature_name: str):
        if feature_name in cls._flags:
            cls._flags[feature_name] = True

    @classmethod
    def disable(cls, feature_name: str):
        if feature_name in cls._flags:
            cls._flags[feature_name] = False

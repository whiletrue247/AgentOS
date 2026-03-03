"""
Config — Secret Loader (KeyChain / .env / getpass)
====================================================
安全的 API Key 與密碼載入器。
優先順序：
  1. 環境變數（適合 CI/Docker）
  2. .env 檔案（python-dotenv）
  3. OS 原生金鑰鏈 (macOS Keychain / Windows Credential Manager / Linux Secret Service)
  4. getpass 互動式輸入（最後手段）

用於取代在 config.yaml 中明文存放 API Key 的不安全做法。
"""

from __future__ import annotations

import getpass
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# 載入 .env
try:
    from dotenv import load_dotenv
    load_dotenv()
    _DOTENV_LOADED = True
except ImportError:
    _DOTENV_LOADED = False

# keyring (OS 金鑰鏈)
try:
    import keyring
    _KEYRING_AVAILABLE = True
except ImportError:
    _KEYRING_AVAILABLE = False


_SERVICE_NAME = "agentos"


def get_secret(
    key: str,
    prompt: Optional[str] = None,
    allow_getpass: bool = True,
) -> str:
    """
    按優先順序取得機密值：
      1. 環境變數 (e.g., OPENAI_API_KEY)
      2. OS 金鑰鏈 (macOS Keychain / Windows Credential)
      3. getpass 互動式輸入
    
    Args:
        key: 環境變數名稱 / keyring key
        prompt: getpass 提示文字 (預設: "Enter {key}: ")
        allow_getpass: 是否允許互動式輸入
        
    Returns:
        secret 值，若所有來源都失敗則回傳空字串
    """
    # 1. 環境變數 (含 .env)
    value = os.environ.get(key, "")
    if value:
        logger.debug(f"🔑 Secret '{key}' loaded from environment")
        return value

    # 2. OS Keyring
    if _KEYRING_AVAILABLE:
        try:
            value = keyring.get_password(_SERVICE_NAME, key)
            if value:
                logger.debug(f"🔑 Secret '{key}' loaded from OS keyring")
                return value
        except Exception as e:
            logger.debug(f"⚠️ Keyring lookup failed for '{key}': {e}")

    # 3. getpass (互動式)
    if allow_getpass:
        import sys
        if sys.stdin.isatty():
            prompt_text = prompt or f"Enter {key}: "
            try:
                value = getpass.getpass(prompt_text)
                if value:
                    # 自動存入 keyring 供下次使用
                    save_secret(key, value)
                    return value
            except (KeyboardInterrupt, EOFError):
                pass

    logger.warning(f"⚠️ Secret '{key}' not found in any source")
    return ""


def save_secret(key: str, value: str) -> bool:
    """
    將機密存入 OS 金鑰鏈。
    
    Args:
        key: 金鑰名稱
        value: 機密值
        
    Returns:
        是否成功儲存
    """
    if not _KEYRING_AVAILABLE:
        logger.debug("ℹ️ keyring not available — secret not persisted")
        return False

    try:
        keyring.set_password(_SERVICE_NAME, key, value)
        logger.info(f"🔐 Secret '{key}' saved to OS keyring")
        return True
    except Exception as e:
        logger.warning(f"⚠️ Failed to save secret '{key}' to keyring: {e}")
        return False


def delete_secret(key: str) -> bool:
    """從 OS 金鑰鏈刪除機密"""
    if not _KEYRING_AVAILABLE:
        return False
    try:
        keyring.delete_password(_SERVICE_NAME, key)
        logger.info(f"🗑️ Secret '{key}' deleted from OS keyring")
        return True
    except Exception as e:
        logger.debug(f"⚠️ Failed to delete secret '{key}': {e}")
        return False


def load_provider_keys(providers: list) -> None:
    """
    為所有 Provider 載入 API Keys。
    遍歷 config 中的 providers，對 api_key 為空的 provider 嘗試從
    環境變數/keyring/getpass 載入。
    
    Args:
        providers: ProviderConfig 列表
    """
    key_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "groq": "GROQ_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "together": "TOGETHER_API_KEY",
        "cohere": "COHERE_API_KEY",
    }

    for p in providers:
        if p.api_key:
            continue  # 已有 key
        
        env_key = key_map.get(p.name.lower(), f"{p.name.upper()}_API_KEY")
        secret = get_secret(env_key, allow_getpass=False)
        if secret:
            p.api_key = secret
            logger.info(f"🔑 {p.name} API key loaded from secure source")

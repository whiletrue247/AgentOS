"""
onboarding/wizard.py
====================
首次啟動引導精靈。
如果系統偵測到 config.yaml 不存在或缺少必要設定，自動跳出互動式 CLI，
引導使用者：
  1. 選擇 AI 模型 (OpenAI / Anthropic / Local)
  2. 輸入 API Key
  3. 產生初始 SOUL.md
  4. 設定通訊方式 (Terminal / Telegram)
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Any

from config_schema import AgentOSConfig

# Defaults for generating a fresh config
DEFAULT_CONFIG_PATH = Path("config.yaml")

class OnboardingWizard:
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config_data: dict[str, Any] = {
            "version": "1.0",
            "gateway": {
                "providers": [],
                "agents": {"default": "openai/gpt-4o"}
            },
            "engine": {
                "watchdog": {"max_steps": 50},
                "retry": {"max_attempts": 3, "backoff_multiplier": 2.0, "retryable_codes": [429, 500, 502, 503]}
            },
            "budget": {
                "daily_limit_m": 1.0
            },
            "sandbox": {
                "type": "subprocess",
                "network_access": True,
                "timeout_seconds": 30
            },
            "truncation": {
                "max_tokens": 10000,
                "head_ratio": 0.3,
                "tail_ratio": 0.7
            },
            "dashboard": {
                "enabled": True,
                "port": 8080
            },
            "messenger": {
                "telegram": {"bot_token": ""}
            }
        }

    def run(self) -> bool:
        """執行首次啟動精靈"""
        if self.config_path.exists():
            return False # 表示不需執行或已經存在
            
        print("\n" + "="*50)
        print("🚀 歡迎使用 AgentOS (v4.0) 🚀")
        print("系統偵測到您是首次啟動，讓我們進行快速設定。")
        print("="*50 + "\n")

        self.step_1_model_selection()
        self.step_2_soul_generation()
        self.step_3_messenger()
        
        self.save_config()
        
        print("\n🎉 設定完成！正在啟動 AgentOS...\n")
        return True

    def step_1_model_selection(self):
        print("Step 1/4 — 選擇主要驅動模型")
        print("  [1] OpenAI (推薦，最穩定通用)")
        print("  [2] Anthropic (適合寫程式)")
        print("  [3] 本地 Ollama (免費，無需網路，需先安裝)")
        
        while True:
            choice = input("👉 請選擇 [1-3]: ").strip()
            if choice == "1":
                self.setup_openai()
                break
            elif choice == "2":
                self.setup_anthropic()
                break
            elif choice == "3":
                self.setup_ollama()
                break
            else:
                print("❌ 請輸入 1 或 2 或 3")

    def setup_openai(self):
        print("\n🔗 https://platform.openai.com/api-keys")
        api_key = input("🔑 請輸入您的 OpenAI API Key (sk-...): ").strip()
        provider = {
            "name": "openai",
            "api_key": api_key,
            "models": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
        }
        self.config_data["gateway"]["providers"].append(provider)
        self.config_data["gateway"]["agents"]["default"] = "openai/gpt-4o"

    def setup_anthropic(self):
        print("\n🔗 https://console.anthropic.com/settings/keys")
        api_key = input("🔑 請輸入您的 Anthropic API Key (sk-ant-...): ").strip()
        provider = {
            "name": "anthropic",
            "api_key": api_key,
            "models": ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"]
        }
        self.config_data["gateway"]["providers"].append(provider)
        self.config_data["gateway"]["agents"]["default"] = "anthropic/claude-3-sonnet"

    def setup_ollama(self):
        print("\n確保您已經在本地運行 `ollama serve`")
        url = input("🌐 請輸入 Ollama Base URL (預設: http://localhost:11434): ").strip()
        if not url:
            url = "http://localhost:11434"
            
        model = input("🤖 請輸入您想使用的模型名稱 (預設: llama3): ").strip()
        if not model:
            model = "llama3"
            
        provider = {
            "name": "ollama",
            "api_key": "",
            "base_url": url,
            "models": [model]
        }
        self.config_data["gateway"]["providers"].append(provider)
        self.config_data["gateway"]["agents"]["default"] = f"ollama/{model}"

    def step_2_soul_generation(self):
        print("\nStep 2/4 — 定義 AI 靈魂 (SOUL) 📝")
        print("您可以稍後在 Dashboard 修改，但現在我們需要一個基礎。")
        choice = input("是否要建立基礎的 SOUL.md? [Y/n]: ").strip().lower()
        
        soul_path = Path("SOUL.md")
        if choice != 'n':
            if not soul_path.exists():
                default_soul = """# Default Agent
A general-purpose AI assistant powered by AgentOS.

## 🎯 核心目標 (Core Objectives)
- Help the user answer questions and solve problems.
- Execute tools safely and report the results.

## 📜 行為準則 (Rules & Guidelines)
- Be concise and direct.
- If you are unsure, ask the user.

## 🛠️ 預設技能 (Default Skills)
- file reading/writing
- web searching
"""
                soul_path.write_text(default_soul, encoding="utf-8")
                print("✅ 已產生預設的 SOUL.md")
        else:
            print("⏭️ 跳過 SOUL 產生。")

    def step_3_messenger(self):
        print("\nStep 3/4 — 選擇通訊方式 💬")
        print("  [1] 僅 Terminal (終端機直接對白)")
        print("  [2] Telegram Bot (遠端控制)")
        
        while True:
            choice = input("👉 請選擇 [1-2]: ").strip()
            if choice == "1":
                print("✅ 將使用 Terminal 互動。")
                break
            elif choice == "2":
                print("\n🔗 請找 @BotFather 建立機器人並取得 Token")
                token = input("🤖 請輸入 Telegram Bot Token: ").strip()
                self.config_data["messenger"]["telegram"]["bot_token"] = token
                break
            else:
                print("❌ 請輸入 1 或 2")

    def save_config(self):
        print("\nStep 4/4 — 儲存設定 💾")
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.config_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            print(f"✅ 設定檔已儲存至 {self.config_path}")
        except Exception as e:
            print(f"❌ 儲存設定失敗: {e}")
            sys.exit(1)

def check_and_run_wizard():
    """主程式呼叫的入口點"""
    # 簡單偵測 config.yaml 是否存在
    if not Path("config.yaml").exists():
        wizard = OnboardingWizard()
        wizard.run()

if __name__ == "__main__":
    check_and_run_wizard()

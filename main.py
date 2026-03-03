#!/usr/bin/env python3
"""
AgentOS — main.py
=================
一鍵啟動腳本。將所有核心模組 + 平台層串接在一起：

  01_Kernel (SOUL.md)
    ↓ System Prompt
  04_Engine (心臟)
    ├── Gateway  ← API 路由 + Key 注入
    ├── RateLimiter ← Token Bucket 節流
    ├── CostGuard ← 預算守衛
    ├── StateMachine ← 任務狀態 + Checkpoint
    ├── 02_Memory (MemoryManager + SQLite Provider)
    └── 03_Tool_System (ToolCatalog + SysTools + Sandbox + Truncator)
  Platform
    ├── Messenger (Telegram Bot)
    └── Dashboard (Web Panel)

用法：
  python main.py                # 首次執行會觸發 Onboarding Wizard
  python main.py --terminal     # 強制使用 Terminal 模式 (跳過 Telegram)
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import sys
from pathlib import Path

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-25s │ %(levelname)-5s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("AgentOS")


# ============================================================
# Conversation Persistence (SQLite)
# ============================================================
_CONV_DB_PATH = Path("data/conversation_history.db")


def _init_conversation_db() -> None:
    """初始化對話歷史資料庫"""
    _CONV_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_CONV_DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.commit()


def _load_conversation_history() -> list[dict]:
    """從 SQLite 載入對話歷史"""
    if not _CONV_DB_PATH.exists():
        return []
    with sqlite3.connect(str(_CONV_DB_PATH)) as conn:
        rows = conn.execute(
            "SELECT role, content FROM history ORDER BY id"
        ).fetchall()
    return [{"role": r, "content": c} for r, c in rows]


def _append_conversation(role: str, content: str) -> None:
    """追加一筆對話紀錄"""
    with sqlite3.connect(str(_CONV_DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO history (role, content) VALUES (?, ?)",
            (role, content),
        )
        conn.commit()


def _clear_conversation_history() -> None:
    """清除對話歷史"""
    with sqlite3.connect(str(_CONV_DB_PATH)) as conn:
        conn.execute("DELETE FROM history")
        conn.commit()


async def boot() -> None:
    """AgentOS 啟動程序"""

    logger.info("=" * 50)
    logger.info("🚀 AgentOS v4.0 啟動中...")
    logger.info("=" * 50)

    # ── Step 0: Onboarding ──────────────────────────
    from onboarding.wizard import check_and_run_wizard
    check_and_run_wizard()

    # ── Step 1: 載入設定 ────────────────────────────
    from config_schema import load_config, validate_config
    config = load_config()
    warnings = validate_config(config)
    for w in warnings:
        logger.warning(w)
    logger.info("✅ Config 已載入")

    # ── Step 2: 靈魂載入 (01_Kernel) ────────────────
    from importlib import import_module
    kernel_mod = import_module("01_Kernel.kernel")
    kernel = kernel_mod.Kernel(config.kernel)
    soul_content = kernel.load_soul()
    logger.info(f"✅ SOUL 已載入 ({len(soul_content)} chars)")

    # ── Step 3: 記憶系統 (02_Memory) ────────────────
    memory_mod = import_module("02_Memory.memory_manager")
    sqlite_mod = import_module("02_Memory.providers.sqlite")

    sqlite_provider = sqlite_mod.SQLiteMemoryProvider()
    memory_manager = memory_mod.MemoryManager(provider=sqlite_provider)
    logger.info("✅ Memory 已啟動 (SQLite)")

    # ── Step 4: 工具系統 (03_Tool_System) ───────────
    catalog_mod = import_module("03_Tool_System.catalog")
    sys_tools_mod = import_module("03_Tool_System.sys_tools")
    sandbox_module = import_module("03_Tool_System.sandbox")
    subprocess_mod = import_module("03_Tool_System.sandbox_subprocess")
    docker_mod = import_module("03_Tool_System.sandbox_docker")
    truncator_mod = import_module("03_Tool_System.truncator")

    tool_catalog = catalog_mod.ToolCatalog(config=config)
    sys_tools_mod.register_system_tools(tool_catalog)

    # 偵測是否有裝 Docker
    import subprocess
    has_docker = False
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        has_docker = True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    if has_docker:
        logger.info("🐳 檢測到 Docker，啟用強隔離 DockerSandbox")
        sandbox_provider = docker_mod.DockerSandbox(
            work_dir="./data/sandbox_workspace",
            docker_runtime=config.sandbox.docker_runtime
        )
    else:
        logger.warning("⚠️ 找不到 Docker，降級使用零隔離 SubprocessSandbox")
        sandbox_provider = subprocess_mod.SubprocessSandbox(work_dir="./data/sandbox_workspace")
        
    sandbox_manager = sandbox_module.SandboxManager(config=config, provider=sandbox_provider)
    truncator = truncator_mod.Truncator(config=config)

    # 對話歷史持久化初始化
    _init_conversation_db()

    logger.info(f"✅ 工具系統已啟動 ({len(tool_catalog.get_all_tools())} 工具)")

    # ── Step 5: 引擎核心 (04_Engine) ────────────────
    engine_mod = import_module("04_Engine.engine")
    gateway_mod = import_module("04_Engine.gateway")
    rate_mod = import_module("04_Engine.rate_limiter")
    cost_mod = import_module("04_Engine.cost_guard")
    state_mod = import_module("04_Engine.state_machine")

    gateway = gateway_mod.APIGateway(config)
    rate_limiter = rate_mod.RateLimiter(
        rpm=config.engine.rate_limit.rpm,
        tpm=config.engine.rate_limit.tpm,
    )
    cost_guard = cost_mod.CostGuard(config)
    state_mod.StateMachine()

    engine = engine_mod.Engine(config)

    # ── 工具執行回調 ──
    async def tool_executor(req):
        """Engine 呼叫工具的回調"""
        from contracts.interfaces import ToolCallResult

        tool_schema = tool_catalog.get_tool(req.tool_name)
        if not tool_schema:
            return ToolCallResult(
                tool_name=req.tool_name,
                success=False, output="",
                error=f"Tool '{req.tool_name}' not found in catalog.",
            )

        # 如果工具有 execute 邏輯 (local_plugin)，用 sandbox 執行
        try:
            result = await sandbox_manager.execute(
                tool_name=req.tool_name,
                arguments=req.arguments,
            )
            # 截斷過長輸出
            output = truncator.truncate(result.output) if result.output else ""
            return ToolCallResult(
                tool_name=req.tool_name,
                success=result.success,
                output=output,
                error=result.error,
            )
        except Exception as e:
            return ToolCallResult(
                tool_name=req.tool_name,
                success=False, output="",
                error=str(e),
            )

    # ── 注入所有子模組到 Engine ──
    engine.inject(
        gateway=gateway,
        rate_limiter=rate_limiter,
        tool_executor=tool_executor,
        memory_manager=memory_manager,
        soul_content=soul_content,
    )
    logger.info("✅ Engine 已啟動 (ReAct Loop Ready)")

    # ── Step 6: 是否啟動 Telegram? ─────────────────
    use_terminal = "--terminal" in sys.argv

    if not use_terminal and config.messenger.telegram.bot_token:
        try:
            tg_mod = import_module("platform.messenger_telegram")
            tg_bot = tg_mod.TelegramMessenger(config=config, engine=engine)
            await tg_bot.start()
            logger.info("✅ Telegram Bot 已啟動")
        except ImportError:
            logger.warning("⚠️ python-telegram-bot 未安裝，改用 Terminal 模式")
            use_terminal = True
        except Exception as e:
            logger.warning(f"⚠️ Telegram 啟動失敗: {e}，改用 Terminal 模式")
            use_terminal = True
    else:
        use_terminal = True

    # ── Step 7: Terminal 互動模式 ───────────────────
    if use_terminal:
        logger.info("🖥️  Terminal 模式啟動。輸入 /quit 結束。")
        print("\n" + "=" * 50)
        print("🤖 AgentOS 已就緒！請輸入您的指令：")
        print("=" * 50 + "\n")

        # 從 SQLite 載入上次的對話歷史
        conversation_history = _load_conversation_history()
        if conversation_history:
            logger.info(f"📂 已恢復 {len(conversation_history)} 筆對話歷史")

        while True:
            try:
                user_input = await asyncio.to_thread(input, "You > ")
            except (EOFError, KeyboardInterrupt):
                break

            if user_input.strip().lower() in ("/quit", "/exit", "exit", "quit"):
                break

            if user_input.strip().lower() == "/clear":
                conversation_history.clear()
                _clear_conversation_history()
                print("🧹 對話歷史已清除。\n")
                continue

            if user_input.strip().lower() == "/cost":
                report = cost_guard.get_report()
                print(f"📊 今日: {report.daily_m:.4f}M / {report.daily_limit_m:.1f}M ({report.budget_remaining_pct:.1f}% left)")
                print(f"   呼叫次數: {report.calls_today}\n")
                continue

            # 預算檢查
            can_go, budget_msg = cost_guard.check_budget()
            if not can_go:
                print(f"\n{budget_msg}\n")
                continue

            # 持久化使用者訊息
            _append_conversation("user", user_input)

            # 呼叫 Engine
            print()
            reply = await engine.handle_message(
                user_message=user_input,
                agent_id="default",
                conversation_history=conversation_history,
            )

            # 持久化 Agent 回覆
            _append_conversation("assistant", reply)

            # 同步 Cost Guard
            cost_guard.record_from_gateway(gateway)

            print(f"\n🤖 Agent > {reply}\n")
    else:
        logger.info("✅ 系統已將 Telegram 置於背景運行。按 Ctrl+C 結束。")
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass


async def _shutdown(
    cost_guard=None,
    sandbox_manager=None,
    sandbox_provider=None,
):
    """Graceful shutdown: 確保所有資源釋放"""
    if cost_guard:
        try:
            cost_guard.save()
            logger.info("💾 Cost Guard 已保存")
        except Exception as e:
            logger.error(f"❌ Cost Guard 保存失敗: {e}")

    if sandbox_provider:
        try:
            await sandbox_provider.cleanup()
            logger.info("🧹 Sandbox 已清理")
        except Exception as e:
            logger.error(f"❌ Sandbox 清理失敗: {e}")

    logger.info("👋 AgentOS 已關閉。")


def main():
    try:
        asyncio.run(boot())
    except KeyboardInterrupt:
        logger.info("👋 收到 Ctrl+C，AgentOS 關閉。")
    except asyncio.CancelledError:
        logger.info("👋 收到取消信號，AgentOS 關閉。")


if __name__ == "__main__":
    main()

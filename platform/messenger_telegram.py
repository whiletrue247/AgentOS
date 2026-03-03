"""
platform/messenger_telegram.py
==============================
Telegram Bot 整合，作為 AgentOS 的前台介面。
負責接收使用者訊息、維護對話歷史，並呼叫 Engine 執行，最後回傳結果。
支援 streaming 更新狀態 (透過 EngineEvent)。

對話歷史持久化至 SQLite，按 chat_id 隔離。
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config_schema import AgentOSConfig
from contracts.interfaces import EngineEvent, EventType

logger = logging.getLogger(__name__)

# ============================================================
# Telegram Conversation Persistence (SQLite)
# ============================================================
_TG_CONV_DB_PATH = Path("data/tg_conversation_history.db")


def _tg_init_db() -> None:
    """初始化 Telegram 對話歷史資料庫"""
    _TG_CONV_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_TG_CONV_DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tg_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL DEFAULT (strftime('%s','now'))
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tg_history_chat_id
            ON tg_history (chat_id)
        """)
        conn.commit()


def _tg_load_history(chat_id: int) -> list[dict]:
    """從 SQLite 載入指定 chat_id 的對話歷史"""
    if not _TG_CONV_DB_PATH.exists():
        return []
    with sqlite3.connect(str(_TG_CONV_DB_PATH)) as conn:
        rows = conn.execute(
            "SELECT role, content FROM tg_history WHERE chat_id = ? ORDER BY id",
            (chat_id,),
        ).fetchall()
    return [{"role": r, "content": c} for r, c in rows]


def _tg_append(chat_id: int, role: str, content: str) -> None:
    """追加一筆 Telegram 對話紀錄"""
    with sqlite3.connect(str(_TG_CONV_DB_PATH)) as conn:
        conn.execute(
            "INSERT INTO tg_history (chat_id, role, content) VALUES (?, ?, ?)",
            (chat_id, role, content),
        )
        conn.commit()


def _tg_clear_history(chat_id: int) -> None:
    """清除指定 chat_id 的對話歷史"""
    with sqlite3.connect(str(_TG_CONV_DB_PATH)) as conn:
        conn.execute("DELETE FROM tg_history WHERE chat_id = ?", (chat_id,))
        conn.commit()


class TelegramMessenger:
    """
    Telegram Bot 前端介面
    """
    def __init__(self, config: AgentOSConfig, engine):
        self.config = config
        self.engine = engine
        self.app: Optional[Application] = None
        self._histories: dict[int, list[dict]] = {}  # chat_id -> messages (in-memory cache)

        # 初始化 Telegram 對話歷史 DB
        _tg_init_db()

        # 訂閱 Engine 事件以提供即時反饋
        self.engine.on(EventType.TOOL_CALL, self._on_tool_call)
        
        # 暫存 chat_id 以備廣播或事件推送用
        self._active_chats: set[int] = set()

    async def start(self) -> None:
        """啟動 Telegram Bot Polling"""
        token = self.config.messenger.telegram.bot_token
        if not token:
            logger.warning("⚠️ 未設定 Telegram Bot Token，跳過啟動 Telegram 模組")
            return
            
        try:
            self.app = Application.builder().token(token).build()
            
            # 手動初始化及啟動，適用於已經在 asyncio event loop 下運行的環境
            await self.app.initialize()
            
            # 註冊 Handlers
            self.app.add_handler(CommandHandler("start", self._start_cmd))
            self.app.add_handler(CommandHandler("clear", self._clear_cmd))
            self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
            
            await self.app.start()
            await self.app.updater.start_polling()
            logger.info("🚀 Telegram Bot 已啟動")
            
        except ImportError:
            logger.error("❌ 缺少 'python-telegram-bot' 套件。請執行: pip install python-telegram-bot")
        except Exception as e:
            logger.error(f"❌ Telegram 啟動失敗: {e}")

    async def stop(self) -> None:
        """停止 Telegram Bot"""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("🛑 Telegram Bot 已停止")

    # ========================================
    # 事件處理
    # ========================================

    async def _on_tool_call(self, event: EngineEvent) -> None:
        """當 Agent 呼叫工具時發送提示訊息"""
        # 注意：這裡的事件是全局的，理想狀態下 payload 應該帶有 session_id/chat_id。
        # 此處採用簡單廣播給最近互動過的活躍聊天室。
        tool_name = event.payload.get("tool_name", "unknown_tool")
        msg = f"🔧 執行工具中: `{tool_name}`..."
        
        if self.app and self.app.bot:
            for chat_id in self._active_chats:
                try:
                    await self.app.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
                except Exception as e:
                    logger.debug(f"Failed to send tool alert to {chat_id}: {e}")

    # ========================================
    # Telegram Handlers
    # ========================================

    async def _start_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        self._active_chats.add(chat_id)
        # 從 SQLite 恢復該 chat 的對話歷史
        self._histories[chat_id] = _tg_load_history(chat_id)
        restored = len(self._histories[chat_id])
        welcome_msg = "👋 歡迎使用 AgentOS！我是您的私人 AI 助理。\n\n您可直接與我對話，或傳送 /clear 來清除我的記憶。"
        if restored:
            welcome_msg += f"\n\n📂 已恢復 {restored} 筆對話歷史。"
        await update.message.reply_text(welcome_msg)
        logger.info(f"💬 [Telegram] New user started: {chat_id} (restored {restored} messages)")

    async def _clear_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = update.effective_chat.id
        self._histories[chat_id] = []
        _tg_clear_history(chat_id)
        await update.message.reply_text("🧹 您的對話歷史已清除。")
        logger.info(f"💬 [Telegram] Chat cleared: {chat_id}")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id
        user_text = update.message.text
        self._active_chats.add(chat_id)

        if chat_id not in self._histories:
            # 首次收到訊息時從 DB 恢復歷史
            self._histories[chat_id] = _tg_load_history(chat_id)

        logger.info(f"📨 [Telegram] 收到來自 {chat_id} 的訊息: {user_text[:20]}...")

        # 持久化使用者訊息
        _tg_append(chat_id, "user", user_text)

        # 顯示輸入中狀態
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        
        try:
            # 呼叫 Core Engine 處理訊息
            agent_id = f"tg_{chat_id}"
            
            reply_text = await self.engine.handle_message(
                user_message=user_text,
                agent_id=agent_id,
                conversation_history=self._histories[chat_id]
            )

            # 持久化 Agent 回覆
            _tg_append(chat_id, "assistant", reply_text)

            # 將回應切分為符合 Telegram 長度限制 (4096)
            await self._send_long_message(context.bot, chat_id, reply_text)
            
        except Exception as e:
            logger.error(f"❌ 處理 Telegram 訊息時發生錯誤: {e}", exc_info=True)
            await update.message.reply_text(f"⚠️ 抱歉，系統內部發生錯誤: {str(e)[:100]}")

    async def _send_long_message(self, bot, chat_id: int, text: str) -> None:
        """分批發送長文本訊息"""
        max_len = 4000
        # 考慮到可能回傳空字串的狀況
        if not text:
            await bot.send_message(chat_id=chat_id, text="[空回覆]")
            return

        for i in range(0, len(text), max_len):
            chunk = text[i:i+max_len]
            # 簡單預防 markdown parse 錯誤而發不出去，預設不啟用嚴格 ParseMode
            await bot.send_message(chat_id=chat_id, text=chunk)

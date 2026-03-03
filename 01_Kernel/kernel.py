"""
01_Kernel — 靈魂載入器
======================
負責在 OS 啟動時載入 SOUL.md，作為 Agent 的核心 System Prompt。
依據 OS 中立原則，此模組「不解析」SOUL.md 的內部結構，僅作為純文字載入。

v5.0 新增：SOUL 版本控制
  - 每次載入時計算 SHA-256
  - 與上次版本比較，若有變化則記錄版本歷史到 data/soul_versions/
  - 提供 diff 回顧功能
"""

import difflib
import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from contracts.interfaces import KernelConfig

logger = logging.getLogger(__name__)

# SOUL 版本歷史目錄
_SOUL_VERSIONS_DIR = Path("data/soul_versions")
_SOUL_META_FILE = _SOUL_VERSIONS_DIR / "meta.json"


class Kernel:
    def __init__(self, config: Optional[KernelConfig] = None):
        self.config = config or KernelConfig()
        self._last_hash: str = ""

    def load_soul(self) -> str:
        """
        從路徑讀取 SOUL.md，並自動進行版本控制。
        """
        soul_path = Path(self.config.soul_path)

        if not soul_path.exists():
            default_prompt = "You are a helpful AI Agent. (SOUL.md not found)"
            logger.warning(f"⚠️ 找不到 SOUL.md (預期路徑: {soul_path.absolute()})。使用預設 Prompt。")
            self.config.soul_content = default_prompt
            return default_prompt

        try:
            with open(soul_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    logger.warning("⚠️ SOUL.md 為空。")
                    content = "You are a helpful AI Agent."
                    
                # 防禦: 超長 SOUL.md 保護 (上限 10 萬字元，約 2-3 萬 tokens)
                MAX_SOUL_LEN = 100_000
                if len(content) > MAX_SOUL_LEN:
                    logger.error(
                        f"🚨 SOUL.md 超過長度限制 ({len(content)} > {MAX_SOUL_LEN} chars)！"
                        f"為避免 Context Window 爆炸，已自動截斷結尾。"
                    )
                    content = content[:MAX_SOUL_LEN] + "\n\n...[SOUL TRUNCATED DUE TO EXCESSIVE LENGTH]..."

                # 版本控制
                self._track_version(content, soul_path)

                self.config.soul_content = content
                return content
        except Exception as e:
            logger.error(f"❌ 讀取 SOUL.md 失敗: {e}")
            self.config.soul_content = "You are a helpful AI Agent."
            return self.config.soul_content

    def get_system_prompt(self) -> str:
        """
        取得最終要注入到大模型 System Prompt 的文本。
        """
        if not self.config.soul_content:
            self.load_soul()
        return self.config.soul_content

    # ========================================
    # SOUL 版本控制
    # ========================================

    def _track_version(self, content: str, soul_path: Path) -> None:
        """追蹤 SOUL.md 的版本變化"""
        current_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self._last_hash = current_hash

        # 初始化版本目錄
        _SOUL_VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

        # 載入 metadata
        meta = self._load_meta()
        last_hash = meta.get("last_hash", "")

        if current_hash == last_hash:
            logger.debug("🔒 SOUL.md 未變更")
            return

        # 有變更！記錄新版本
        version_num = meta.get("version_count", 0) + 1
        timestamp = datetime.now().isoformat()

        # 備份當前版本
        backup_name = f"SOUL_v{version_num}_{current_hash[:8]}.md"
        backup_path = _SOUL_VERSIONS_DIR / backup_name
        shutil.copy2(soul_path, backup_path)

        # 生成 diff (如果有前一版)
        diff_text = ""
        if last_hash and meta.get("last_backup"):
            last_backup = _SOUL_VERSIONS_DIR / meta["last_backup"]
            if last_backup.exists():
                old_lines = last_backup.read_text(encoding="utf-8").splitlines(keepends=True)
                new_lines = content.splitlines(keepends=True)
                diff_text = "".join(difflib.unified_diff(
                    old_lines, new_lines,
                    fromfile=f"SOUL v{version_num - 1}",
                    tofile=f"SOUL v{version_num}",
                ))
                if diff_text:
                    diff_path = _SOUL_VERSIONS_DIR / f"diff_v{version_num - 1}_to_v{version_num}.txt"
                    diff_path.write_text(diff_text, encoding="utf-8")
                    logger.info(f"📝 SOUL diff 已儲存: {diff_path.name}")

        # 更新 metadata
        meta["last_hash"] = current_hash
        meta["last_backup"] = backup_name
        meta["version_count"] = version_num
        meta["last_updated"] = timestamp
        history = meta.get("history", [])
        history.append({
            "version": version_num,
            "hash": current_hash,
            "backup": backup_name,
            "timestamp": timestamp,
            "has_diff": bool(diff_text),
        })
        meta["history"] = history
        self._save_meta(meta)

        logger.info(
            f"📦 SOUL 版本更新: v{version_num} (hash: {current_hash[:12]}...)"
        )

    @staticmethod
    def _load_meta() -> dict:
        """載入 SOUL 版本 metadata"""
        if _SOUL_META_FILE.exists():
            try:
                return json.loads(_SOUL_META_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    @staticmethod
    def _save_meta(meta: dict) -> None:
        """儲存 SOUL 版本 metadata"""
        _SOUL_META_FILE.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_soul_hash(self) -> str:
        """取得當前 SOUL 的 SHA-256 hash"""
        return self._last_hash

    def get_version_history(self) -> list[dict]:
        """取得 SOUL 版本歷史"""
        meta = self._load_meta()
        return meta.get("history", [])


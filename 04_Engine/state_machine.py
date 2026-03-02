"""
04_Engine — 任務狀態機 + Checkpoint
===================================
追蹤每個任務的生命週期狀態。
支援 Checkpoint 機制：任務中斷後可從最近的 Checkpoint 恢復。

狀態流轉：
  PENDING → RUNNING → COMPLETED
                    → FAILED
                    → PAUSED (等待人類回覆)
                    → CANCELLED
"""

from __future__ import annotations

import enum
import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from paths import get_data_dir

logger = logging.getLogger(__name__)


class TaskState(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"         # 等待 SYS_ASK_HUMAN 回覆
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskRecord:
    """一個任務的完整紀錄"""
    task_id: str = ""
    description: str = ""
    state: str = "pending"
    agent_id: str = "default"

    # 時序
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # ReAct 進度
    current_step: int = 0
    max_steps: int = 50

    # Checkpoint: 保存對話歷史快照
    checkpoint_messages: list[dict] = field(default_factory=list)
    checkpoint_step: int = 0

    # 結果
    result: Optional[str] = None
    error: Optional[str] = None

    # 自由擴充
    metadata: dict[str, Any] = field(default_factory=dict)


class StateMachine:
    """任務狀態機"""

    def __init__(self, checkpoint_dir: Optional[str] = None):
        if checkpoint_dir is None:
            checkpoint_dir = str(get_data_dir() / "checkpoints")
        self._tasks: dict[str, TaskRecord] = {}
        self._checkpoint_dir = Path(checkpoint_dir)
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # ========================================
    # 生命週期
    # ========================================

    def create_task(self, description: str, agent_id: str = "default", max_steps: int = 50) -> TaskRecord:
        """建立新任務"""
        task = TaskRecord(
            task_id=str(uuid.uuid4())[:8],
            description=description,
            state=TaskState.PENDING.value,
            agent_id=agent_id,
            created_at=datetime.now().isoformat(),
            max_steps=max_steps,
        )
        self._tasks[task.task_id] = task
        logger.info(f"📋 任務建立: [{task.task_id}] {description}")
        return task

    def start(self, task_id: str) -> TaskRecord:
        task = self._get(task_id)
        task.state = TaskState.RUNNING.value
        task.started_at = datetime.now().isoformat()
        logger.info(f"▶️ 任務開始: [{task_id}]")
        return task

    def complete(self, task_id: str, result: str = "") -> TaskRecord:
        task = self._get(task_id)
        task.state = TaskState.COMPLETED.value
        task.completed_at = datetime.now().isoformat()
        task.result = result
        self._cleanup_checkpoint(task_id)
        logger.info(f"✅ 任務完成: [{task_id}]")
        return task

    def fail(self, task_id: str, error: str = "") -> TaskRecord:
        task = self._get(task_id)
        task.state = TaskState.FAILED.value
        task.completed_at = datetime.now().isoformat()
        task.error = error
        logger.error(f"❌ 任務失敗: [{task_id}] {error}")
        return task

    def pause(self, task_id: str) -> TaskRecord:
        """暫停任務（等待人類回覆）"""
        task = self._get(task_id)
        task.state = TaskState.PAUSED.value
        logger.info(f"⏸️ 任務暫停: [{task_id}] (waiting for human)")
        return task

    def resume(self, task_id: str) -> TaskRecord:
        """恢復暫停的任務"""
        task = self._get(task_id)
        task.state = TaskState.RUNNING.value
        logger.info(f"▶️ 任務恢復: [{task_id}]")
        return task

    def cancel(self, task_id: str) -> TaskRecord:
        task = self._get(task_id)
        task.state = TaskState.CANCELLED.value
        task.completed_at = datetime.now().isoformat()
        self._cleanup_checkpoint(task_id)
        logger.info(f"🚫 任務取消: [{task_id}]")
        return task

    def update_step(self, task_id: str, step: int) -> None:
        task = self._get(task_id)
        task.current_step = step

    # ========================================
    # Checkpoint
    # ========================================

    def save_checkpoint(self, task_id: str, messages: list[dict], step: int) -> None:
        """儲存對話歷史快照"""
        task = self._get(task_id)
        task.checkpoint_messages = messages
        task.checkpoint_step = step

        cp_path = self._checkpoint_dir / f"{task_id}.json"
        with open(cp_path, "w", encoding="utf-8") as f:
            json.dump({
                "task_id": task_id,
                "step": step,
                "messages": messages,
                "state": task.state,
            }, f, ensure_ascii=False, indent=2)

        logger.debug(f"💾 Checkpoint 已存: [{task_id}] step={step}")

    def load_checkpoint(self, task_id: str) -> Optional[dict]:
        """載入 Checkpoint"""
        cp_path = self._checkpoint_dir / f"{task_id}.json"
        if not cp_path.exists():
            return None

        with open(cp_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        logger.info(f"📂 Checkpoint 已載入: [{task_id}] step={data.get('step')}")
        return data

    def _cleanup_checkpoint(self, task_id: str) -> None:
        cp_path = self._checkpoint_dir / f"{task_id}.json"
        if cp_path.exists():
            cp_path.unlink()

    # ========================================
    # 查詢
    # ========================================

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        return self._tasks.get(task_id)

    def list_tasks(self, state: Optional[str] = None) -> list[TaskRecord]:
        tasks = list(self._tasks.values())
        if state:
            tasks = [t for t in tasks if t.state == state]
        return tasks

    def _get(self, task_id: str) -> TaskRecord:
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        return task

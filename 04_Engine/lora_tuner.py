"""
04_Engine — LoRA Tuner Scheduler (v5.0 SOTA)
===============================================
定期從使用者互動歷史 + KG 變更中擷取訓練資料，
觸發 PEFT/LoRA 微調以個人化本地模型。

支援：
  - Unsloth (4-bit QLoRA, 2x faster)
  - HuggingFace PEFT + transformers
  - 自動生成 Alpaca/ShareGPT 格式訓練集
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from typing import Dict, List

logger = logging.getLogger(__name__)

# 嘗試載入訓練框架
try:
    from peft import LoraConfig, get_peft_model
    PEFT_AVAILABLE = True
except ImportError:
    PEFT_AVAILABLE = False

try:
    from unsloth import FastLanguageModel
    UNSLOTH_AVAILABLE = True
except ImportError:
    UNSLOTH_AVAILABLE = False


class LoRATunerSchedule:
    """
    LoRA 微調排程器 (v5.0 SOTA)。
    定期從互動歷史擷取訓練資料，並觸發 PEFT/LoRA 微調。
    """

    def __init__(
        self,
        interval_hours: int = 24,
        data_dir: str = "data/lora",
        base_model: str = "unsloth/llama-3.2-3b-instruct-bnb-4bit",
    ):
        self.interval_hours = interval_hours
        self.data_dir = data_dir
        self.base_model = base_model
        self.is_running = False
        self.last_run = None
        self._task = None

        os.makedirs(data_dir, exist_ok=True)
        backend = "unsloth" if UNSLOTH_AVAILABLE else ("peft" if PEFT_AVAILABLE else "data-only")
        logger.info(f"🧬 LoRA Tuner: interval={interval_hours}h, backend={backend}")

    async def start(self):
        """啟動背景微調排程"""
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._tune_loop())
        logger.info("🔁 LoRA 定期微調背景任務啟動")

    async def stop(self):
        """停止排程"""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _tune_loop(self):
        while self.is_running:
            try:
                await self.trigger_tuning_job()
            except Exception as e:
                logger.error(f"❌ LoRA 微調失敗: {e}")
            await asyncio.sleep(self.interval_hours * 3600)

    # ----------------------------------------------------------
    # 主要工作流程
    # ----------------------------------------------------------
    async def trigger_tuning_job(self):
        """完整的微調工作流程：擷取→格式化→訓練→導出。"""
        self.last_run = datetime.datetime.now()
        logger.info("🔥 觸發 LoRA 微調...")

        # Step 1: 收集訓練資料
        dataset = await self._collect_training_data()
        if len(dataset) < 10:
            logger.info(f"ℹ️ 訓練資料不足 ({len(dataset)} 筆)，跳過本次微調")
            return

        # Step 2: 導出為 JSONL
        dataset_path = self._export_dataset(dataset)
        logger.info(f"📝 訓練集已導出: {dataset_path} ({len(dataset)} 筆)")

        # Step 3: 執行訓練
        if UNSLOTH_AVAILABLE:
            await self._train_unsloth(dataset_path)
        elif PEFT_AVAILABLE:
            await self._train_peft(dataset_path)
        else:
            logger.info("ℹ️ 無可用的訓練框架 (需要 unsloth 或 peft)，僅導出資料集")

    # ----------------------------------------------------------
    # 資料收集
    # ----------------------------------------------------------
    async def _collect_training_data(self) -> List[Dict[str, str]]:
        """從互動歷史和 KG 中擷取訓練樣本 (Alpaca 格式)。"""
        logger.info("📊 收集互動歷史...")

        # 讀取 daily_feedback 產生的 JSONL
        feedback_path = os.path.join(self.data_dir, "../feedback")
        samples = []

        if os.path.exists(feedback_path):
            for fname in os.listdir(feedback_path):
                if fname.endswith(".jsonl"):
                    filepath = os.path.join(feedback_path, fname)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    record = json.loads(line)
                                    # 轉為 Alpaca 格式
                                    sample = {
                                        "instruction": record.get("instruction", record.get("user_message", "")),
                                        "input": record.get("context", ""),
                                        "output": record.get("response", record.get("agent_response", "")),
                                    }
                                    if sample["instruction"] and sample["output"]:
                                        samples.append(sample)
                    except Exception as e:
                        logger.warning(f"⚠️ 讀取 {fname} 失敗: {e}")

        logger.info(f"📊 收集到 {len(samples)} 筆訓練樣本")
        return samples

    def _export_dataset(self, dataset: List[Dict[str, str]]) -> str:
        """導出為 JSONL 檔案。"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.data_dir, f"train_{timestamp}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for sample in dataset:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        return path

    # ----------------------------------------------------------
    # Unsloth 訓練 (推薦: 4-bit QLoRA, 2x faster)
    # ----------------------------------------------------------
    async def _train_unsloth(self, dataset_path: str):
        """使用 Unsloth 進行 4-bit QLoRA 微調。"""
        logger.info(f"🚀 Unsloth QLoRA 訓練: model={self.base_model}")

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=self.base_model,
            max_seq_length=2048,
            load_in_4bit=True,
        )

        model = FastLanguageModel.get_peft_model(
            model,
            r=16,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                            "gate_proj", "up_proj", "down_proj"],
            lora_alpha=16,
            lora_dropout=0,
            use_gradient_checkpointing="unsloth",
        )

        # 載入資料集
        from datasets import load_dataset
        dataset = load_dataset("json", data_files=dataset_path, split="train")

        from trl import SFTTrainer
        from transformers import TrainingArguments

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            args=TrainingArguments(
                output_dir=os.path.join(self.data_dir, "checkpoints"),
                per_device_train_batch_size=2,
                gradient_accumulation_steps=4,
                warmup_steps=5,
                max_steps=60,
                learning_rate=2e-4,
                fp16=True,
                logging_steps=1,
                save_strategy="no",
            ),
        )

        trainer.train()

        # 導出 adapter
        adapter_path = os.path.join(self.data_dir, "adapter_latest")
        model.save_pretrained(adapter_path)
        tokenizer.save_pretrained(adapter_path)
        logger.info(f"✅ LoRA adapter 已保存: {adapter_path}")

    # ----------------------------------------------------------
    # HuggingFace PEFT 訓練 (fallback)
    # ----------------------------------------------------------
    async def _train_peft(self, dataset_path: str):
        """使用 HuggingFace PEFT 進行 LoRA 微調。"""
        logger.info(f"🚀 PEFT LoRA 訓練: model={self.base_model}")

        from transformers import AutoModelForCausalLM, AutoTokenizer

        AutoTokenizer.from_pretrained(self.base_model)
        model = AutoModelForCausalLM.from_pretrained(self.base_model, load_in_4bit=True)

        config = LoraConfig(
            r=16, lora_alpha=32, lora_dropout=0.05,
            target_modules=["q_proj", "v_proj"],
            task_type="CAUSAL_LM",
        )
        model = get_peft_model(model, config)

        logger.info(f"📊 Trainable params: {model.print_trainable_parameters()}")

        # 實際訓練需要 datasets + trl，這裡記錄路徑供外部使用
        adapter_path = os.path.join(self.data_dir, "adapter_peft")
        model.save_pretrained(adapter_path)
        logger.info(f"✅ PEFT adapter 已保存: {adapter_path}")

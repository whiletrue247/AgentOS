"""
04_Engine — Prompt Injection Detector (Sprint 2)
==================================================
多層次的提示注入攻擊檢測器。

偵測策略：
  1. 規則層 (Rule-based): 偵測已知的注入模式 (角色覆寫、指令繞過等)
  2. 啟發式層 (Heuristic): 分析 prompt 結構異常 (突然出現 system 指令等)
  3. 統計層 (Statistical): 計算 prompt 的熵值和特殊字元比例

回傳：
  InjectionReport(is_suspicious, confidence, matched_rules, details)

使用方式：
  detector = InjectionDetector()
  report = detector.scan(user_message)
  if report.is_suspicious and report.confidence > 0.7:
      # 攔截或要求二次確認
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

__all__ = ["InjectionDetector", "InjectionReport"]


# ============================================================
# 已知注入模式 (持續更新)
# ============================================================

_INJECTION_PATTERNS: list[tuple[str, str, float]] = [
    # (pattern_name, regex, confidence_weight)

    # 角色覆寫攻擊
    ("role_override", r"(?i)(you\s+are\s+now|act\s+as|pretend\s+(to\s+)?be|from\s+now\s+on\s+you)", 0.7),
    ("ignore_instructions", r"(?i)(ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?))", 0.9),
    ("system_prompt_leak", r"(?i)(show\s+me\s+(your|the)\s+system\s+prompt|repeat\s+(your|the)\s+(system|initial)\s+(prompt|instructions?))", 0.85),

    # 注入分隔符
    ("delimiter_injection", r"(?i)(```system|<\|system\|>|<\|im_start\|>|<\|endoftext\|>|\[INST\]|\[\/INST\])", 0.95),
    ("markdown_system", r"(?i)(#{1,3}\s*system\s*(prompt|message|instruction))", 0.7),

    # 越獄嘗試
    ("jailbreak_dan", r"(?i)(DAN\s+mode|do\s+anything\s+now|jailbreak|developer\s+mode)", 0.8),
    ("bypass_safety", r"(?i)(bypass\s+(safety|security|filter)|disable\s+(safety|guardrail|filter))", 0.85),

    # 指令注入
    ("command_injection_shell", r"(?i)(;\s*rm\s+-rf|&&\s*curl|`.*`|\$\(.*\)|;\s*wget)", 0.9),
    ("path_traversal", r"\.\./\.\./", 0.75),

    # 資料滲透
    ("data_exfil", r"(?i)(send\s+(all|my)\s+(data|info|files?)\s+to|upload\s+.*\s+to\s+(http|ftp))", 0.85),

    # 社會工程
    ("social_engineering", r"(?i)(this\s+is\s+(an?\s+)?emergency|override\s+.*\s+protocol|admin\s+mode|sudo\s+mode)", 0.6),
]


@dataclass
class InjectionReport:
    """注入檢測報告"""
    is_suspicious: bool = False
    confidence: float = 0.0           # 0.0 ~ 1.0，越高越可疑
    matched_rules: List[str] = field(default_factory=list)
    details: str = ""
    heuristic_flags: List[str] = field(default_factory=list)


class InjectionDetector:
    """
    多層次提示注入檢測器。

    使用方式：
        detector = InjectionDetector()
        report = detector.scan("ignore previous instructions and...")
        if report.is_suspicious:
            logger.warning(f"🚨 注入偵測: {report}")
    """

    def __init__(self, sensitivity: float = 0.5):
        """
        Args:
            sensitivity: 敏感度 (0.0 ~ 1.0)，越高越嚴格
        """
        self._sensitivity = max(0.0, min(1.0, sensitivity))
        self._compiled_patterns = [
            (name, re.compile(pattern), weight)
            for name, pattern, weight in _INJECTION_PATTERNS
        ]
        logger.info(f"🛡️ InjectionDetector 初始化完成 (sensitivity={self._sensitivity:.1f}, {len(self._compiled_patterns)} rules)")

    def scan(self, text: str) -> InjectionReport:
        """
        掃描文字是否包含提示注入。

        Returns:
            InjectionReport
        """
        if not text or not text.strip():
            return InjectionReport()

        report = InjectionReport()

        # === Layer 1: 規則比對 ===
        self._scan_rules(text, report)

        # === Layer 2: 啟發式分析 ===
        self._scan_heuristics(text, report)

        # === Layer 3: 統計異常 ===
        self._scan_statistical(text, report)

        # 最終判定
        threshold = 0.5 - (self._sensitivity * 0.3)  # sensitivity=1.0 → threshold=0.2
        report.is_suspicious = report.confidence >= threshold

        if report.is_suspicious:
            details = ", ".join(report.matched_rules + report.heuristic_flags)
            report.details = f"Injection detected (confidence={report.confidence:.2f}): {details}"
            logger.warning(f"🚨 {report.details}")

        return report

    def _scan_rules(self, text: str, report: InjectionReport) -> None:
        """Layer 1: 規則比對"""
        max_weight = 0.0
        for name, pattern, weight in self._compiled_patterns:
            if pattern.search(text):
                report.matched_rules.append(name)
                max_weight = max(max_weight, weight)

        if report.matched_rules:
            # 多條規則命中 → 信心度加成
            rule_confidence = min(1.0, max_weight + len(report.matched_rules) * 0.05)
            report.confidence = max(report.confidence, rule_confidence)

    def _scan_heuristics(self, text: str, report: InjectionReport) -> None:
        """Layer 2: 啟發式分析"""

        # 1. 突然出現系統角色指令 (在 user message 中出現 "system:" 等)
        if re.search(r"(?i)^(system|assistant)\s*:", text, re.MULTILINE):
            report.heuristic_flags.append("role_label_in_user_msg")
            report.confidence = max(report.confidence, 0.6)

        # 2. 過多的指令性語言 (命令式句子比例)
        sentences = re.split(r'[.!?\n]', text)
        imperative_count = sum(1 for s in sentences if re.match(r'^\s*(you\s+must|always|never|do\s+not|don\'t)\b', s, re.I))
        if len(sentences) > 0 and imperative_count / max(len(sentences), 1) > 0.5:
            report.heuristic_flags.append("high_imperative_ratio")
            report.confidence = max(report.confidence, 0.4)

        # 3. 含有 Base64 長段 (可能是混淆注入)
        b64_pattern = re.findall(r'[A-Za-z0-9+/]{50,}={0,2}', text)
        if b64_pattern:
            report.heuristic_flags.append("base64_blob_detected")
            report.confidence = max(report.confidence, 0.5)

        # 4. 多語言混合 (可能是繞過策略)
        has_cjk = bool(re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', text))
        has_cyrillic = bool(re.search(r'[\u0400-\u04ff]', text))
        has_arabic = bool(re.search(r'[\u0600-\u06ff]', text))
        script_count = sum([has_cjk, has_cyrillic, has_arabic, bool(re.search(r'[a-zA-Z]', text))])
        if script_count >= 3:
            report.heuristic_flags.append("multi_script_mixing")
            report.confidence = max(report.confidence, 0.35)

    def _scan_statistical(self, text: str, report: InjectionReport) -> None:
        """Layer 3: 統計異常"""

        # 1. 特殊字元比例 (正常文本 < 5%, 注入文本常 > 15%)
        special_chars = sum(1 for c in text if c in '`|<>{}[]\\$();&!')
        special_ratio = special_chars / max(len(text), 1)
        if special_ratio > 0.15:
            report.heuristic_flags.append(f"high_special_char_ratio({special_ratio:.2f})")
            report.confidence = max(report.confidence, 0.45)

        # 2. Shannon 熵值 (高熵值可能表示亂碼/混淆)
        if len(text) > 50:
            entropy = self._shannon_entropy(text)
            # 自然語言熵值通常在 3.5~4.5，注入文本常 > 5.0
            if entropy > 5.5:
                report.heuristic_flags.append(f"high_entropy({entropy:.2f})")
                report.confidence = max(report.confidence, 0.4)

    @staticmethod
    def _shannon_entropy(text: str) -> float:
        """計算 Shannon 熵值"""
        if not text:
            return 0.0
        freq: dict[str, int] = {}
        for c in text:
            freq[c] = freq.get(c, 0) + 1
        length = len(text)
        return -sum(
            (count / length) * math.log2(count / length)
            for count in freq.values()
        )

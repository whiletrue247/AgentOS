"""
conftest.py — 修正 platform/ 目錄遮蔽標準庫問題
"""
import sys
import os

# 取得專案根目錄
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 確保專案子目錄在 path 中，供測試 import 使用
for subdir in ["03_Tool_System", "04_Engine", "05_Orchestrator", "06_Embodiment"]:
    path = os.path.join(PROJECT_ROOT, subdir)
    if path not in sys.path:
        sys.path.insert(0, path)

# 確保專案根目錄也在 path 中
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import json
import os
from unittest.mock import patch, mock_open, MagicMock, AsyncMock
import pytest
from pathlib import Path
from importlib import import_module

kernel_mod = import_module("01_Kernel.kernel")
soul_gen_mod = import_module("01_Kernel.soul_generator")
from contracts.interfaces import KernelConfig

@pytest.fixture
def temp_kernel_env(tmp_path, monkeypatch):
    """建立一個隔離的測試環境，將 SOUL 相關目錄替換到 tmp_path"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    soul_cache = data_dir / "soul_cache.json"
    soul_versions = data_dir / "soul_versions"
    soul_meta = soul_versions / "meta.json"
    soul_path = tmp_path / "SOUL.md"

    # Monkeypatch kernel.py internal paths
    monkeypatch.setattr(kernel_mod, "_SOUL_VERSIONS_DIR", soul_versions)
    monkeypatch.setattr(kernel_mod, "_SOUL_CACHE_FILE", soul_cache)
    monkeypatch.setattr(kernel_mod, "_SOUL_META_FILE", soul_meta)

    return {"soul_path": soul_path, "data_dir": data_dir, "soul_cache": soul_cache}

def test_kernel_load_soul_not_found(temp_kernel_env):
    """測試 SOUL 文件不存在的情況"""
    config = KernelConfig(soul_path=str(temp_kernel_env["soul_path"]))
    k = kernel_mod.Kernel(config)
    
    content = k.load_soul()
    assert "SOUL.md not found" in content or "You are a helpful AI Agent" in content
    assert k.get_system_prompt() == content

def test_kernel_load_soul_success_and_cache(temp_kernel_env):
    """測試 SOUL 文件讀取、快取與版本控制流程"""
    soul_path = temp_kernel_env["soul_path"]
    soul_path.write_text("Test SOUL Content", encoding="utf-8")
    
    config = KernelConfig(soul_path=str(soul_path))
    k = kernel_mod.Kernel(config)
    
    # 第一次讀取 (無快取)
    content1 = k.load_soul()
    assert content1 == "Test SOUL Content"
    assert temp_kernel_env["soul_cache"].exists()
    
    # 第二次讀取 (mtime hit)
    content2 = k.load_soul()
    assert content2 == "Test SOUL Content"
    
    # 觸發 disk cache hit (清空 memory cache 但保留 mtime 與 cache file)
    k._cached_content = None
    content3 = k.load_soul()
    assert content3 == "Test SOUL Content"

def test_kernel_soul_update_creates_version(temp_kernel_env):
    """測試 SOUL 內容更新後是否正確建立新版本備份"""
    soul_path = temp_kernel_env["soul_path"]
    soul_path.write_text("V1", encoding="utf-8")
    config = KernelConfig(soul_path=str(soul_path))
    k = kernel_mod.Kernel(config)
    k.load_soul()
    
    # 修改內容
    soul_path.write_text("V2", encoding="utf-8")
    import time
    time.sleep(0.01) # 確保 mtime 改變
    
    k.load_soul()
    history = k.get_version_history()
    assert len(history) == 2
    assert history[-1]["version"] == 2

@pytest.mark.asyncio
async def test_soul_generator():
    """測試 SoulGenerator 樣板生成機制"""
    from contracts.interfaces import KernelConfig
    mock_engine = AsyncMock()
    mock_engine.handle_message.return_value = "```markdown\n# software_engineer\nidentity\n```"
    gen = soul_gen_mod.SoulGenerator(KernelConfig(), engine=mock_engine)
    content = await gen.generate("software_engineer")
    assert "software_engineer" in content.lower() or "role" in content.lower()
    
    mock_engine.handle_message.return_value = "```markdown\n# Test Role\nTraits: T1\n```"
    custom = await gen.generate("Test Role")
    assert "Test Role" in custom
    assert "T1" in custom

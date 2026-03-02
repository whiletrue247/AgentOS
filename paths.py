import os
from pathlib import Path

# 取出專案根目錄位置：這個檔案 (paths.py) 所在的目錄，也就是 Agent_Base_OS
PROJECT_ROOT = Path(__file__).resolve().parent

def get_agentos_home() -> Path:
    """
    獲取 AgentOS 的資料儲存根目錄。
    優先順序：
    1. 環境變數 AGENTOS_HOME
    2. 預設：當前專案根目錄 (PROJECT_ROOT)
    """
    env_home = os.environ.get("AGENTOS_HOME")
    if env_home:
        home_path = Path(env_home).resolve()
    else:
        home_path = PROJECT_ROOT
        
    # 自動確保留有一定的基礎資料夾
    data_dir = home_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    return home_path

def get_data_dir() -> Path:
    """獲取 data 目錄路徑 (存放 sqlite, tool_catalog.json 等)"""
    home = get_agentos_home()
    data_dir = home / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

def get_tools_dir() -> Path:
    """獲取安裝的外掛工具所在目錄"""
    home = get_agentos_home()
    tools_dir = home / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    return tools_dir

def get_config_path() -> Path:
    """獲取 config.yaml 路徑"""
    return get_agentos_home() / "config.yaml"

def get_soul_path(filename: str = "SOUL.md") -> Path:
    """獲取 SOUL.md 路徑"""
    return get_agentos_home() / filename

def get_sqlite_db_path() -> Path:
    """獲取 SQLite 資料庫默認路徑"""
    return get_data_dir() / "memory.db"

def get_catalog_path() -> Path:
    """獲取 Tools Catalog 默認路徑"""
    return get_data_dir() / "tool_catalog.json"

def get_cost_history_path() -> Path:
    """獲取 Cost Guard 歷史花費路徑"""
    return get_data_dir() / "cost_history.json"

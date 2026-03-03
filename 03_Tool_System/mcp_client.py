"""
03_Tool_System — MCP Client (Model Context Protocol)
===================================================
連接外部 MCP Server (目前支援 Stdio) 的通訊客戶端。
當 AgentOS 啟動時，會根據 config.yaml 建立連線，獲取外部工具 (tools/list) 
並註冊至 ToolCatalog。當 LLM 呼叫時，透過此 Client 執行 (tools/call)。
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from contracts.interfaces import ToolSchema
from config_schema import MCPServerConfig

logger = logging.getLogger(__name__)

class MCPClient:
    """
    透過 Stdio 協議與單個 MCP Server 溝通的客戶端。
    （這是最輕量、最無依賴的實作，使用 JSON-RPC 2.0 OVER stdin/stdout）
    """
    def __init__(self, name: str, config: MCPServerConfig):
        self.name = name
        self.config = config
        self._process: Optional[asyncio.subprocess.Process] = None
        self._msg_id = 0
        self._pending_requests: Dict[int, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None

    async def start(self) -> bool:
        """啟動外部 MCP Subprocess，透過 stdio 建立通訊"""
        env = os.environ.copy()
        if self.config.env:
            env.update(self.config.env)

        cmd = [self.config.command] + self.config.args
        cmd_str = " ".join(cmd)
        
        try:
            self._process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, # 隱藏 Server 的 Debug LOG
                env=env
            )
            
            # 建立背景讀取 Task
            self._reader_task = asyncio.create_task(self._read_loop())
            
            # 發送 initialize 握手協定
            init_res = await self._send_request(
                "initialize", 
                {
                    "protocolVersion": "2024-11-05", 
                    "capabilities": {},
                    "clientInfo": {"name": "AgentOS", "version": "5.0"}
                }
            )
            
            # 發送 initialized 通知
            await self._send_notification("initialized", {})
            
            logger.info(f"🔌 MCP Server [{self.name}] 初始化成功 (protocol: {init_res.get('protocolVersion')})")
            return True
            
        except Exception as e:
            logger.error(f"❌ 啟動 MCP Server [{self.name}] 失敗 ({cmd_str}): {e}")
            return False

    async def get_tools(self) -> List[ToolSchema]:
        """向 MCP Server 獲取所有工具，轉為內部 ToolSchema"""
        try:
            res = await self._send_request("tools/list", {})
            tools = res.get("tools", [])
            
            schemas = []
            for t in tools:
                schema = ToolSchema(
                    name=t["name"],
                    description=t.get("description", f"MCP Tool from {self.name}"),
                    parameters=t.get("inputSchema", {"type": "object", "properties": {}}),
                    install_type="mcp",
                    requires_network=True,
                    mcp_server=self.name
                )
                schemas.append(schema)
                
            return schemas
        except Exception as e:
            logger.error(f"❌ 獲取 MCP Server [{self.name}] 工具失敗: {e}")
            return []

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """請求 MCP Server 執行外部工具"""
        try:
            res = await self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })
            
            # MCP 的 tools/call 回應通常放在 content 陣列中
            contents = res.get("content", [])
            output = ""
            for item in contents:
                if item.get("type") == "text":
                    output += item.get("text", "") + "\n"
                    
            if res.get("isError", False):
                raise RuntimeError(output or "MCP Server Error")
                
            return output.strip()
        except Exception as e:
            logger.error(f"❌ 執行 MCP工具 [{self.name}.{tool_name}] 失敗: {e}")
            raise RuntimeError(str(e))

    async def stop(self):
        """關閉連線並清理"""
        if self._reader_task:
            self._reader_task.cancel()
        
        if self._process and self._process.returncode is None:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
        logger.info(f"🔌 MCP Server [{self.name}] 已斷線")

    # ========================================
    # JSON-RPC 通訊底層
    # ========================================

    async def _send_request(self, method: str, params: dict) -> dict:
        self._msg_id += 1
        msg_id = self._msg_id
        
        payload = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params
        }
        
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[msg_id] = future
        
        data = json.dumps(payload) + "\n"
        if self._process and self._process.stdin:
            self._process.stdin.write(data.encode('utf-8'))
            await self._process.stdin.drain()
        
        return await future

    async def _send_notification(self, method: str, params: dict):
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        data = json.dumps(payload) + "\n"
        if self._process and self._process.stdin:
            self._process.stdin.write(data.encode('utf-8'))
            await self._process.stdin.drain()

    async def _read_loop(self):
        """持續讀取 stdout，解析 JSON-RPC 的 response"""
        while self._process and self._process.stdout:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break
                    
                line_str = line.decode('utf-8').strip()
                if not line_str:
                    continue
                    
                msg = json.loads(line_str)
                
                # 如果是 response
                if "id" in msg and msg["id"] in self._pending_requests:
                    future = self._pending_requests.pop(msg["id"])
                    if "error" in msg:
                        future.set_exception(RuntimeError(msg["error"].get("message", "Unknown RPC Error")))
                    else:
                        future.set_result(msg.get("result", {}))
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"⚠️ 解析 MCP stdout 錯誤 (可能是 debug text): {e}")

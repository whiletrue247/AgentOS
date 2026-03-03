"""
platform/dashboard/server.py
============================
本地 Web 面板伺服器 (基於 aiohttp)。
提供靜態檔案服務 (HTML/JS/CSS)，並提供 API 供面板讀取 AgentOS 狀態。
利用 EngineEvent 機制實現 SSE 即時推送。
"""

import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web
from config_schema import AgentOSConfig
from contracts.interfaces import EngineEvent, EventType

logger = logging.getLogger(__name__)


class DashboardServer:
    def __init__(self, config: AgentOSConfig, engine, state_machine, cost_guard, event_trace=None):
        self.config = config
        self.engine = engine
        self.state_machine = state_machine
        self.cost_guard = cost_guard
        self.event_trace = event_trace  # EventTrace 實例 (Observability 2.0)
        
        self.app = web.Application()
        self._setup_routes()
        
        # SSE 客戶端清單
        self._clients: set[web.Response] = set()
        
        # 訂閱全域 Engine 事件以廣播到前端
        self._subscribe_events()

    def _setup_routes(self) -> None:
        """設定 API 與靜態檔案路由"""
        self.app.router.add_get("/api/status", self._get_status)
        self.app.router.add_get("/api/tasks", self._get_tasks)
        self.app.router.add_get("/api/cost", self._get_cost)
        self.app.router.add_get("/api/stream", self._sse_handler)
        # Observability 2.0: Event Trace APIs
        self.app.router.add_get("/api/trace/stats", self._get_trace_stats)
        self.app.router.add_get("/api/trace/recent", self._get_trace_recent)
        self.app.router.add_get("/api/trace/{session_id}", self._get_trace_session)
        self.app.router.add_post("/api/trace/rollback", self._post_trace_rollback)
        
        # 靜態檔案路由 (index.html, JS, CSS)
        static_dir = Path(__file__).parent / "static"
        if not static_dir.exists():
            static_dir.mkdir(parents=True)
            # 生產環境下應已有檔案，若是新建，在這裡寫個 dummy 以防報錯
            (static_dir / "index.html").write_text("<h1>Dashboard Loading...</h1>", encoding="utf-8")
            
        self.app.router.add_static("/", static_dir, show_index=True)

    def _subscribe_events(self) -> None:
        """訂閱需要推送到前台的事件"""
        target_events = [
            EventType.USER_MESSAGE,
            EventType.AGENT_RESPONSE,
            EventType.TOOL_CALL,
            EventType.TOOL_RESULT,
            EventType.TASK_COMPLETE,
            EventType.BUDGET_WARNING,
            EventType.ERROR,
        ]
        for et in target_events:
            self.engine.on(et, self._broadcast_event)

    async def _broadcast_event(self, event: EngineEvent) -> None:
        """將 Engine 內部事件轉成 SSE 推送給前端"""
        if not self._clients:
            return
            
        data_str = json.dumps({
            "type": event.event_type.value,
            "timestamp": event.timestamp.isoformat(),
            "payload": event.payload,
            "agent_id": event.source_agent
        }, ensure_ascii=False)
        
        msg = f"event: engine_event\ndata: {data_str}\n\n"
        
        dead_clients = set()
        for client in self._clients:
            try:
                await client.write(msg.encode("utf-8"))
            except Exception:
                dead_clients.add(client)
                
        self._clients -= dead_clients

    # ========================================
    # API endpoints
    # ========================================

    async def _get_status(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "online",
            "version": "5.1.0",
            "active_clients": len(self._clients),
            "event_trace": self.event_trace is not None,
        })

    async def _get_tasks(self, request: web.Request) -> web.Response:
        tasks = []
        if self.state_machine:
            for t in self.state_machine.list_tasks():
                import dataclasses
                # tasks dictionary output
                tasks.append(dataclasses.asdict(t))
        return web.json_response({"tasks": tasks})

    async def _get_cost(self, request: web.Request) -> web.Response:
        report = {}
        if self.cost_guard:
            import dataclasses
            report = dataclasses.asdict(self.cost_guard.get_report())
        return web.json_response({"cost_report": report})

    # ========================================
    # Observability 2.0: Event Trace APIs
    # ========================================

    async def _get_trace_stats(self, request: web.Request) -> web.Response:
        """GET /api/trace/stats — 事件統計"""
        if not self.event_trace:
            return web.json_response({"error": "EventTrace not configured"}, status=503)
        return web.json_response(self.event_trace.get_stats())

    async def _get_trace_recent(self, request: web.Request) -> web.Response:
        """GET /api/trace/recent?type=xxx&limit=50 — 最近事件"""
        if not self.event_trace:
            return web.json_response({"error": "EventTrace not configured"}, status=503)
        event_type = request.query.get("type")
        limit = int(request.query.get("limit", "50"))
        events = self.event_trace.get_recent_events(event_type=event_type, limit=limit)
        return web.json_response({"events": events})

    async def _get_trace_session(self, request: web.Request) -> web.Response:
        """GET /api/trace/{session_id} — Session 完整時間軸"""
        if not self.event_trace:
            return web.json_response({"error": "EventTrace not configured"}, status=503)
        session_id = request.match_info["session_id"]
        limit = int(request.query.get("limit", "100"))
        events = self.event_trace.get_session_trace(session_id, limit=limit)
        return web.json_response({"session_id": session_id, "events": events})

    async def _post_trace_rollback(self, request: web.Request) -> web.Response:
        """POST /api/trace/rollback {event_id, session_id} — 回滾到指定事件"""
        if not self.event_trace:
            return web.json_response({"error": "EventTrace not configured"}, status=503)
        try:
            body = await request.json()
            event_id = body["event_id"]
            session_id = body["session_id"]
        except (KeyError, json.JSONDecodeError):
            return web.json_response({"error": "Missing event_id or session_id"}, status=400)
        deleted = self.event_trace.delete_events_after(event_id, session_id)
        return web.json_response({"rolled_back": deleted, "to_event": event_id})

    async def _sse_handler(self, request: web.Request) -> web.StreamResponse:
        """前端訂閱 SSE 用的 endpoint"""
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        await response.prepare(request)
        
        self._clients.add(response)
        logger.info(f"🟢 Dashboard 建立 SSE 連線 (目前共 {len(self._clients)} 人)")
        
        try:
            # 傳送個初始 ping
            await response.write(b"event: ping\ndata: connected\n\n")
            
            # 維持連線，定期發送 heartbeat
            while True:
                await asyncio.sleep(15)
                await response.write(b": heartbeat\n\n")
        except asyncio.CancelledError:
            pass
        finally:
            self._clients.discard(response)
            logger.info(f"🔴 Dashboard SSE 斷線 (剩餘 {len(self._clients)} 人)")
            
        return response

    # ========================================
    # 啟動與停止
    # ========================================

    async def start(self) -> None:
        """啟動 Web Server"""
        if not self.config.dashboard.enabled:
            logger.info("⏸️ Dashboard 未啟用，跳過啟動")
            return
            
        port = self.config.dashboard.port
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', port)
        await site.start()
        logger.info(f"🌐 Dashboard 已啟動於 http://localhost:{port}")

    async def stop(self) -> None:
        """停止 Web Server 確保優雅關閉"""
        # 關閉所有 SSE 連線
        for client in list(self._clients):
            try:
                await client.write(b"event: close\ndata: server shutting down\n\n")
                client.force_close()
            except Exception:
                pass
        self._clients.clear()
        
        # 停止 Server
        # （由 aiohttp.web 自動處理 graceful shutdown，若 runner 被記錄下來）
        logger.info("🛑 Dashboard 已停止")


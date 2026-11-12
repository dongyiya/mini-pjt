"""MCP 클라이언트 브리지 — src/mcp_server.py 에 stdio로 붙어 MCP 도구를 동기 LangChain 도구로 제공합니다.

- 백그라운드 스레드의 이벤트 루프에서 MCP 세션 하나를 계속 열어 두고(서버 프로세스 1개), 도구 호출을 그 루프로 넘깁니다.
- 에이전트 그래프는 동기로 돌기 때문에, 비동기 MCP 도구를 동기 함수로 감쌉니다.
- 서버를 띄우지 못하면 None 을 돌려주고, 에이전트는 로컬 도구로 대신합니다(src/agent.py make_tools).
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from typing import Any

from src.config import ROOT


def _text(result: Any) -> str:
    """MCP 도구 결과(문자열 또는 content 블록 목록)를 문자열로."""
    if isinstance(result, str):
        return result
    if isinstance(result, tuple):          # (content, artifact)
        result = result[0]
    if isinstance(result, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else getattr(b, "text", str(b)) for b in result)
    return json.dumps(result, ensure_ascii=False)


class McpBridge:
    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.stop_event: asyncio.Event | None = None
        self.tools: list = []
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, name="mcp-bridge", daemon=True)

    def start(self) -> "McpBridge":
        self.thread.start()
        if not self.ready.wait(self.timeout):
            raise TimeoutError("MCP 서버 연결 시간 초과")
        if self.error:
            raise self.error
        return self

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._session())

    async def _session(self) -> None:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        from langchain_mcp_adapters.tools import load_mcp_tools

        client = MultiServerMCPClient({"msds": {
            "command": sys.executable, "args": ["-X", "utf8", "-m", "src.mcp_server"],
            "transport": "stdio", "cwd": str(ROOT)}})
        try:
            async with client.session("msds") as session:
                self.tools = await load_mcp_tools(session)
                self.stop_event = asyncio.Event()
                self.ready.set()
                await self.stop_event.wait()
        except BaseException as e:  # 연결 실패를 start() 로 전달
            self.error = e
            self.ready.set()

    def call(self, tool, args: dict) -> str:
        fut = asyncio.run_coroutine_threadsafe(tool.ainvoke(args), self.loop)
        return _text(fut.result(self.timeout))

    def langchain_tools(self) -> dict[str, Any]:
        """이름 → 동기 StructuredTool."""
        from langchain_core.tools import StructuredTool

        out = {}
        for t in self.tools:
            def fn(_t=t, **kwargs):
                return self.call(_t, kwargs)
            out[t.name] = StructuredTool(name=t.name, description=t.description, args_schema=t.args_schema, func=fn)
        return out

    def close(self) -> None:
        if self.stop_event is not None:
            self.loop.call_soon_threadsafe(self.stop_event.set)
        self.thread.join(timeout=5)


_bridge: McpBridge | None = None
_lock = threading.Lock()


def get_mcp_tools() -> dict[str, Any] | None:
    """프로세스당 한 번 MCP 서버에 연결해 도구를 돌려줍니다. 실패하면 None."""
    global _bridge
    with _lock:
        if _bridge is None:
            try:
                _bridge = McpBridge().start()
            except BaseException as e:
                print(f"[경고] MCP 서버 연결 실패, 로컬 도구 사용: {type(e).__name__}: {e}", file=sys.stderr)
                _bridge = False  # type: ignore[assignment]
        return _bridge.langchain_tools() if _bridge else None

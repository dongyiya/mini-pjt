"""MCP 서버·클라이언트 테스트 — 실제로 서버 프로세스를 stdio로 띄워 도구를 호출합니다(네트워크 없음)."""

import json
from datetime import date

import pytest

# (기존 코드) from src import mcp_client, mcp_server, tools
from src.tools import mcp_client, mcp_server
from src.tools import msds_tools as tools


@pytest.fixture(scope="module")
def bridge():
    b = mcp_client.McpBridge(timeout=60).start()
    yield b
    b.close()


def test_server_exposes_expected_tools(bridge):
    assert sorted(t.name for t in bridge.tools) == sorted(mcp_server.MCP_TOOL_NAMES)


def test_mcp_results_match_local_tools(bridge):
    lc = bridge.langchain_tools()
    assert json.loads(lc["find_products_by_cas"].invoke({"cas": "108-88-3"})) == tools.find_products_by_cas("108-88-3")
    assert json.loads(lc["get_msds"].invoke({"product_id": "P-002", "sections": ["3"]})) == \
        tools.get_msds("P-002", ["3"])
    assert json.loads(lc["get_substance"].invoke({"cas": "108-88-3"}))["name"] == "톨루엔"


def test_mcp_keeps_masking(bridge):
    out = bridge.langchain_tools()["get_msds"].invoke({"product_id": "P-001"})
    for bad in ("2-부톡시에탄올", "111-76-2", "010-1234-5678", "김민수"):
        assert bad not in out


def test_make_tools_uses_mcp_when_enabled(monkeypatch, bridge):
    # (기존 코드) from src import agent as A
    from src.workflows import graph as A

    monkeypatch.setenv("MSDS_USE_MCP", "1")
    monkeypatch.setattr(mcp_client, "_bridge", bridge)
    names = {t.name: t for t in A.make_tools(date(2026, 11, 12))["impact"]}
    assert names["get_msds"].func.__name__ == "fn"                 # MCP 브리지 함수
    assert names["assess_update"].func.__name__ == "assess_update"  # MCP 대상이 아닌 도구는 로컬


def test_make_tools_local_when_disabled(monkeypatch):
    # (기존 코드) from src import agent as A
    from src.workflows import graph as A

    monkeypatch.setenv("MSDS_USE_MCP", "0")
    names = {t.name: t for t in A.make_tools(date(2026, 11, 12))["impact"]}
    assert names["get_msds"].func.__name__ == "get_msds"


def test_get_mcp_tools_falls_back_on_failure(monkeypatch):
    monkeypatch.setattr(mcp_client, "_bridge", None)

    class Broken(mcp_client.McpBridge):
        def start(self):
            raise ConnectionError("spawn failed")

    monkeypatch.setattr(mcp_client, "McpBridge", Broken)
    assert mcp_client.get_mcp_tools() is None
    assert mcp_client.get_mcp_tools() is None        # 한 번 실패하면 다시 시도하지 않음

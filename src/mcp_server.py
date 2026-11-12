"""MCP 서버 (패턴 5) — 사내 MSDS DB(제품·성분·물질 정보) 조회를 MCP 도구로 노출합니다.

    ../.venv/Scripts/python -m src.mcp_server        # stdio 전송

- 노출 도구: get_msds, list_products, find_products_by_cas, find_products_by_term, get_substance, classify_mixture
- 영업비밀·연락처 마스킹은 src/tools.py 단계에서 이미 적용되므로 MCP 경계 밖으로 원본이 나가지 않습니다.
- 에이전트는 src/mcp_client.py 로 이 서버에 붙어 도구를 호출합니다.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from src import tools

mcp = FastMCP("msds-db", log_level="WARNING")


def _j(x) -> str:
    return json.dumps(x, ensure_ascii=False)


@mcp.tool()
def get_msds(product_id: str, sections: list[str] | None = None) -> str:
    """제품 MSDS를 조회합니다. 영업비밀 성분과 담당자 연락처는 마스킹됩니다. sections 예: ["3", "15"]."""
    return _j(tools.get_msds(product_id, sections))


@mcp.tool()
def list_products() -> str:
    """등록된 제품 목록(id, 제품명, MSDS 개정판)을 돌려줍니다."""
    return _j(tools.list_products())


@mcp.tool()
def find_products_by_cas(cas: str) -> str:
    """CAS 번호로 해당 성분을 포함한 제품을 찾습니다. 영업비밀 성분은 검색되지 않습니다."""
    return _j(tools.find_products_by_cas(cas))


@mcp.tool()
def find_products_by_term(term: str, section: str = "15") -> str:
    """MSDS 특정 항목(기본 15번 법적 규제현황)에 용어가 적힌 제품을 찾습니다."""
    return _j(tools.find_products_by_term(term, section))


@mcp.tool()
def get_substance(cas: str) -> str:
    """단일물질 정보(안전보건공단 공개 MSDS 스냅샷: GHS 분류, 그림문자, 신호어, 국내 규제현황)를 CAS로 조회합니다."""
    return _j(tools.get_substance(cas))


@mcp.tool()
def classify_mixture(product_id: str) -> str:
    """제품 성분별 GHS 분류를 모아 제품 MSDS 2번과 비교한 검토 목록을 만듭니다(최종 혼합물 분류는 확인 필요)."""
    return _j(tools.classify_mixture(product_id))


MCP_TOOL_NAMES = ("get_msds", "list_products", "find_products_by_cas", "find_products_by_term",
                  "get_substance", "classify_mixture")


if __name__ == "__main__":
    mcp.run()

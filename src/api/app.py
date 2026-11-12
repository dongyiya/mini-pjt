"""FastAPI 서버 — API Spec.md 준수.

    ../.venv/Scripts/python -m uvicorn src.api.app:app --port 8000   (기존: src.api:app)

POST /query  Content-Type: application/json  Body: {"question": "..."}
Response    {"answer": str, "contexts": [{"doc_id", "text"}], "trace": [{"step", "input", "output"}]}

HITL: 개정 초안이 나오면 answer 에 "승인 대기 REQ-xxxx"를 돌려주고,
      같은 /query 에 {"question": "승인 REQ-xxxx"} 또는 {"question": "반려 REQ-xxxx 사유"}를 보내 재개합니다.
GET /health  컨테이너 상태 확인용
"""

from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# (기존 코드) from src.agent import build_graph, run_query, sqlite_checkpointer
from src.workflows.graph import build_graph, run_query, sqlite_checkpointer
# (기존 코드) from src.schemas import QueryRequest, QueryResponse
from src.api.schemas import QueryRequest, QueryResponse

log = logging.getLogger("msds-agent")


class UTF8JSONResponse(JSONResponse):
    """Content-Type 에 charset=utf-8 을 명시합니다(Windows PowerShell 5.1 Invoke-RestMethod 한글 깨짐 방지)."""
    media_type = "application/json; charset=utf-8"


# (기존 코드) 기본 JSONResponse — charset 이 없어 PowerShell 5.1 에서 한글이 깨져 교체
# app = FastAPI(title="MSDS 개정 지원 에이전트", version="0.1.0")
app = FastAPI(title="MSDS 개정 지원 에이전트", version="0.1.0", default_response_class=UTF8JSONResponse)


@lru_cache(maxsize=1)
def get_graph():
    return build_graph(checkpointer=sqlite_checkpointer())


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    try:
        result = run_query(req.question, get_graph())
        return QueryResponse(**result)
    except Exception as e:  # 응답 모양은 API Spec 그대로 유지
        log.exception("query failed")
        body = QueryResponse(answer="처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.", contexts=[],
                             trace=[{"step": "error", "input": req.question, "output": type(e).__name__}])
        return UTF8JSONResponse(status_code=500, content=body.model_dump())


# --- 사용자 화면 (2026-11-12 추가) -----------------------------------------------------------
# GET /  → src/api/static/index.html. 화면의 모든 버튼은 POST /query 만 호출합니다(API Spec 그대로).
# 변경 사건·제품 목록과 법령 기준일은 화면을 열 때 데이터 파일에서 읽어 HTML 에 넣어 보냅니다(별도 API 없음).
import json as _json
from pathlib import Path as _Path

from fastapi.responses import HTMLResponse

# (기존 코드) from src import retriever as _retriever
from src.regulation import retriever as _retriever
# (기존 코드) from src import tools as _tools
# (기존 코드) from src.tools import msds_tools as _tools  — 현재 쓰는 곳이 없어 주석 처리 (2026-11-12)
# (기존 코드) from src.config import LAW_DIR as _LAW_DIR
from src.shared.config import LAW_DIR as _LAW_DIR

_UI = _Path(__file__).resolve().parent / "static" / "index.html"


def _law_versions() -> list[dict]:
    out = []
    for p in sorted(_LAW_DIR.glob("*.md")):
        meta = _retriever._parse_front(p.read_text(encoding="utf-8"))
        out.append({k: meta.get(k, "") for k in ("law", "status", "effective", "collected")})
    return out


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui() -> HTMLResponse:
    # (기존 코드) from src.revision_preview import build_ui_data
    from src.revision.preview import build_ui_data

    laws = _law_versions()
    # (기존 코드) 변경 사건·제품 목록만 전달 — 대시보드·MSDS 조회·변경 전후 비교 데이터를 추가하며 교체
    # boot = {"updates": _tools.list_regulation_updates(), "products": _tools.list_products(), "laws": laws,
    #         "lawsAsOf": max((x["collected"] for x in laws if x["collected"]), default="")}
    # (기존 코드) 승인 대기 건 없이 전달 — 서버 체크포인트의 승인 대기 건을 승인함에 불러오도록 교체
    # boot = {**build_ui_data(), "laws": laws,
    #         "lawsAsOf": max((x["collected"] for x in laws if x["collected"]), default="")}
    # (기존 코드) from src.revision_preview import pending_requests
    from src.revision.preview import pending_requests

    # (기존 코드) 승인 대기 건만 전달 — '중복 요청'으로 닫힌 건 번호도 전달해 브라우저 승인함에서 지우도록 교체 (2026-11-12)
    # try:
    #     graph = get_graph()
    #     pending = pending_requests(graph, graph.checkpointer)
    # except Exception:  # 체크포인트를 읽지 못해도 화면은 열리게 함
    #     log.exception("pending requests load failed")
    #     pending = []
    # boot = {**build_ui_data(), "laws": laws, "pending": pending,
    #         "lawsAsOf": max((x["collected"] for x in laws if x["collected"]), default="")}
    from src.revision.dedupe import closed_duplicate_ids

    try:
        graph = get_graph()
        pending = pending_requests(graph, graph.checkpointer)
        duplicates = closed_duplicate_ids(graph)
    except Exception:  # 체크포인트를 읽지 못해도 화면은 열리게 함
        log.exception("pending requests load failed")
        pending, duplicates = [], []
    boot = {**build_ui_data(), "laws": laws, "pending": pending, "closedDuplicates": duplicates,
            "lawsAsOf": max((x["collected"] for x in laws if x["collected"]), default="")}
    data = _json.dumps(boot, ensure_ascii=False).replace("</", "<\/")
    return HTMLResponse(_UI.read_text(encoding="utf-8").replace("/*__BOOT__*/null", data))

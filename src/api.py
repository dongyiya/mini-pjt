"""FastAPI 서버 — API Spec.md 준수.

    ../.venv/Scripts/python -m uvicorn src.api:app --port 8000

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

from src.agent import build_graph, run_query, sqlite_checkpointer
from src.schemas import QueryRequest, QueryResponse

log = logging.getLogger("msds-agent")
app = FastAPI(title="MSDS 개정 지원 에이전트", version="0.1.0")


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
        return JSONResponse(status_code=500, content=body.model_dump())

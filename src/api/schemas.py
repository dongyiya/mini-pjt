"""API Spec 입출력 스키마 (이름·구조 변경 금지).

QueryRequest {question} → QueryResponse {answer, contexts[{doc_id,text}], trace[{step,input,output}]}
(2026-11-12 리팩토링: src/schemas.py 에서 API 부분만 옮김. 에이전트 구조화 출력은 src/agents/schemas.py)
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class Context(BaseModel):
    doc_id: str
    text: str


class TraceStep(BaseModel):
    step: str
    input: str
    output: str


class QueryResponse(BaseModel):
    answer: str
    contexts: list[Context]
    trace: list[TraceStep]

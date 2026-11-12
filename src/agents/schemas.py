"""에이전트 구조화 출력 스키마 (패턴 1: LCEL 구조화 출력).
(2026-11-12 리팩토링: src/schemas.py → src/agents/schemas.py. API Spec 입출력은 src/api/schemas.py)

(기존 docstring)
데이터 스키마 (패턴 1: LCEL 구조화 출력 + API Spec 입출력).

- API Spec 모양: QueryRequest {question} → QueryResponse {answer, contexts[{doc_id,text}], trace[{step,input,output}]}
- LLM 구조화 출력: Route(Supervisor 라우팅), RevisionJudgment(개정 판정·초안)
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DOC_ID = re.compile(r"^(law:[^:\s]+:\d+(의\d+)?(@\d{4}-\d{2}-\d{2})?|msds:P-\d{3})$")


# ---------------------------------------------------------------- API Spec (이름·구조 변경 금지)
# (기존 코드) API 입출력 스키마 — 2026-11-12 리팩토링으로 src/api/schemas.py 로 옮김
# class QueryRequest(BaseModel):
#     question: str = Field(min_length=1, max_length=2000)
#
#
# class Context(BaseModel):
#     doc_id: str
#     text: str
#
#
# class TraceStep(BaseModel):
#     step: str
#     input: str
#     output: str
#
#
# class QueryResponse(BaseModel):
#     answer: str
#     contexts: list[Context]
#     trace: list[TraceStep]


# ---------------------------------------------------------------- Supervisor 라우팅
class Route(BaseModel):
    """질문을 어느 서브 에이전트에 맡길지."""
    agent: Literal["regulation", "impact", "revision", "out_of_scope"] = Field(
        description=("regulation: 법령 조문·제도 질문 / impact: 제품 MSDS·성분 조회, 변경 사건 영향 확인 / "
                     "revision: 특정 변경 사건을 반영해 제품 MSDS를 고치거나 재제출해야 하는지(개정 초안 필요) / "
                     "out_of_scope: MSDS·산업안전보건법·화학물질관리법과 무관"))
    reason: str = Field(description="한 문장 근거")


# ---------------------------------------------------------------- 개정 판정 (HITL 대상)
class ProductRevision(BaseModel):
    product_id: str = Field(description="예: P-002")
    product_name: str
    sections: list[str] = Field(description="고칠 MSDS 항목 번호 (예: ['3'])")
    changes: list[str] = Field(description="항목별 바꿀 내용 (예: '톨루엔 함유량 10~20% → 25~35%')")
    resubmission_required: bool = Field(description="시행규칙 제159조제1항에 따른 공단 재제출 대상 여부")


class RevisionJudgment(BaseModel):
    revision_needed: bool
    products: list[ProductRevision] = Field(default_factory=list)
    reasons: list[str] = Field(description="판정 이유. 조문 번호를 포함")
    legal_basis: list[str] = Field(description="근거 doc_id 목록 (예: law:산안법시행규칙:159, msds:P-002)")
    draft: str = Field(description="담당자 검토용 개정 초안 요약 (항목별 변경 전→후)")

    @field_validator("legal_basis")
    @classmethod
    def _check_doc_ids(cls, v: list[str]) -> list[str]:
        bad = [d for d in v if not DOC_ID.match(d)]
        if bad:
            raise ValueError(f"doc_id 형식이 아닙니다: {bad}")
        return v

    @property
    def resubmission_required(self) -> bool:
        return any(p.resubmission_required for p in self.products)

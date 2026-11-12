"""최소 파이프라인 스케치 (LLM 없이 규칙 기반).

API Spec 응답 모양({answer, contexts[{doc_id,text}], trace[{step,input,output}]})을
1일차에 미리 고정하고, 데이터·도구·검색이 맞물리는지 확인하기 위한 뼈대입니다.
2일차에 src/agent.py의 LangGraph(Supervisor + ReAct + 구조화 출력 + HITL)로 바꿉니다.

    python -m src.workflows.pipeline_v1 "U-01 반영하려면 어떤 제품 MSDS를 고쳐야 해?"
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

# (기존 코드) from src import tools
from src.tools import msds_tools as tools
# (기존 코드) from src.retriever import get_chunk, retrieve
from src.regulation.retriever import get_chunk, retrieve

INJECTION = re.compile(r"(이전|위의?)\s*(지시|명령|규칙).*(무시|잊)|ignore (all|previous)|system prompt", re.I)
APPROVAL_BYPASS = re.compile(r"승인\s*없이|바로\s*(확정|제출)|자동\s*제출")
TRADE_SECRET = re.compile(r"영업비밀.*(실제|진짜|정확|이름|성분명|함유량)|(실제|진짜)\s*성분")
CONTACT = re.compile(r"(담당자|연락처|전화|이메일)")
IN_SCOPE = re.compile(r"MSDS|물질안전보건자료|화학|성분|CAS|유해|규제|화관법|산안법|산업안전보건법|화학물질관리법|"
                      r"제품|개정|제출|게시|U-\d+|P-\d+|\d{2,7}-\d{2}-\d")


def _ctx(doc_id: str, text: str) -> dict[str, str]:
    return {"doc_id": doc_id, "text": text}


def guard(question: str) -> str | None:
    """입력 가드레일. 막아야 하면 거절 사유를 돌려줍니다."""
    if INJECTION.search(question):
        return "시스템 지시를 바꾸려는 요청은 처리할 수 없습니다. MSDS 관련 질문을 해 주세요."
    if APPROVAL_BYPASS.search(question):
        return "MSDS 개정본 확정·제출은 담당자 승인 후에만 진행합니다. 초안 검토를 요청해 주세요."
    if TRADE_SECRET.search(question):
        return "영업비밀로 지정된 성분의 실제 명칭과 함유량은 제공할 수 없습니다."
    if not IN_SCOPE.search(question):
        return "이 서비스는 MSDS와 관련 법규(산업안전보건법·화학물질관리법) 질문만 답합니다."
    return None


def run(question: str) -> dict[str, Any]:
    trace: list[dict[str, str]] = []
    contexts: list[dict[str, str]] = []

    refusal = guard(question)
    trace.append({"step": "input_guard", "input": question, "output": refusal or "통과"})
    if refusal:
        return {"answer": refusal, "contexts": [], "trace": trace}

    lines: list[str] = []
    update_ids = re.findall(r"U-\d+", question.upper())
    product_ids = re.findall(r"P-\d+", question.upper())
    cas_list = re.findall(r"\b\d{2,7}-\d{2}-\d\b", question)

    # 1) 변경 사건 → 영향 판정 도구
    for uid in update_ids:
        result = tools.assess_update(uid)
        trace.append({"step": "tool:assess_update", "input": uid,
                      "output": json.dumps(result, ensure_ascii=False)[:500]})
        if "error" in result:
            lines.append(result["error"])
            continue
        for a in result["affected"]:
            r = a["resubmission"]
            need = "재제출 필요" if r["resubmission_required"] else "재제출 대상 항목 아님"
            lines.append(f"- {a['product_id']} {a['product_name']}: {', '.join(a['sections'])}번 항목 개정 검토, "
                         f"{need} ({r['basis']})")
            contexts.append(_ctx(f"msds:{a['product_id']}",
                                 json.dumps(tools.get_msds(a["product_id"], a["sections"] or None), ensure_ascii=False)))
        # (기존 코드) doc_id 문자열로 검색해서 조문을 찾던 방식 — 검색 점수에 따라 빠지는 문제가 있어 교체
        # for doc_id in result["doc_ids"]:
        #     for c in retrieve(doc_id, k=10):
        #         if c.doc_id == doc_id:
        #             contexts.append(_ctx(c.doc_id, c.text))
        #             break
        doc_ids = list(result["doc_ids"])
        for a in result["affected"]:
            doc_ids += [d for d in a["resubmission"]["doc_ids"] if d not in doc_ids]
        for doc_id in doc_ids:
            c = get_chunk(doc_id)
            if c and all(x["doc_id"] != doc_id for x in contexts):
                contexts.append(_ctx(c.doc_id, c.text))

    # 2) CAS → 제품 검색 도구
    for cas in cas_list:
        hits = tools.find_products_by_cas(cas)
        trace.append({"step": "tool:find_products_by_cas", "input": cas,
                      "output": json.dumps(hits, ensure_ascii=False)})
        lines.append(f"- CAS {cas} 포함 제품: " + (", ".join(f"{h['product_id']}({h['content']})" for h in hits) or "없음"))
        for h in hits:
            contexts.append(_ctx(f"msds:{h['product_id']}",
                                 json.dumps(tools.get_msds(h["product_id"], ["3"]), ensure_ascii=False)))

    # 3) 제품 MSDS 조회 (마스킹 적용)
    if not update_ids:
        for pid in product_ids:
            view = tools.get_msds(pid)
            trace.append({"step": "tool:get_msds", "input": pid, "output": json.dumps(view, ensure_ascii=False)[:500]})
            contexts.append(_ctx(f"msds:{pid}", json.dumps(view, ensure_ascii=False)))
            if CONTACT.search(question) and "section1" in view:
                s1 = view["section1"]
                lines.append(f"- {pid} 담당자: {s1['contact_name']}, {s1['contact_phone']}, {s1['contact_email']} (마스킹됨)")

    # 4) 법령 검색 (RAG)
    if not lines:
        chunks = retrieve(question, k=3)
        trace.append({"step": "retrieve", "input": question, "output": ", ".join(c.doc_id for c in chunks)})
        for c in chunks:
            contexts.append(_ctx(c.doc_id, c.text))
        if chunks:
            lines.append(f"가장 관련 있는 조문은 {chunks[0].title}입니다. (LLM 답변 생성은 2일차에 연결)")

    answer = "\n".join(lines) or "관련 정보를 찾지 못했습니다."
    answer = tools.mask_email(tools.mask_phone(answer))  # 출력 가드레일
    trace.append({"step": "output_guard", "input": "answer", "output": "연락처·이메일 마스킹 적용"})
    return {"answer": answer, "contexts": contexts, "trace": trace}


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "U-01 반영하려면 어떤 제품 MSDS를 고쳐야 해?"
    print(json.dumps(run(q), ensure_ascii=False, indent=2))

"""도구 결과 → trace / contexts(근거) 변환.

(2026-11-12 리팩토링: src/agent.py 의 _law_contexts·_msds_context·contexts_from_tool·_contexts_from_tool_v1·collect 를 옮김.
 문장형 근거 문구는 같은 폴더 evidence_text.py)
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from src.guardrails import guard as guardrails
from src.regulation import retriever
from src.shared.trace import dumps as _dumps
from src.shared.trace import message_text as _text
from src.shared.trace import step
from src.tools import msds_tools as tools


def _law_contexts(doc_ids: list[str], as_of: date) -> list[dict]:
    out = []
    for d in doc_ids:
        if not d.startswith("law:"):
            continue
        cur, future = retriever.get_applicable(d, as_of)
        if cur:
            out.append({"doc_id": cur.doc_id, "text": cur.text})
        out += [{"doc_id": c.doc_id, "text": c.label(as_of) + c.text} for c in future]
    return out


# (기존 코드) 제품 MSDS 근거를 JSON 문자열로 — 2차 평가 faithfulness 개선을 위해 문장형으로 교체
# def _msds_context(pid: str, sections: list[str] | None = None) -> dict:
#     view = tools.get_msds(pid, sections)
#     return {"doc_id": f"msds:{pid}", "text": _dumps(view)}
def _msds_context(pid: str, sections: list[str] | None = None) -> dict:
    # (기존 코드) from src import context_text
    from src.workflows import evidence_text as context_text

    view = tools.get_msds(pid, sections)
    return {"doc_id": f"msds:{pid}", "text": context_text.msds_text(view)}


def contexts_from_tool(name: str, args: dict, result: Any, as_of: date) -> list[dict]:
    """도구 호출 하나의 결과에서 근거 문서를 뽑습니다(API Spec contexts 형식).

    (2026-11-12) JSON 대신 문장형 근거(src/workflows/evidence_text.py)를 쓰고, 규칙 판정 결과를 `rule:` 근거로 추가합니다.
    아래 기존 분기는 _contexts_from_tool_v1 로 남겼습니다.
    """
    if not isinstance(result, (dict, list)) or (isinstance(result, dict) and "error" in result):
        return []
    # (기존 코드) from src import context_text as T
    from src.workflows import evidence_text as T

    if name == "search_law":
        out = [{"doc_id": c["doc_id"], "text": c["text"]} for c in result.get("applicable", [])]
        out += [{"doc_id": c["doc_id"], "text": f"[시행 예정 {c['effective_from']}] {c['text']}"}
                for c in result.get("upcoming", [])]
        return out
    if name == "get_msds":
        return [{"doc_id": result.get("doc_id", f"msds:{args.get('product_id')}"), "text": T.msds_text(result)}]
    if name == "get_regulation_update":
        return ([{"doc_id": f"update:{result['id']}", "text": T.update_text(result)}]
                + _law_contexts(result.get("related_docs", []), as_of))
    if name == "list_regulation_updates":
        return [{"doc_id": "catalog:updates", "text": T.updates_catalog_text(result)}]
    if name == "list_products":
        return [{"doc_id": "catalog:products", "text": T.products_catalog_text(result)}]
    if name == "check_resubmission":
        return ([{"doc_id": f"rule:check_resubmission:{args.get('change', '')}", "text": T.resubmission_text(result)}]
                + _law_contexts(result.get("doc_ids", []), as_of))
    if name == "assess_update":
        uid = result.get("update", {}).get("id", args.get("update_id", ""))
        out = [{"doc_id": f"rule:assess_update:{uid}", "text": T.assessment_text(result)}]
        out += _law_contexts(result.get("doc_ids", []), as_of)
        for a in result.get("affected", []):
            out.append(_msds_context(a["product_id"], a.get("sections") or None))
            out += _law_contexts(a.get("resubmission", {}).get("doc_ids", []), as_of)
        return out
    if name == "find_products_by_cas":
        return ([{"doc_id": f"rule:find_products_by_cas:{args.get('cas', '')}",
                  "text": T.products_by_cas_text(args.get("cas", ""), result)}]
                + [_msds_context(h["product_id"], ["3"]) for h in result])
    if name == "find_products_by_term":
        return [_msds_context(h["product_id"], [args.get("section", "15")]) for h in result]
    if name == "get_substance":
        return [{"doc_id": result["doc_id"], "text": T.substance_text(result)}]
    if name == "classify_mixture":
        return [{"doc_id": f"msds:{result['product_id']}", "text": T.mixture_text(result)}]
    return []


def _contexts_from_tool_v1(name: str, args: dict, result: Any, as_of: date) -> list[dict]:
    """(기존 코드) 1·2차 평가 때의 JSON 근거 버전 — 비교용으로 남김, 호출하지 않음."""
    if not isinstance(result, (dict, list)) or (isinstance(result, dict) and "error" in result):
        return []
    if name == "search_law":
        out = [{"doc_id": c["doc_id"], "text": c["text"]} for c in result.get("applicable", [])]
        out += [{"doc_id": c["doc_id"], "text": f"[시행 예정 {c['effective_from']}] {c['text']}"}
                for c in result.get("upcoming", [])]
        return out
    if name == "get_msds":
        return [{"doc_id": result.get("doc_id", f"msds:{args.get('product_id')}"), "text": _dumps(result)}]
    if name == "get_regulation_update":
        return ([{"doc_id": f"update:{result['id']}", "text": _dumps(result)}]
                + _law_contexts(result.get("related_docs", []), as_of))
    if name == "list_regulation_updates":
        return [{"doc_id": "catalog:updates", "text": _dumps(result)}]
    if name == "list_products":
        return [{"doc_id": "catalog:products", "text": _dumps(result)}]
    if name == "check_resubmission":
        return _law_contexts(result.get("doc_ids", []), as_of)
    if name == "assess_update":
        out = _law_contexts(result.get("doc_ids", []), as_of)
        for a in result.get("affected", []):
            out.append(_msds_context(a["product_id"], a.get("sections") or None))
            out += _law_contexts(a.get("resubmission", {}).get("doc_ids", []), as_of)
        return out
    if name in ("find_products_by_cas", "find_products_by_term"):
        section = "3" if name == "find_products_by_cas" else args.get("section", "15")
        return [_msds_context(h["product_id"], [section]) for h in result]
    if name == "get_substance":
        return [{"doc_id": result["doc_id"], "text": _dumps(result)}]
    if name == "classify_mixture":
        return [{"doc_id": f"msds:{result['product_id']}", "text": _dumps(result)}]
    return []


def collect(messages: list[BaseMessage], as_of: date) -> tuple[list[dict], list[dict]]:
    """에이전트 메시지에서 도구 호출 trace와 contexts를 모읍니다(마스킹 적용, doc_id 중복 제거)."""
    calls = {}
    for m in messages:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls:
                calls[tc["id"]] = tc
    trace, contexts, seen = [], [], set()
    for m in messages:
        if not isinstance(m, ToolMessage):
            continue
        tc = calls.get(m.tool_call_id, {"name": m.name or "?", "args": {}})
        raw = _text(m)
        trace.append(step(f"tool:{tc['name']}", tc.get("args", {}), raw))
        try:
            result = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        for c in contexts_from_tool(tc["name"], tc.get("args", {}), result, as_of):
            if c["doc_id"] not in seen:
                seen.add(c["doc_id"])
                contexts.append({"doc_id": c["doc_id"], "text": guardrails.mask_output(c["text"])[0]})
    return trace, contexts

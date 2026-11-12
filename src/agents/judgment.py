"""개정 판정 후처리 — 판정 사후 검증과 답변 문구.

(2026-11-12 리팩토링: src/agent.py 의 sanitize_judgment·format_judgment 를 그대로 옮김)
"""

from __future__ import annotations

import json
import re

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from src.agents.schemas import RevisionJudgment
from src.shared.trace import message_text as _text


# ---------------------------------------------------------------- 판정 사후 검증 (1차 평가 16번 환각 대응)
def sanitize_judgment(j: RevisionJudgment, messages: list[BaseMessage]) -> tuple[RevisionJudgment, list[str]]:
    """LLM 판정의 영향 제품·항목을 assess_update 도구 결과로 검증해 근거 없는 것을 뺍니다. (판정, 제거 내역)"""
    calls = {tc["id"]: tc for m in messages if isinstance(m, AIMessage) for tc in m.tool_calls}
    allowed: dict[str, set[str]] = {}
    seen_assess = False
    for m in messages:
        if isinstance(m, ToolMessage) and calls.get(m.tool_call_id, {}).get("name") == "assess_update":
            try:
                res = json.loads(_text(m))
            except (json.JSONDecodeError, TypeError):
                continue
            seen_assess = True
            for a in res.get("affected", []):
                allowed.setdefault(a["product_id"], set()).update(a.get("sections", []))
    if not seen_assess:
        return j, []
    removed, kept = [], []
    for p in j.products:
        ok = allowed.get(p.product_id)
        if not ok:
            removed.append(f"{p.product_id}: 도구 결과(assess_update)상 변경 사건의 영향 제품이 아니어서 수정 대상에서 제외")
            continue
        drop = [s for s in p.sections if s not in ok]
        if drop:
            removed.append(f"{p.product_id}: {', '.join(drop)}번 항목은 도구 결과(assess_update)상 변경 사건의 영향이 없어 "
                           "수정 대상에서 제외")
        secs = [s for s in p.sections if s in ok]
        changes = [c for c in p.changes
                   if not (mm := re.match(r"\s*(\d+)번", c)) or mm[1] in secs]
        kept.append(p.model_copy(update={"sections": secs, "changes": changes}))
    if not removed:
        return j, []
    draft = "\n".join(f"[{p.product_id}] {c}" for p in kept for c in p.changes) or "수정할 항목 없음"
    fixed = j.model_copy(update={"products": kept, "revision_needed": bool(kept),
                                 "reasons": j.reasons + removed, "draft": draft})
    return fixed, removed


# ---------------------------------------------------------------- 답변 문구
def format_judgment(j: RevisionJudgment, req_id: str, pending: bool) -> str:
    if not j.revision_needed:
        return "결론: 고쳐야 할 MSDS가 없습니다.\n\n판단 근거\n" + "\n".join(f"- {r}" for r in j.reasons)
    resub = [p for p in j.products if p.resubmission_required]
    head = ("결론: 예, 공단 재제출 대상입니다." if resub else
            "결론: MSDS 개정(수정) 검토가 필요하지만, 시행규칙 제159조제1항의 재제출 대상 항목에는 해당하지 않습니다.")
    lines = [head, "", "영향 제품과 고칠 항목"]
    for p in j.products:
        tag = "공단 재제출 대상" if p.resubmission_required else "재제출 대상 아님"
        lines.append(f"- {p.product_id} {p.product_name}: {', '.join(p.sections)}번 항목 수정 / {tag}")
        lines += [f"  · {c}" for c in p.changes]
    lines += ["", "판단 근거"] + [f"- {r}" for r in j.reasons]
    if resub:
        lines += ["", "재제출 대상 제품은 변경사항을 반영한 MSDS를 지체 없이 공단에 제출해야 합니다(시행규칙 제159조제2항)."]
    lines += ["", "개정 초안", j.draft]
    if pending:
        lines += ["", f"개정 초안은 담당자 승인 대기 상태입니다 ({req_id}). 확정·제출은 승인 후에만 진행합니다.",
                  f"승인하려면 '승인 {req_id}', 반려하려면 '반려 {req_id} 사유'를 보내 주세요."]
    return "\n".join(lines)

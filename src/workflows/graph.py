"""메인 에이전트 그래프."""

# --- 아래부터 추가 (기존 코드: 위 docstring 한 줄) ---
# LangGraph 그래프 (패턴 1·2·6·7·9·11)
#
#   POST /query → input_guard ─(차단)──────────────────────────────┐
#                     └→ supervisor ─┬→ regulation_agent ──────────┤
#                                    ├→ impact_agent ──────────────┤
#                                    ├→ revision_agent ─(개정 필요)→ approval(interrupt) ─┤
#                                    └→ (범위 밖) ──────────────────┤
#                                                                  └→ output_guard → END
#
# - supervisor: 질문 기준일 추출(select_law_version) + LCEL 구조화 출력(Route)으로 위임 대상 결정
# - 서브 에이전트: create_agent(ReAct, bind_tools)로 도구를 스스로 골라 호출. 도구는 기준일이 묶인 채로 전달
# - revision_agent: 도구 결과를 근거로 LCEL 구조화 출력(RevisionJudgment) → 개정 필요하면 approval 노드에서 interrupt()
# - HITL: 엔드포인트를 늘리지 않고 같은 /query 에 "승인 REQ-xxxx" / "반려 REQ-xxxx 사유"로 재개 (SqliteSaver, thread_id=REQ-xxxx)
# - 모든 노드는 trace 에 {step, input, output}을 쌓고, 도구 결과에서 근거(contexts)를 모읍니다.
# - LLM이 하는 부분(route / react / judge)은 Brains 로 묶어 테스트에서 가짜로 바꿔 끼울 수 있습니다.
#
# (2026-11-12 리팩토링) src/agent.py → src/workflows/graph.py. 그래프·/query 처리만 남기고 나머지는 도메인 폴더로 옮겼습니다.
#   - 프롬프트            → src/agents/prompts.py
#   - Brains·도구 묶음    → src/agents/brains.py
#   - 판정 검증·답변 문구 → src/agents/judgment.py
#   - 도구 결과 → 근거    → src/workflows/evidence.py
#   - 체크포인터·REQ 번호 → src/memory/checkpointer.py
#   - step·메시지 텍스트  → src/shared/trace.py
#   옮긴 함수 이름은 아래 import 로 이 모듈에서도 그대로 쓸 수 있습니다(기존 호출·테스트 호환).

from __future__ import annotations

import operator
import re
from datetime import date
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

# (기존 코드) import
# import json
# import secrets
# import sqlite3
# from dataclasses import dataclass
# from typing import Any, Callable
# from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage
# from src import guardrails, retriever, tools
# from src.config import CHECKPOINT_DB
# from src.dates import extract_as_of
# from src.schemas import RevisionJudgment, Route
from src.agents.brains import Brains, _typed, llm_brains, make_tools, use_mcp  # noqa: F401
from src.agents.judgment import format_judgment, sanitize_judgment
from src.agents.prompts import COMMON_RULES, JUDGE_PROMPT, PROMPTS, ROUTER_PROMPT  # noqa: F401
from src.agents.schemas import RevisionJudgment, Route  # noqa: F401
from src.guardrails import guard as guardrails
from src.memory.checkpointer import new_req_id, sqlite_checkpointer  # noqa: F401
from src.shared.dates import extract_as_of
from src.shared.trace import dumps as _dumps  # noqa: F401
from src.shared.trace import message_text as _text
from src.shared.trace import step
from src.workflows.evidence import (_contexts_from_tool_v1, _law_contexts, _msds_context, collect,  # noqa: F401
                                    contexts_from_tool)

OUT_OF_SCOPE_MESSAGE = ("이 서비스는 MSDS(물질안전보건자료)와 관련 법규(산업안전보건법·화학물질관리법) 질문만 답합니다. "
                        "범위 밖 질문에는 답하지 않습니다.")
DECISION = re.compile(r"^\s*(승인|반려)\s+(REQ-[0-9A-Za-z]+)\s*[,:]?\s*(.*)$", re.S | re.I)


# ---------------------------------------------------------------- 상태
class AgentState(TypedDict, total=False):
    question: str
    req_id: str
    as_of: str
    as_of_reason: str
    route: str
    blocked: bool
    answer: str
    judgment: dict | None
    decision: dict | None
    contexts: Annotated[list[dict], operator.add]
    trace: Annotated[list[dict], operator.add]


# (리팩토링) step → src/shared/trace.py
# (리팩토링) 도구(기준일 고정)·프롬프트 → src/agents/brains.py, src/agents/prompts.py
# (리팩토링) LLM 부분(Brains, llm_brains) → src/agents/brains.py
# (리팩토링) 도구 결과 → trace/contexts (_law_contexts, _msds_context, contexts_from_tool, collect) → src/workflows/evidence.py
# (리팩토링) 판정 사후 검증·답변 문구 (sanitize_judgment, format_judgment) → src/agents/judgment.py


# ---------------------------------------------------------------- 그래프
def build_graph(brains: Brains | None = None, checkpointer=None):
    brains_ref = {"b": brains}

    def B() -> Brains:
        if brains_ref["b"] is None:
            brains_ref["b"] = llm_brains()
        return brains_ref["b"]

    def input_guard(state: AgentState):
        g = guardrails.check_input(state["question"])
        out = "통과" if not g.blocked else f"차단({', '.join(g.kinds)})"
        upd = {"trace": [step("input_guard", state["question"], out)], "blocked": g.blocked}
        if g.blocked:
            upd["answer"] = g.message
        return upd

    def supervisor(state: AgentState):
        as_of, why = extract_as_of(state["question"])
        r = B().route(state["question"])
        upd = {"as_of": as_of.isoformat(), "as_of_reason": why, "route": r.agent,
               "trace": [step("select_law_version", state["question"], f"기준일 {as_of.isoformat()} ({why})"),
                         step("supervisor", state["question"], f"{r.agent}: {r.reason}")]}
        if r.agent == "out_of_scope":
            upd["answer"] = OUT_OF_SCOPE_MESSAGE
        return upd

    def sub_agent(name: str):
        def node(state: AgentState):
            as_of = date.fromisoformat(state["as_of"])
            msgs = B().react(name, state["question"], as_of)
            trace, contexts = collect(msgs, as_of)
            final = next((_text(m) for m in reversed(msgs) if isinstance(m, AIMessage) and _text(m).strip()), "")
            upd = {"trace": trace + [step(f"{name}_agent", state["question"], final)], "contexts": contexts}
            if name != "revision":
                upd["answer"] = final or "도구 결과로 답을 찾지 못했습니다."
                return upd
            j = B().judge(state["question"], msgs, as_of)
            # (기존 코드) LLM 판정을 그대로 사용 — 1차 평가 16번에서 도구 결과에 없는 항목을 만들어 내 사후 검증 추가
            # upd["judgment"] = j.model_dump()
            # upd["trace"] = upd["trace"] + [step("revision_judgment", "RevisionJudgment", j.model_dump())]
            j, removed = sanitize_judgment(j, msgs)
            upd["judgment"] = j.model_dump()
            upd["trace"] = upd["trace"] + [step("revision_judgment", "RevisionJudgment", j.model_dump(), limit=20000)]
            if removed:
                upd["trace"] = upd["trace"] + [step("judgment_check", "assess_update 대조", removed)]
            upd["answer"] = (format_judgment(j, state["req_id"], pending=True) if j.revision_needed
                             else (final or format_judgment(j, state["req_id"], pending=False)))
            return upd
        return node

    def approval(state: AgentState):
        j = RevisionJudgment(**state["judgment"])
        decision = interrupt({"req_id": state["req_id"], "draft": j.draft})
        d = decision.get("decision")
        # (기존 코드) 승인 시 초안 확정 문구만 돌려줌 — 승인된 변경을 제품 MSDS에 반영하도록 교체 (2026-11-12, (나)안)
        # if d == "approve":
        #     ans = (f"{state['req_id']} 승인 완료: 개정 초안이 확정되었습니다.\n\n" + format_judgment(j, state["req_id"], False)
        #            + "\n\n공단 제출은 자동으로 하지 않습니다. 확정본으로 담당자가 직접 제출하세요.")
        # else:
        if d == "approve":
            # (기존 코드) from src import msds_revision
            from src.revision import msds_apply as msds_revision

            results = msds_revision.apply(state["req_id"], state["question"], state["judgment"],
                                          decision.get("inputs") or {})
            applied = any(r["changes"] for r in results)
            ans = (f"{state['req_id']} 승인 완료: 개정 초안이 확정되었고"
                   + (" 제품 MSDS에 반영했습니다." if applied else ", 제품 MSDS에서 바꿀 내용은 없었습니다.") + "\n\n"
                   + msds_revision.render_result(results) + "\n\n" + format_judgment(j, state["req_id"], False)
                   + "\n\n공단 제출은 자동으로 하지 않습니다. 확정본으로 담당자가 직접 제출하세요.")
            return {"decision": decision, "answer": ans,
                    "trace": [step("hitl_decision", state["req_id"], decision),
                              step("msds_apply", state["req_id"], results, limit=6000)]}
        else:
            reason = decision.get("reason") or "사유 없음"
            ans = f"{state['req_id']} 반려: 개정 초안을 확정하지 않았습니다. 사유: {reason}"
        return {"decision": decision, "answer": ans,
                "trace": [step("hitl_decision", state["req_id"], decision)]}

    # (기존 코드) 답변 마스킹만 — 승인·마스킹·거절 안내의 출처인 서비스 정책을 근거(contexts)로 붙이도록 교체
    # def output_guard(state: AgentState):
    #     masked, applied = guardrails.mask_output(state.get("answer", ""))
    #     return {"answer": masked,
    #             "trace": [step("output_guard", "answer", "마스킹: " + (", ".join(applied) if applied else "없음"))]}
    def output_guard(state: AgentState):
        # (기존 코드) from src import context_text
        from src.workflows import evidence_text as context_text

        masked, applied = guardrails.mask_output(state.get("answer", ""))
        upd = {"answer": masked,
               "trace": [step("output_guard", "answer", "마스킹: " + (", ".join(applied) if applied else "없음"))]}
        have = {c["doc_id"] for c in state.get("contexts", [])}
        if context_text.POLICY_DOC_ID not in have and (applied or context_text.needs_policy(masked)):
            upd["contexts"] = [{"doc_id": context_text.POLICY_DOC_ID, "text": context_text.service_policy_text()}]
        return upd

    g = StateGraph(AgentState)
    g.add_node("input_guard", input_guard)
    g.add_node("supervisor", supervisor)
    for name in ("regulation", "impact", "revision"):
        g.add_node(f"{name}_agent", sub_agent(name))
    g.add_node("approval", approval)
    g.add_node("output_guard", output_guard)

    g.add_edge(START, "input_guard")
    g.add_conditional_edges("input_guard", lambda s: "output_guard" if s.get("blocked") else "supervisor",
                            ["output_guard", "supervisor"])
    g.add_conditional_edges("supervisor",
                            lambda s: "output_guard" if s["route"] == "out_of_scope" else f"{s['route']}_agent",
                            ["regulation_agent", "impact_agent", "revision_agent", "output_guard"])
    g.add_edge("regulation_agent", "output_guard")
    g.add_edge("impact_agent", "output_guard")
    g.add_conditional_edges("revision_agent",
                            lambda s: "approval" if (s.get("judgment") or {}).get("revision_needed") else "output_guard",
                            ["approval", "output_guard"])
    g.add_edge("approval", "output_guard")
    g.add_edge("output_guard", END)
    return g.compile(checkpointer=checkpointer)


# (리팩토링) sqlite_checkpointer·new_req_id → src/memory/checkpointer.py


def parse_decision(question: str) -> tuple[str, str, str] | None:
    """'승인 REQ-1A2B' / '반려 REQ-1A2B 사유' → (approve|reject, REQ-ID, 사유)."""
    m = DECISION.match(question)
    if not m:
        return None
    return ("approve" if m[1] == "승인" else "reject"), m[2].upper(), m[3].strip()


def _response(state: dict) -> dict:
    return {"answer": state.get("answer", ""),
            "contexts": [{"doc_id": c["doc_id"], "text": c["text"]} for c in state.get("contexts", [])],
            "trace": [{"step": t["step"], "input": t["input"], "output": t["output"]} for t in state.get("trace", [])]}


def run_query(question: str, graph) -> dict:
    """POST /query 한 번 처리. 승인/반려 명령이면 해당 REQ의 그래프를 재개합니다.
    '법령 갱신' 명령이면 법령을 다시 가져옵니다(UI '법령 가져오기' 버튼, src/regulation/refresh.py)."""
    # (기존 코드) from src import law_refresh
    from src.regulation import refresh as law_refresh

    if law_refresh.is_refresh_command(question):
        return law_refresh.refresh()
    cmd = parse_decision(question)
    if cmd:
        decision, req_id, reason = cmd
        config = {"configurable": {"thread_id": req_id}}
        snap = graph.get_state(config)
        if not snap.next or "approval" not in snap.next:
            return {"answer": f"{req_id}에 해당하는 승인 대기 건이 없습니다. 요청 번호를 확인해 주세요.",
                    "contexts": [], "trace": [step("hitl_decision", question, "대기 건 없음")]}
        if decision == "reject" and not reason:
            return {"answer": f"반려하려면 사유를 함께 보내 주세요. 예: '반려 {req_id} 함유량 재확인 필요'",
                    "contexts": [], "trace": [step("hitl_decision", question, "반려 사유 없음")]}
        # (기존 코드) 입력값 확인 없이 바로 재개 — '확인 필요' 항목은 대체 표기를 받아야 승인되도록 교체 ((나)안)
        # graph.invoke(Command(resume={"decision": decision, "reason": reason}), config)
        # return _response(graph.get_state(config).values)
        inputs: dict[str, str] = {}
        if decision == "approve":
            # (기존 코드) from src import msds_revision
            from src.revision import msds_apply as msds_revision

            v = snap.values
            required = msds_revision.required_inputs(msds_revision.request_ops(v.get("question", ""), v.get("judgment")))
            inputs = msds_revision.parse_inputs(reason)
            msg = msds_revision.missing_inputs_message(req_id, required, inputs)
            if msg:
                return {"answer": msg, "contexts": [],
                        "trace": [step("hitl_decision", question, "대체 표기 입력 필요"),
                                  step("required_inputs", req_id, required, limit=6000)]}
        graph.invoke(Command(resume={"decision": decision, "reason": reason, "inputs": inputs}), config)
        return _response(graph.get_state(config).values)

    req_id = new_req_id()
    config = {"configurable": {"thread_id": req_id}, "run_name": "msds-query",
              "metadata": {"req_id": req_id}, "recursion_limit": 30}
    graph.invoke({"question": question, "req_id": req_id}, config)
    snap = graph.get_state(config)
    values = dict(snap.values)
    if snap.next and "approval" in snap.next:      # interrupt → 승인 대기 응답 (출력 가드 직접 적용)
        masked, applied = guardrails.mask_output(values.get("answer", ""))
        values["answer"] = masked
        values["trace"] = list(values.get("trace", [])) + [
            step("hitl_interrupt", req_id, "담당자 승인 대기"),
            step("output_guard", "answer", "마스킹: " + (", ".join(applied) if applied else "없음"))]
        # (추가) 승인 대기 안내('확정·제출은 승인 후에만')의 근거로 서비스 정책을 붙임
        # (기존 코드) from src import context_text
        from src.workflows import evidence_text as context_text

        if all(c["doc_id"] != context_text.POLICY_DOC_ID for c in values.get("contexts", [])):
            values["contexts"] = list(values.get("contexts", [])) + [
                {"doc_id": context_text.POLICY_DOC_ID, "text": context_text.service_policy_text()}]
    return _response(values)

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

from __future__ import annotations

import json
import operator
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Callable, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src import guardrails, retriever, tools
from src.config import CHECKPOINT_DB
from src.dates import extract_as_of
from src.schemas import RevisionJudgment, Route

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


def step(name: str, inp: Any, out: Any) -> dict[str, str]:
    def s(x):
        return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    return {"step": name, "input": s(inp)[:1500], "output": s(out)[:1500]}


# ---------------------------------------------------------------- 도구 (기준일 고정) 와 프롬프트
def _dumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)


def make_tools(as_of: date) -> dict[str, list]:
    """서브 에이전트별 도구 묶음. 모든 도구는 JSON 문자열을 돌려줍니다."""
    from langchain_core.tools import StructuredTool

    def wrap(fn):
        return StructuredTool.from_function(func=_typed(fn), name=fn.__name__, description=(fn.__doc__ or "").strip())

    def search_law(query: str) -> str:
        """법령 조문(산업안전보건법·시행규칙·화학물질관리법)을 검색합니다. 질문 기준일에 시행 중인 조문(applicable)과
        시행 예정 조문(upcoming)을 나눠 돌려줍니다. 판정 근거는 applicable만 씁니다."""
        return _dumps(tools.search_law(query, as_of=as_of.isoformat()))

    law = StructuredTool.from_function(func=search_law)
    by_name = {fn.__name__: wrap(fn) for fn in (
        tools.get_msds, tools.list_products, tools.find_products_by_cas, tools.find_products_by_term,
        tools.get_regulation_update, tools.list_regulation_updates, tools.check_resubmission,
        tools.assess_update, tools.get_substance, tools.classify_mixture)}
    # MSDS DB 도구는 MCP 서버를 거쳐 호출합니다(패턴 5). MSDS_USE_MCP=0 이거나 연결에 실패하면 로컬 도구 그대로.
    if use_mcp():
        from src.mcp_client import get_mcp_tools

        remote = get_mcp_tools() or {}
        by_name.update({k: v for k, v in remote.items() if k in by_name})
    impact = list(by_name.values()) + [law]
    return {
        "regulation": [law, by_name["get_regulation_update"], by_name["list_regulation_updates"]],
        "impact": impact,
        "revision": impact,
    }


def use_mcp() -> bool:
    import os
    return os.getenv("MSDS_USE_MCP", "1") != "0"


def _typed(fn: Callable) -> Callable:
    """원래 함수의 시그니처·설명을 유지하면서 결과를 JSON 문자열로 바꾸는 래퍼."""
    import functools

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        return _dumps(fn(*args, **kwargs))
    return inner


COMMON_RULES = """
공통 규칙:
- 질문 기준일은 {as_of}입니다. 법령은 기준일에 시행 중인 조문으로 판단하고, search_law 결과의 upcoming(시행 예정) 조문은
  판정 근거로 쓰지 말고 내용이 다르면 "시행 예정(YYYY-MM-DD 시행)"으로 따로 알리세요.
- 조문 번호와 내용, 제품 정보, 수치는 도구 결과에 있는 것만 씁니다. 도구 결과로 확인하지 못한 것은 "확인 필요"로 표시하고 지어내지 마세요.
- 근거 조문은 '시행규칙 제159조제1항제2호'처럼 조·항·호까지 적습니다.
- 영업비밀 성분의 실제 명칭·CAS·정확한 함유량은 말하지 않습니다. 담당자 연락처는 마스킹된 값만 씁니다.
- MSDS 개정본의 확정·제출은 담당자 승인 후에만 가능합니다. "제출 완료"라고 말하지 마세요.
- 결론을 먼저 한두 문장으로 쓰고, 이어서 근거를 번호 목록(1. 2. 3.)으로 정리합니다. 표·이모지·제목 기호(#)는 쓰지 않습니다.
- 질문에 답하는 데 필요한 도구만 부르고, 묻지 않은 내용(다른 변경 사건 목록 등)은 덧붙이지 않습니다. 한국어로 답합니다.
"""

PROMPTS = {
    "regulation": "당신은 MSDS 관련 법령(산업안전보건법·시행규칙·화학물질관리법) 안내 담당입니다. "
                  "반드시 search_law로 조문을 찾아 원문에 근거해 답하세요. 질문이 법령 개정 이력(정의 삭제, 개정 시행일)을 "
                  "물을 때만 list_regulation_updates / get_regulation_update로 등록된 법령 개정 사건을 확인하세요." + COMMON_RULES,
    "impact": "당신은 제품 MSDS 영향 분석 담당입니다. 제품·성분·CAS·변경 사건 질문은 도구로 확인해 답하세요. "
              "없는 제품(P-번호)이나 변경 사건(U-번호)이면 list_products / list_regulation_updates로 등록된 목록을 안내하세요. "
              "성분 함유량을 물으면 제품별 함유량을 함께 적으세요. 특정 성분과 관련된 규제 변경을 물으면 "
              "list_regulation_updates로 사건을 찾고, 법령 개정 사건은 assess_update로 실제 영향 제품을 확인한 뒤 "
              "find_products_by_cas로 그 성분이 든 제품을 찾아 '영향 제품'과 '성분은 있지만 영향 없는 제품(이유)'을 구분해 답하세요. "
              "사내 변경 사건(배합·제품명 변경)은 법령 개정으로 소개하지 마세요." + COMMON_RULES,
    "revision": "당신은 MSDS 개정 판정 담당입니다. 변경 사건(U-번호)마다 get_regulation_update와 assess_update를 "
                "한 번씩 부르세요(가능하면 한 번에 함께). assess_update 결과에 재제출 판정과 근거 doc_id가 들어 있으므로 "
                "check_resubmission·search_law는 판정이 불분명할 때만 씁니다. 바꿀 값(변경 전 값)이 필요하면 get_msds로 해당 항목만 "
                "조회하세요. 변경 사건이 여러 개면 사건별로 나눠 확인하세요. 마지막 답변은 세 줄 이내로 요약하세요." + COMMON_RULES,
}

ROUTER_PROMPT = """MSDS 개정 지원 에이전트의 Supervisor입니다. 질문을 맡을 서브 에이전트를 고르세요.
- regulation: 법령 조문·제도 자체를 묻는 질문 (예: 재제출 대상 항목, 제출 시기, 게시 장소, 유독물질 정의가 아직 있는지)
- impact: 제품 MSDS·성분·CAS 조회, 어떤 제품에 무엇이 들었는지, 규제 변경이 어떤 제품과 관련 있는지 둘러보는 질문
  (예: 톨루엔이 든 제품, P-006에 벤젠이 있는지, 담당자 연락처, 톨루엔 관련 바뀐 규제)
- revision: 특정 변경 사건(U-번호)이나 제품 변경 때문에 MSDS를 고치거나 다시 제출해야 하는지 판정하는 질문
  (예: U-02 반영 후 P-002 재제출?, U-01 반영하려면 어떤 제품을 고쳐야?, U-04처럼 제품명만 바뀌어도 재제출?)
- out_of_scope: MSDS·산업안전보건법·화학물질관리법과 무관한 질문"""

JUDGE_PROMPT = """아래 도구 결과만 근거로 MSDS 개정 판정을 구조화하세요.
- revision_needed: 고쳐야 할 제품이 하나라도 있으면 true. 변경 사건이 없거나 영향 제품이 없으면 false.
- products: 영향 제품만. sections는 MSDS 항목 번호, changes는 '항목: 변경 전 → 변경 후' 형식(도구 결과의 값 그대로),
  resubmission_required는 check_resubmission/assess_update 결과의 resubmission_required 그대로.
- reasons: 조·항·호를 포함한 판정 이유 (예: '제품명 변경 없이 구성성분 함유량만 바뀌어 시행규칙 제159조제1항제2호에 해당').
  15번(법적 규제현황)만 바뀌는 경우는 시행규칙 제159조제1항 각 호에 해당하지 않아 재제출 대상이 아님을 적으세요.
- legal_basis: 도구 결과에 나온 doc_id만 (law:..., msds:P-...).
- draft: 담당자 검토용 개정 초안. 제품별로 '[P-002] 3번 구성성분: 톨루엔 10~20% → 25~35%' 처럼 한 줄씩.
  도구 결과로 정할 수 없는 값(예: 현행 화학물질관리법 구분)은 '확인 필요'로 적으세요.
- 영업비밀 성분의 실제 명칭·CAS·함유량은 쓰지 마세요.
- 영향 제품과 항목은 assess_update 결과의 affected 에 있는 것만 씁니다. 질문에 나온 제품이 어떤 변경 사건의 영향을
  받지 않으면 reasons 에 '<사건>은 <제품>에 영향 없음(이유)'을 적으세요 (예: 'U-01은 P-002에 영향 없음: 15번에 화학물질관리법 표기 없음').

질문 기준일: {as_of}
질문: {question}

도구 결과:
{tool_results}"""


# ---------------------------------------------------------------- LLM 부분 (테스트에서 교체)
@dataclass
class Brains:
    route: Callable[[str], Route]
    react: Callable[[str, str, date], list[BaseMessage]]
    judge: Callable[[str, list[BaseMessage], date], RevisionJudgment]


def llm_brains() -> Brains:
    from langchain.agents import create_agent
    from langchain_core.prompts import ChatPromptTemplate

    from src.llm import get_chat_model

    model = get_chat_model(max_tokens=2048)
    router = (ChatPromptTemplate.from_messages([("system", ROUTER_PROMPT), ("human", "{question}")])
              | model.with_structured_output(Route)).with_retry(stop_after_attempt=2)
    judge_chain = (ChatPromptTemplate.from_messages([("human", JUDGE_PROMPT)])
                   | model.with_structured_output(RevisionJudgment)).with_retry(stop_after_attempt=2)

    def route(question: str) -> Route:
        return router.invoke({"question": question})

    def react(agent: str, question: str, as_of: date) -> list[BaseMessage]:
        graph = create_agent(model, make_tools(as_of)[agent],
                             system_prompt=PROMPTS[agent].format(as_of=as_of.isoformat()), name=f"{agent}_agent")
        out = graph.invoke({"messages": [HumanMessage(question)]}, {"recursion_limit": 20})
        return out["messages"]

    def judge(question: str, messages: list[BaseMessage], as_of: date) -> RevisionJudgment:
        results = "\n\n".join(f"[{m.name}] {m.content}" for m in messages if isinstance(m, ToolMessage))
        return judge_chain.invoke({"question": question, "as_of": as_of.isoformat(),
                                   "tool_results": results or "(도구 결과 없음)"})

    return Brains(route=route, react=react, judge=judge)


# ---------------------------------------------------------------- 도구 결과 → trace / contexts
def _text(msg: BaseMessage) -> str:
    c = msg.content
    if isinstance(c, str):
        return c
    return "".join(b.get("text", "") for b in c if isinstance(b, dict))


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


def _msds_context(pid: str, sections: list[str] | None = None) -> dict:
    view = tools.get_msds(pid, sections)
    return {"doc_id": f"msds:{pid}", "text": _dumps(view)}


def contexts_from_tool(name: str, args: dict, result: Any, as_of: date) -> list[dict]:
    """도구 호출 하나의 결과에서 근거 문서를 뽑습니다(API Spec contexts 형식)."""
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
            upd["trace"] = upd["trace"] + [step("revision_judgment", "RevisionJudgment", j.model_dump())]
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
        if d == "approve":
            ans = (f"{state['req_id']} 승인 완료: 개정 초안이 확정되었습니다.\n\n" + format_judgment(j, state["req_id"], False)
                   + "\n\n공단 제출은 자동으로 하지 않습니다. 확정본으로 담당자가 직접 제출하세요.")
        else:
            reason = decision.get("reason") or "사유 없음"
            ans = f"{state['req_id']} 반려: 개정 초안을 확정하지 않았습니다. 사유: {reason}"
        return {"decision": decision, "answer": ans,
                "trace": [step("hitl_decision", state["req_id"], decision)]}

    def output_guard(state: AgentState):
        masked, applied = guardrails.mask_output(state.get("answer", ""))
        return {"answer": masked,
                "trace": [step("output_guard", "answer", "마스킹: " + (", ".join(applied) if applied else "없음"))]}

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


def sqlite_checkpointer(path=CHECKPOINT_DB):
    from langgraph.checkpoint.sqlite import SqliteSaver
    return SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))


def new_req_id() -> str:
    return "REQ-" + secrets.token_hex(2).upper()


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
    '법령 갱신' 명령이면 법령을 다시 가져옵니다(UI '법령 가져오기' 버튼, src/law_refresh.py)."""
    from src import law_refresh

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
        graph.invoke(Command(resume={"decision": decision, "reason": reason}), config)
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
    return _response(values)

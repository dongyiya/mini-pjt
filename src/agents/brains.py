"""서브 에이전트 실행 로직 — LLM 부분(라우터·ReAct·판정)과 에이전트별 도구 묶음.

(2026-11-12 리팩토링: src/agent.py 의 make_tools·use_mcp·_typed·Brains·llm_brains 를 그대로 옮김)
LLM이 하는 부분(route / react / judge)은 Brains 로 묶어 테스트에서 가짜로 바꿔 끼울 수 있습니다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Callable

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

from src.agents.prompts import JUDGE_PROMPT, PROMPTS, ROUTER_PROMPT
from src.agents.schemas import RevisionJudgment, Route
from src.shared.trace import dumps as _dumps
from src.tools import msds_tools as tools


# ---------------------------------------------------------------- 도구 (기준일 고정)
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
        # (기존 코드) from src.mcp_client import get_mcp_tools
        from src.tools.mcp_client import get_mcp_tools

        remote = get_mcp_tools() or {}
        by_name.update({k: v for k, v in remote.items() if k in by_name})
    impact = list(by_name.values()) + [law]
    return {
        "regulation": [law, by_name["get_regulation_update"], by_name["list_regulation_updates"]],
        "impact": impact,
        "revision": impact,
    }


def use_mcp() -> bool:
    return os.getenv("MSDS_USE_MCP", "1") != "0"


def _typed(fn: Callable) -> Callable:
    """원래 함수의 시그니처·설명을 유지하면서 결과를 JSON 문자열로 바꾸는 래퍼."""
    import functools

    @functools.wraps(fn)
    def inner(*args, **kwargs):
        return _dumps(fn(*args, **kwargs))
    return inner


# ---------------------------------------------------------------- LLM 부분 (테스트에서 교체)
@dataclass
class Brains:
    route: Callable[[str], Route]
    react: Callable[[str, str, date], list[BaseMessage]]
    judge: Callable[[str, list[BaseMessage], date], RevisionJudgment]


def llm_brains() -> Brains:
    from langchain.agents import create_agent
    from langchain_core.prompts import ChatPromptTemplate

    # (기존 코드) from src.llm import get_chat_model
    from src.shared.llm import get_chat_model

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

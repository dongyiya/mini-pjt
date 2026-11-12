"""trace 단계와 메시지 텍스트 공통 함수 (2026-11-12 리팩토링: src/agent.py 의 step·_text 를 옮김)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import BaseMessage


def dumps(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)


# (기존 코드) 출력 길이 1500자 고정 — UI 영향 분석 표가 revision_judgment JSON 전체를 읽도록 limit 인자 추가
# def step(name: str, inp: Any, out: Any) -> dict[str, str]:
#     def s(x):
#         return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
#     return {"step": name, "input": s(inp)[:1500], "output": s(out)[:1500]}
def step(name: str, inp: Any, out: Any, limit: int = 1500) -> dict[str, str]:
    """API Spec trace 한 단계 {step, input, output}."""
    def s(x):
        return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    return {"step": name, "input": s(inp)[:1500], "output": s(out)[:limit]}


def message_text(msg: BaseMessage) -> str:
    """LangChain 메시지 본문을 문자열로 (블록 목록이면 text 블록만 이어 붙임)."""
    c = msg.content
    if isinstance(c, str):
        return c
    return "".join(b.get("text", "") for b in c if isinstance(b, dict))

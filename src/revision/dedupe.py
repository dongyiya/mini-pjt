"""승인 요청 중복 방지·정리 (2026-11-12 추가).

중복 기준: 승인하면 제품 MSDS에 **똑같은 변경**이 일어나는 승인 대기 건.
  - 비교 값(signature)은 승인 시 반영할 변경 작업(msds_apply.request_ops)입니다. 질문 문장이 달라도
    (예: 'U-02 반영 후 P-002 재제출?'과 'U-01·U-02 모두 반영하면 P-002는?') 반영 내용이 같으면 중복입니다.
  - 변경 작업을 만들 수 없는 판정이면 판정의 제품·항목·변경 내용으로 비교합니다.

- 새 질문: 같은 변경의 승인 대기 건이 이미 있으면 새 요청을 만들지 않고(새 thread 는 '중복 요청'으로 닫음)
  기존 요청 번호로 안내합니다 → src/workflows/graph.py run_query
- 기존 중복: 같은 변경끼리 가장 최근 건 하나만 남기고 나머지를 '중복 요청' 사유로 반려 처리합니다(기록은 남음).
  MSDS는 바뀌지 않습니다 → close_existing_duplicates(), 화면은 closed_duplicate_ids()로 브라우저 목록에서도 지움
"""

from __future__ import annotations

import json
from typing import Any

from langgraph.types import Command

DUP_PREFIX = "중복 요청"


def signature(question: str, judgment: dict | None) -> str:
    """승인 요청의 비교 값 — 반영할 변경 작업(제품·항목·전/후 값)."""
    from src.revision import msds_apply

    ops = msds_apply.request_ops(question or "", judgment)
    if any(ops.values()):
        body: Any = {pid: ops[pid] for pid in sorted(ops) if ops[pid]}
    else:
        body = sorted(
            (p.get("product_id", ""), sorted(p.get("sections", [])), sorted(p.get("changes", [])))
            for p in (judgment or {}).get("products", []))
    return json.dumps(body, ensure_ascii=False, sort_keys=True)


def _thread_ids(checkpointer) -> list[str]:
    ids: list[str] = []
    for t in checkpointer.list(None):
        tid = t.config["configurable"]["thread_id"]
        if tid not in ids:
            ids.append(tid)
    return ids


def pending_with_signature(graph) -> list[dict]:
    """승인 대기 중인 요청 [{id, createdAt, signature}] (최근 것부터)."""
    out = []
    for tid in _thread_ids(graph.checkpointer):
        snap = graph.get_state({"configurable": {"thread_id": tid}})
        if not snap.next or "approval" not in snap.next:
            continue
        v = snap.values
        out.append({"id": tid, "createdAt": snap.created_at or "",
                    "signature": signature(v.get("question", ""), v.get("judgment"))})
    out.sort(key=lambda r: r["createdAt"], reverse=True)
    return out


def find_pending_duplicate(graph, req_id: str, question: str, judgment: dict | None) -> str | None:
    """req_id 와 같은 변경의 다른 승인 대기 건이 있으면 그 요청 번호(가장 최근 것)."""
    sig = signature(question, judgment)
    for p in pending_with_signature(graph):
        if p["id"] != req_id and p["signature"] == sig:
            return p["id"]
    return None


def close_as_duplicate(graph, req_id: str, kept_id: str) -> None:
    """승인 대기 건을 '중복 요청' 사유로 반려 처리합니다(MSDS 변경 없음, 기록은 체크포인트에 남음)."""
    graph.invoke(Command(resume={"decision": "reject", "reason": f"{DUP_PREFIX}: {kept_id}와 같은 변경", "inputs": {}}),
                 {"configurable": {"thread_id": req_id}})


def close_existing_duplicates(graph) -> list[tuple[str, str]]:
    """같은 변경의 승인 대기 건 중 가장 최근 건만 남기고 나머지를 닫습니다. [(닫은 건, 남긴 건)]"""
    kept: dict[str, str] = {}
    closed: list[tuple[str, str]] = []
    for p in pending_with_signature(graph):          # 최근 것부터 → 처음 본 것이 남길 건
        if p["signature"] not in kept:
            kept[p["signature"]] = p["id"]
            continue
        close_as_duplicate(graph, p["id"], kept[p["signature"]])
        closed.append((p["id"], kept[p["signature"]]))
    return closed


def closed_duplicate_ids(graph) -> list[str]:
    """'중복 요청'으로 닫힌 요청 번호 — 화면이 브라우저에 남은 같은 건을 지우는 데 씁니다."""
    out = []
    for tid in _thread_ids(graph.checkpointer):
        v = graph.get_state({"configurable": {"thread_id": tid}}).values
        if str((v.get("decision") or {}).get("reason", "")).startswith(DUP_PREFIX):
            out.append(tid)
    return out

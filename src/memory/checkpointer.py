"""HITL 대화 상태 저장 — SqliteSaver 체크포인터와 승인 요청 번호(thread_id=REQ-xxxx).

(2026-11-12 리팩토링: src/agent.py 의 sqlite_checkpointer·new_req_id 를 그대로 옮김)
"""

from __future__ import annotations

import secrets
import sqlite3

from src.shared.config import CHECKPOINT_DB


def sqlite_checkpointer(path=CHECKPOINT_DB):
    from langgraph.checkpoint.sqlite import SqliteSaver
    return SqliteSaver(sqlite3.connect(str(path), check_same_thread=False))


def new_req_id() -> str:
    return "REQ-" + secrets.token_hex(2).upper()

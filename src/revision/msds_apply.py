"""승인된 개정 초안을 제품 MSDS(data/msds/products.json)에 반영합니다. (2026-11-12 사용자 요청, (나)안)

- 반영 내용: 승인 요청(REQ)의 질문에 나온 변경 사건(U-번호)과 판정 제품에 대한 변경 작업(op, src/revision/preview.py update_ops)
- '확인 필요' 항목(op = replace, needs_input)은 담당자가 대체 표기를 입력해야 승인됩니다.
  입력 형식(승인 문장 다음 줄부터): `P-001 15번: 사고대비물질(톨루엔)`
- 반영할 때 개정판 번호 +1, 개정일 = 승인일. 바꾸기 전 제품 MSDS 는 data/msds/history/ 에 보관하고,
  data/msds/revision_log.json 에 개정 기록을 남깁니다.
- 이미 반영돼 값이 다르면(같은 사건을 두 번 승인 등) 그 작업은 건너뛰고 알립니다.
- 원래 데모 데이터로 되돌리기: ./run.sh reset-msds
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import date
from typing import Any

# (기존 코드) from src import tools
from src.tools import msds_tools as tools
# (기존 코드) from src.config import MSDS_PATH, today
from src.shared.config import MSDS_PATH, today

HISTORY_DIR = MSDS_PATH.parent / "history"
LOG_PATH = MSDS_PATH.parent / "revision_log.json"
BASELINE_PATH = MSDS_PATH.parent / "products.baseline.json"   # 원래 데모 데이터 (평가셋이 가정한 상태)


def reset_to_baseline() -> bool:
    """승인 반영 시험으로 바뀐 제품 MSDS를 원래 데모 데이터로 되돌립니다. 바뀐 게 있었으면 True.

    사용자 결정(2026-11-12): 승인 → MSDS 반영은 시험 기능이므로, 평가 전에는 항상 원래 데이터로 되돌린 뒤 평가합니다.
    (evaluation/run_eval.py 가 평가 시작 때 호출, ./run.sh reset-msds 로도 실행)
    """
    import shutil

    changed = MSDS_PATH.read_bytes() != BASELINE_PATH.read_bytes() or HISTORY_DIR.exists() or LOG_PATH.exists()
    if changed:
        with _lock:
            shutil.copyfile(BASELINE_PATH, MSDS_PATH)
            shutil.rmtree(HISTORY_DIR, ignore_errors=True)
            LOG_PATH.unlink(missing_ok=True)
            tools._products.cache_clear()
            _clear_guardrail_caches()
    return changed
INPUT_LINE = re.compile(r"(P-\d{3})\s*(\d+)\s*번\s*[:：]\s*(.+)")
_lock = threading.Lock()


def request_ops(question: str, judgment: dict | None) -> dict[str, list[dict]]:
    """승인 요청 하나에 해당하는 제품별 변경 작업."""
    # (기존 코드) from src.revision_preview import update_ops
    from src.revision.preview import update_ops

    uids = list(dict.fromkeys(u.upper() for u in re.findall(r"U-\d+", question, re.I)))
    pids = [p["product_id"] for p in (judgment or {}).get("products", [])]
    out: dict[str, list[dict]] = {}
    for uid in uids:
        for pid, ops in update_ops(uid).items():
            if not pids or pid in pids:
                out.setdefault(pid, []).extend(ops)
    return out


def required_inputs(ops_by_pid: dict[str, list[dict]]) -> list[dict]:
    return [{"key": f"{pid}:{op['section']}", "product_id": pid, "section": op["section"], "law": op.get("law", ""),
             "value": op["value"], "suggest": op.get("suggest", ""), "reason": op.get("reason", "")}
            for pid, ops in ops_by_pid.items() for op in ops if op.get("needs_input")]


def parse_inputs(text: str) -> dict[str, str]:
    """'P-001 15번: 사고대비물질(톨루엔)' 줄들 → {'P-001:15': '사고대비물질(톨루엔)'}"""
    return {f"{m[1].upper()}:{m[2]}": m[3].strip() for m in INPUT_LINE.finditer(text)}


def split_items(text: str) -> list[str]:
    """괄호 밖의 쉼표로만 나눕니다: '인체만성유해성물질(벤젠), 사고대비물질(톨루엔)' → 2개."""
    items, depth, cur = [], 0, ""
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            items.append(cur.strip())
            cur = ""
        else:
            cur += ch
    items.append(cur.strip())
    return [i for i in items if i]


def missing_inputs_message(req_id: str, required: list[dict], given: dict[str, str]) -> str | None:
    missing = [r for r in required if not given.get(r["key"])]
    if not missing:
        return None
    lines = [f"{req_id}를 승인하려면 '확인 필요' 항목의 대체 표기를 입력해야 합니다.", ""]
    for r in missing:
        lines += [f"- {r['product_id']} {r['section']}번 {r['law']}: 기존 '{r['value']}'",
                  f"  추천 문구: {r['suggest']}", f"  사유: {r['reason']}"]
    lines += ["", "다음처럼 승인 문장 아래 줄에 적어 보내 주세요(추천 문구를 그대로 써도 됩니다):", f"승인 {req_id}"]
    lines += [f"{r['product_id']} {r['section']}번: {r['suggest']}" for r in missing]
    return "\n".join(lines)


def _apply_one(p: dict, ops: list[dict], inputs: dict[str, str]) -> tuple[list[str], list[str]]:
    done, skipped = [], []
    for op in ops:
        sec = op.get("section")
        if op["op"] == "set" and op.get("field") == "name":
            if p["name"] != op["before"]:
                skipped.append(f"1번 제품명: 현재 값이 '{p['name']}'라 건너뜀(이미 반영됐거나 값이 다름)")
                continue
            p["name"] = op["after"]
            done.append(f"1번 제품명: {op['before']} → {op['after']}")
        elif op["op"] == "component":
            comp = next((c for c in p["section3"] if c["name"] == op["name"]), None)
            if comp is None or comp.get(op["field"]) != op["before"]:
                skipped.append(f"3번 {op['name']}: 현재 값이 '{comp and comp.get(op['field'])}'라 건너뜀(이미 반영됐거나 값이 다름)")
                continue
            comp[op["field"]] = op["after"]
            done.append(f"3번 {op['name']} 함유량: {op['before']} → {op['after']}")
        elif op["op"] == "add":
            ghs = p.setdefault("section2", {}).setdefault("ghs", [])
            if op["value"] in ghs:
                skipped.append(f"2번 '{op['value']}': 이미 있어 건너뜀")
                continue
            ghs.append(op["value"])
            done.append(f"2번 유해성 분류 추가: {op['value']}")
        elif op["op"] in ("replace", "remove"):
            items = p.setdefault(f"section{sec}", {}).setdefault(op["law"], [])
            if op["value"] not in items:
                skipped.append(f"{sec}번 {op['law']} '{op['value']}': 이미 없어 건너뜀")
                continue
            new = split_items(inputs.get(f"{p['id']}:{sec}", "")) if op["op"] == "replace" else []
            new = [n for n in new if n != "해당 표기 없음"]
            rest = [i for i in items if i != op["value"] and i != "해당 표기 없음"]
            p[f"section{sec}"][op["law"]] = (rest + [n for n in new if n not in rest]) or ["해당 표기 없음"]
            done.append(f"{sec}번 {op['law']}: '{op['value']}' → " + (", ".join(new) if new else "삭제"))
    return done, skipped


def apply(req_id: str, question: str, judgment: dict | None, inputs: dict[str, str],
          on: date | None = None) -> list[dict]:
    """승인 요청을 MSDS에 반영하고 제품별 결과를 돌려줍니다."""
    on = on or today()
    ops_by_pid = request_ops(question, judgment)
    with _lock:
        doc = json.loads(MSDS_PATH.read_text(encoding="utf-8"))
        results = []
        for pid, ops in ops_by_pid.items():
            p = next((x for x in doc["products"] if x["id"] == pid), None)
            if p is None:
                continue
            before = json.loads(json.dumps(p, ensure_ascii=False))
            done, skipped = _apply_one(p, ops, inputs)
            r = {"product_id": pid, "name": p["name"], "changes": done, "skipped": skipped,
                 "from_rev": before["revision"]["no"], "to_rev": before["revision"]["no"], "archived": None}
            if done:
                p["revision"] = {"no": before["revision"]["no"] + 1, "date": on.isoformat()}
                r["to_rev"] = p["revision"]["no"]
                HISTORY_DIR.mkdir(parents=True, exist_ok=True)
                arch = HISTORY_DIR / f"{pid}_rev{before['revision']['no']}.json"
                arch.write_text(json.dumps(before, ensure_ascii=False, indent=2), encoding="utf-8")
                r["archived"] = arch.relative_to(MSDS_PATH.parent.parent.parent).as_posix()
            results.append(r)
        if any(r["changes"] for r in results):
            tmp = MSDS_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, MSDS_PATH)                        # 한 번에 바꿔 쓰기
            log = json.loads(LOG_PATH.read_text(encoding="utf-8")) if LOG_PATH.exists() else []
            log += [{"req_id": req_id, "product_id": r["product_id"], "from_rev": r["from_rev"], "to_rev": r["to_rev"],
                     "date": on.isoformat(), "changes": r["changes"], "archived": r["archived"]}
                    for r in results if r["changes"]]
            LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
            tools._products.cache_clear()
            _clear_guardrail_caches()
    return results


def _clear_guardrail_caches() -> None:
    # (기존 코드) from src import guardrails
    from src.guardrails import guard as guardrails

    for fn in (guardrails._products, guardrails._in_scope_re, guardrails._secret_terms, guardrails._contact_names):
        fn.cache_clear()


def render_result(results: list[dict]) -> str:
    if not results:
        return "MSDS 반영: 이 요청에 해당하는 변경 작업이 없어 MSDS는 바꾸지 않았습니다."
    lines = ["MSDS 반영 결과"]
    for r in results:
        if r["changes"]:
            lines.append(f"- {r['product_id']} {r['name']}: {r['from_rev']}판 → {r['to_rev']}판 "
                         f"(이전 판 보관: {r['archived']})")
            lines += [f"  · {c}" for c in r["changes"]]
        else:
            lines.append(f"- {r['product_id']} {r['name']}: 바꾼 내용 없음 ({r['from_rev']}판 유지)")
        lines += [f"  · 건너뜀: {s}" for s in r["skipped"]]
    return "\n".join(lines)

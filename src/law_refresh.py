"""법령 수동 갱신 — UI의 '법령 가져오기' 버튼.

API Spec을 바꾸지 않기 위해 별도 엔드포인트 없이 같은 POST /query 에 {"question": "법령 갱신"}을 보내면 실행합니다.
(2026-11-12 사용자 결정: '/query 명령' 방식)

1) 국가법령정보센터에서 대상 법령의 현행·시행예정 판을 다시 받아 data/laws 를 바꿔 씀 (scripts/collect_data.refresh_laws)
2) 갱신 전후 조문을 비교해 추가·변경·삭제된 조문을 알려 줌
3) 검색 인덱스(index/)를 다시 만들고 검색기 캐시를 비움 → 다음 질문부터 새 조문으로 검색
- LLM을 쓰지 않습니다(임베딩만). 동시에 두 번 실행되지 않도록 잠급니다.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Callable

from src import retriever
from src.config import LAW_DIR, get_settings, today

COMMAND = re.compile(r"^\s*법령\s*(갱신|가져오기|업데이트|수집|새로\s*고침)\s*(해\s*줘|하기|실행)?\s*[.!]?\s*$")
_lock = threading.Lock()


def is_refresh_command(question: str) -> bool:
    return COMMAND.match(question) is not None


def snapshot(law_dir: Path = LAW_DIR) -> dict[str, str]:
    retriever._load_chunks_cached.cache_clear()
    return {c.doc_id: c.text for c in retriever.load_chunks(law_dir)}


def diff(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {"added": sorted(set(after) - set(before)),
            "removed": sorted(set(before) - set(after)),
            "changed": sorted(d for d in set(before) & set(after) if before[d] != after[d])}


def _step(name: str, inp: str, out: str) -> dict[str, str]:
    return {"step": name, "input": inp, "output": out[:1500]}


def refresh(collect: Callable[[], list[dict]] | None = None, build: Callable[[], int] | None = None,
            law_dir: Path = LAW_DIR) -> dict:
    """법령을 다시 받고 API Spec 모양({answer, contexts, trace})으로 결과를 돌려줍니다."""
    if not _lock.acquire(blocking=False):
        return {"answer": "법령 갱신이 이미 진행 중입니다. 잠시 후 다시 시도해 주세요.", "contexts": [],
                "trace": [_step("law_refresh", "법령 갱신", "이미 진행 중")]}
    try:
        if collect is None:
            if not get_settings().law_api_oc:
                return {"answer": "법령 API 키(LAW_API_OC)가 없어 법령을 가져올 수 없습니다. 기존 조문을 그대로 씁니다.",
                        "contexts": [], "trace": [_step("law_refresh", "법령 갱신", "LAW_API_OC 없음")]}
            from scripts.collect_data import refresh_laws
            collect = lambda: refresh_laws(out_dir=law_dir)  # noqa: E731
        if build is None:
            from scripts.build_index import build as build_index
            build = build_index

        before = snapshot(law_dir)
        results = collect()
        after = snapshot(law_dir)
        d = diff(before, after)
        trace = [_step("law_refresh_collect", r["law"],
                       "실패: " + r["error"] if not r["ok"] else
                       "; ".join(f"{v['status']} {v['effective']} 조문 {len(v['articles'])}개" for v in r["versions"]))
                 for r in results]
        trace.append(_step("law_refresh_diff", "갱신 전후 조문 비교",
                           f"추가 {len(d['added'])}, 변경 {len(d['changed'])}, 삭제 {len(d['removed'])}"))

        changed_any = any(d.values())
        index_ok = True
        if changed_any or not (retriever.INDEX_DIR / "vectors.npy").exists():
            index_ok = build() == 0
            trace.append(_step("law_refresh_index", "build_index", "다시 만듦" if index_ok else "실패 → BM25만 사용"))
        else:
            trace.append(_step("law_refresh_index", "build_index", "바뀐 조문이 없어 그대로 사용"))
        retriever._load_chunks_cached.cache_clear()
        retriever.get_index.cache_clear()

        return {"answer": render_answer(results, d, index_ok, changed_any),
                "contexts": [{"doc_id": k, "text": after[k]} for k in d["added"] + d["changed"]],
                "trace": trace}
    finally:
        _lock.release()


def render_answer(results: list[dict], d: dict[str, list[str]], index_ok: bool, changed_any: bool) -> str:
    lines = [f"법령을 다시 가져왔습니다 (가져온 날 {today().isoformat()})."]
    for i, r in enumerate(results, 1):
        if not r["ok"]:
            lines.append(f"{i}. {r['law']}: 가져오기 실패, 기존 조문을 그대로 씁니다 ({r['error']}).")
            continue
        cur = [v for v in r["versions"] if v["status"] == "현행"]
        up = [v for v in r["versions"] if v["status"] != "현행"]
        text = f"{i}. {r['law']}: 현행 {cur[0]['effective']} 시행 판(조문 {len(cur[0]['articles'])}개)" if cur else \
            f"{i}. {r['law']}: 현행 판 없음"
        text += (", 시행 예정 " + ", ".join(f"{v['effective']} 시행 판(바뀌는 조문 {', '.join(v['articles'])})" for v in up)
                 if up else ", 내용이 바뀌는 시행 예정 판 없음")
        lines.append(text)
    if changed_any:
        parts = [f"{label} {', '.join(d[k])}" for k, label in (("added", "추가"), ("changed", "변경"), ("removed", "삭제"))
                 if d[k]]
        lines.append("바뀐 조문: " + " / ".join(parts))
        lines.append("검색 인덱스를 다시 만들었습니다." if index_ok else
                     "검색 인덱스를 다시 만들지 못해 키워드 검색(BM25)만 씁니다.")
    else:
        lines.append("바뀐 조문은 없습니다.")
    return "\n".join(lines)

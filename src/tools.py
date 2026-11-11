"""도메인 도구."""

# --- 아래부터 추가 (기존 코드: 위 docstring 한 줄) ---
# MSDS 개정 지원 에이전트의 도메인 도구 뼈대입니다.
# - 표준 라이브러리만 사용하므로 LLM·API 키 없이도 실행·테스트할 수 있습니다.
# - langchain_core가 설치돼 있으면 같은 함수를 LangChain 도구(TOOLS)로도 노출합니다.
# - 데이터: data/msds/products.json(가상 제품), data/regulation_updates.json(규제·사내 변경 사건)

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 산업안전보건법 시행규칙 제159조제1항: 변경 시 MSDS를 다시 제출해야 하는 사항
RESUBMISSION_ITEMS = {
    "제품명": {
        "item": "제159조제1항제1호",
        "text": "제품명(구성성분의 명칭 및 함유량의 변경이 없는 경우로 한정한다)",
    },
    "구성성분": {
        "item": "제159조제1항제2호",
        "text": "분류기준에 해당하는 화학물질의 명칭 및 함유량(제품명의 변경 없이 구성성분의 명칭 및 함유량만 변경된 경우로 한정한다)",
    },
    "유해성": {
        "item": "제159조제1항제3호",
        "text": "건강 및 환경에 대한 유해성, 물리적 위험성",
    },
}
RESUBMISSION_DOC_IDS = ["law:산안법:110", "law:산안법시행규칙:159"]


# ---------------------------------------------------------------- 데이터 로딩
@lru_cache(maxsize=1)
def _products() -> list[dict[str, Any]]:
    with open(DATA_DIR / "msds" / "products.json", encoding="utf-8") as f:
        return json.load(f)["products"]


@lru_cache(maxsize=1)
def _updates() -> list[dict[str, Any]]:
    with open(DATA_DIR / "regulation_updates.json", encoding="utf-8") as f:
        return json.load(f)["updates"]


def _find_product(product_id: str) -> dict[str, Any] | None:
    pid = product_id.strip().upper()
    return next((p for p in _products() if p["id"] == pid), None)


# ---------------------------------------------------------------- 마스킹 (가드레일 6번의 일부)
def mask_phone(text: str) -> str:
    return re.sub(r"(01[016789])-?(\d{3,4})-?(\d{4})", r"\1-****-\3", text)


def mask_email(text: str) -> str:
    return re.sub(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@", r"\1***@", text)


def _public_view(product: dict[str, Any]) -> dict[str, Any]:
    """영업비밀 실명·실함유량과 담당자 연락처를 지운 사본을 돌려줍니다."""
    p = json.loads(json.dumps(product, ensure_ascii=False))
    for comp in p.get("section3", []):
        for key in ("real_name", "real_cas", "real_content"):
            comp.pop(key, None)
    s1 = p.get("section1", {})
    if "contact_phone" in s1:
        s1["contact_phone"] = mask_phone(s1["contact_phone"])
    if "contact_email" in s1:
        s1["contact_email"] = mask_email(s1["contact_email"])
    if "contact_name" in s1:
        s1["contact_name"] = s1["contact_name"][0] + "**"
    return p


# ---------------------------------------------------------------- 도구 함수
def get_msds(product_id: str, sections: list[str] | None = None) -> dict[str, Any]:
    """제품 MSDS를 조회합니다. 영업비밀 성분과 담당자 연락처는 마스킹됩니다.

    sections 예: ["3", "15"]. 생략하면 전체를 돌려줍니다.
    """
    product = _find_product(product_id)
    if product is None:
        return {"error": f"제품 {product_id}을(를) 찾을 수 없습니다."}
    view = _public_view(product)
    if sections:
        keep = {"id", "name", "revision"} | {f"section{s}" for s in sections}
        view = {k: v for k, v in view.items() if k in keep}
    view["doc_id"] = f"msds:{product['id']}"
    return view


def find_products_by_cas(cas: str) -> list[dict[str, str]]:
    """CAS 번호로 해당 성분을 포함한 제품을 찾습니다. 영업비밀 성분은 검색되지 않습니다."""
    cas = cas.strip()
    hits = []
    for p in _products():
        for comp in p["section3"]:
            if comp["cas"] == cas:
                hits.append({"product_id": p["id"], "product_name": p["name"],
                             "component": comp["name"], "content": comp["content"]})
    return hits


def find_products_by_term(term: str, section: str = "15") -> list[dict[str, Any]]:
    """MSDS 특정 항목(기본 15번 법적 규제현황)에 용어가 적힌 제품을 찾습니다."""
    hits = []
    for p in _products():
        block = p.get(f"section{section}")
        text = json.dumps(block, ensure_ascii=False)
        if term in text:
            matched = []
            if isinstance(block, dict):
                for law, items in block.items():
                    matched += [f"{law}: {it}" for it in items if term in it]
            hits.append({"product_id": p["id"], "product_name": p["name"], "matched": matched})
    return hits


def get_regulation_update(update_id: str) -> dict[str, Any]:
    """규제 변경 또는 사내 변경 사건을 조회합니다."""
    uid = update_id.strip().upper()
    for u in _updates():
        if u["id"] == uid:
            return u
    return {"error": f"변경 사건 {update_id}을(를) 찾을 수 없습니다."}


def list_regulation_updates() -> list[dict[str, str]]:
    """등록된 변경 사건 목록(id, 제목, 유형)을 돌려줍니다."""
    return [{"id": u["id"], "title": u["title"], "type": u["type"]} for u in _updates()]


def check_resubmission(change: str) -> dict[str, Any]:
    """바뀐 내용이 시행규칙 제159조제1항의 재제출 대상인지 판정합니다.

    change 예: "제품명", "구성성분 함유량", "건강 및 환경에 대한 유해성", "법적 규제현황"
    """
    if "제품명" in change:
        key = "제품명"
    elif any(k in change for k in ("구성성분", "함유량", "명칭")):
        key = "구성성분"
    elif any(k in change for k in ("유해성", "위험성")):
        key = "유해성"
    else:
        return {
            "change": change,
            "resubmission_required": False,
            "basis": "시행규칙 제159조제1항 각 호(제품명, 구성성분 명칭·함유량, 유해성·위험성)에 해당하지 않습니다.",
            "doc_ids": RESUBMISSION_DOC_IDS,
        }
    item = RESUBMISSION_ITEMS[key]
    return {
        "change": change,
        "resubmission_required": True,
        "basis": f"{item['item']}: {item['text']}",
        "deadline": "변경사항을 반영한 물질안전보건자료를 지체 없이 공단에 제출(시행규칙 제159조제2항)",
        "doc_ids": RESUBMISSION_DOC_IDS,
    }


def assess_update(update_id: str) -> dict[str, Any]:
    """변경 사건 하나가 어떤 제품의 어떤 MSDS 항목에 영향을 주는지 규칙으로 판정합니다.

    LLM 판정의 기준선(baseline)이자 평가셋 정답을 만드는 근거로 씁니다.
    """
    update = get_regulation_update(update_id)
    if "error" in update:
        return update
    match = update["match"]
    affected = []
    if "term" in match:
        for hit in find_products_by_term(match["term"], match["section"]):
            affected.append({
                "product_id": hit["product_id"],
                "product_name": hit["product_name"],
                "sections": [match["section"]],
                "current": hit["matched"],
                "resubmission": check_resubmission("법적 규제현황"),
            })
    else:
        p = _find_product(match["product_id"])
        section = {"제품명": "1", "구성성분 함유량": "3", "건강 및 환경에 대한 유해성": "2"}.get(match["change"], "")
        affected.append({
            "product_id": p["id"],
            "product_name": p["name"],
            "sections": [section] if section else [],
            "resubmission": check_resubmission(match["change"]),
        })
    return {"update": {"id": update["id"], "title": update["title"], "real": update["real"]},
            "affected": affected,
            "doc_ids": update.get("related_docs", [])}


# ---------------------------------------------------------------- LangChain 도구 노출 (설치돼 있을 때만)
TOOLS: list = []
try:  # pragma: no cover - 의존성 설치 여부에 따라 달라짐
    from langchain_core.tools import tool as _tool

    TOOLS = [_tool(fn) for fn in (get_msds, find_products_by_cas, find_products_by_term,
                                  get_regulation_update, list_regulation_updates,
                                  check_resubmission, assess_update)]
except ImportError:
    pass


if __name__ == "__main__":
    print(json.dumps(assess_update("U-01"), ensure_ascii=False, indent=2))

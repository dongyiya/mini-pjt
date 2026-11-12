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
# (기존 코드) 처음 읽은 내용을 계속 캐시 — 승인 시 MSDS가 바뀌면(src/msds_revision.py) 서버·MCP 프로세스가
# 바뀐 파일을 다시 읽도록 파일 수정 시각 기준 캐시로 교체
# @lru_cache(maxsize=1)
# def _products() -> list[dict[str, Any]]:
#     with open(DATA_DIR / "msds" / "products.json", encoding="utf-8") as f:
#         return json.load(f)["products"]
_PRODUCTS_CACHE: dict[str, Any] = {"mtime": None, "data": None}


def _products() -> list[dict[str, Any]]:
    path = DATA_DIR / "msds" / "products.json"
    mtime = path.stat().st_mtime_ns
    if _PRODUCTS_CACHE["mtime"] != mtime:
        with open(path, encoding="utf-8") as f:
            _PRODUCTS_CACHE.update(mtime=mtime, data=json.load(f)["products"])
    return _PRODUCTS_CACHE["data"]


_products.cache_clear = lambda: _PRODUCTS_CACHE.update(mtime=None, data=None)  # 기존 호출부 호환


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


# ---------------------------------------------------------------- 2일차 추가 도구
def list_products() -> list[dict[str, str]]:
    """등록된 제품 목록(id, 제품명, MSDS 개정판)을 돌려줍니다. 없는 제품을 물으면 이 목록으로 안내합니다."""
    return [{"id": p["id"], "name": p["name"], "revision": f"{p['revision']['no']}판 ({p['revision']['date']})"}
            for p in _products()]


def search_law(query: str, as_of: str | None = None, k: int = 3) -> dict[str, Any]:
    """법령 조문을 하이브리드 검색(BM25+FAISS, 쿼리 확장, 리랭킹)합니다.

    as_of(YYYY-MM-DD) 기준으로 시행 중인 판을 'applicable'에, 그 뒤에 시행될 판을 'upcoming'에 담습니다.
    판정 근거는 applicable 조문만 씁니다.
    """
    import os
    from datetime import date as _date

    from src import retriever

    day = _date.fromisoformat(as_of) if as_of else None
    rerank = os.getenv("MSDS_RERANK", "1") != "0"
    r = retriever.search(query, k=k, as_of=day, rerank=rerank)

    def view(c):
        return {"doc_id": c.doc_id, "title": c.title, "text": c.text,
                "effective_from": c.effective_from.isoformat() if c.effective_from else None}

    return {"as_of": r.as_of.isoformat(), "method": r.method,
            "applicable": [view(c) for c in r.applicable],
            "upcoming": [view(c) for c in r.upcoming],
            "notes": r.notes}


DOMESTIC_REG_KEYS = ("산업안전보건법에 의한 규제", "화학물질관리법에 의한 규제",
                     "화학물질의 등록 및 평가 등에 관한 법률 규제")


def _substance(cas: str) -> dict[str, Any] | None:
    path = DATA_DIR / "substances" / f"{cas.strip()}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_substance(cas: str) -> dict[str, Any]:
    """단일물질 정보(안전보건공단 공개 MSDS 스냅샷)를 CAS 번호로 조회합니다.

    GHS 유해성·위험성 분류, 그림문자, 신호어, 국내 법적 규제현황(산안법·화관법·화평법)을 돌려줍니다.
    """
    s = _substance(cas)
    if s is None:
        return {"error": f"CAS {cas} 물질 정보가 없습니다. 등록 제품의 공개 성분만 조회할 수 있습니다."}
    return {
        "cas": s["cas"], "name": s["name"], "doc_id": s["doc_id"],
        "ghs": s["section2"]["ghs"], "pictograms": s["section2"]["pictograms"],
        "signal_word": s["section2"]["signal_word"],
        "regulations": {k: v for k, v in s["section15"].items() if k in DOMESTIC_REG_KEYS},
        "source": f"{s['source']} (공단 갱신일 {s.get('kosha_last_date', '')}, 수집일 {s['collected']})",
    }


def _hazard_class(text: str) -> str:
    """'인화성 액체 : 구분2' / '인화성 액체 구분2' → '인화성액체' (비교용 유해성 항목 이름)."""
    head = re.split(r"\s*:\s*|\s*구분", text, maxsplit=1)[0]
    head = re.sub(r"/\s*피부\s*", "/", head)   # '피부 부식성/피부 자극성' = '피부 부식성/자극성'
    return re.sub(r"[\s/·]", "", head)


def classify_mixture(product_id: str) -> dict[str, Any]:
    """제품 성분별 GHS 분류를 모아 제품 MSDS 2번과 비교한 '검토 목록'을 만듭니다.

    혼합물 최종 분류(가산식·한계농도)는 고시 기준 원문을 아직 수집하지 않아 계산하지 않습니다 → '확인 필요'.
    영업비밀 성분은 공단 자료를 조회하지 않으며 실제 명칭을 드러내지 않습니다.
    """
    product = _find_product(product_id)
    if product is None:
        return {"error": f"제품 {product_id}을(를) 찾을 수 없습니다."}
    current = {_hazard_class(h): h for h in product.get("section2", {}).get("ghs", [])}
    by_class: dict[str, list[dict[str, str]]] = {}
    skipped = []
    for comp in product["section3"]:
        if comp.get("trade_secret"):
            skipped.append(f"{comp['name']}({comp['content']}): 영업비밀 성분이라 공단 자료를 조회하지 않음")
            continue
        s = _substance(comp["cas"])
        if s is None:
            skipped.append(f"{comp['name']}({comp['cas']}): 물질 스냅샷 없음")
            continue
        for g in s["section2"]["ghs"]:
            if g == "자료없음":
                continue
            by_class.setdefault(_hazard_class(g), []).append(
                {"component": comp["name"], "cas": comp["cas"], "content": comp["content"], "classification": g})
    review = [{"hazard_class": by_class[k][0]["classification"].split(" :")[0], "components": v,
               "in_product_section2": k in current}
              for k, v in by_class.items()]
    return {
        "product_id": product["id"], "product_name": product["name"],
        "product_section2": list(current.values()),
        "component_hazards": review,
        "not_in_section2": [r["hazard_class"] for r in review if not r["in_product_section2"]],
        "skipped": skipped,
        "note": "성분별 분류를 모은 검토 목록입니다. 혼합물 최종 분류(가산식·한계농도 적용)는 "
                "「화학물질의 분류·표시 및 물질안전보건자료에 관한 기준」 원문 확인 필요.",
        "doc_ids": [f"msds:{product['id']}"] + [f"substance:{c['cas']}" for c in product["section3"]
                                                 if not c.get("trade_secret") and _substance(c["cas"])],
    }


# ---------------------------------------------------------------- LangChain 도구 노출 (설치돼 있을 때만)
# (기존 코드) 7개 도구만 노출 — list_products, search_law 추가로 교체
# TOOLS: list = []
# try:  # pragma: no cover - 의존성 설치 여부에 따라 달라짐
#     from langchain_core.tools import tool as _tool
#
#     TOOLS = [_tool(fn) for fn in (get_msds, find_products_by_cas, find_products_by_term,
#                                   get_regulation_update, list_regulation_updates,
#                                   check_resubmission, assess_update)]
# except ImportError:
#     pass
ALL_FUNCTIONS = (get_msds, list_products, find_products_by_cas, find_products_by_term,
                 get_regulation_update, list_regulation_updates, check_resubmission, assess_update, search_law,
                 get_substance, classify_mixture)
TOOLS: list = []
try:  # pragma: no cover - 의존성 설치 여부에 따라 달라짐
    from langchain_core.tools import tool as _tool

    TOOLS = [_tool(fn) for fn in ALL_FUNCTIONS]
except ImportError:
    pass


if __name__ == "__main__":
    print(json.dumps(assess_update("U-01"), ensure_ascii=False, indent=2))

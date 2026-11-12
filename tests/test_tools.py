"""src/tools.py 단위 테스트 (1일차 도구 + 2일차 추가 도구)."""

import json

# (기존 코드) from src import tools as T
from src.tools import msds_tools as T


def test_get_msds_masks_secret_and_contact():
    v = T.get_msds("P-001")
    s = json.dumps(v, ensure_ascii=False)
    for bad in ("2-부톡시에탄올", "111-76-2", "7.2%", "010-1234-5678", "김민수"):
        assert bad not in s
    assert v["section1"]["contact_phone"] == "010-****-5678"
    assert v["doc_id"] == "msds:P-001"


def test_get_msds_sections_and_unknown():
    v = T.get_msds("p-006", ["3"])
    assert set(v) == {"id", "name", "revision", "section3", "doc_id"}
    assert [c["name"] for c in v["section3"]] == ["에탄올", "물"]
    assert "error" in T.get_msds("P-009")


def test_list_products():
    ps = T.list_products()
    assert [p["id"] for p in ps] == [f"P-00{i}" for i in range(1, 7)]


def test_find_products_by_cas_toluene():
    hits = T.find_products_by_cas("108-88-3")
    assert [(h["product_id"], h["content"]) for h in hits] == [("P-001", "40~50%"), ("P-002", "10~20%"),
                                                               ("P-005", "60~70%")]
    assert T.find_products_by_cas("111-76-2") == []          # 영업비밀 실제 CAS로는 검색되지 않음


def test_find_products_by_term_u01():
    assert [h["product_id"] for h in T.find_products_by_term("유독물질")] == ["P-001", "P-003", "P-005"]


def test_regulation_updates():
    assert [u["id"] for u in T.list_regulation_updates()] == ["U-01", "U-02", "U-03", "U-04"]
    assert "error" in T.get_regulation_update("U-05")


def test_check_resubmission_rules():
    assert T.check_resubmission("제품명")["basis"].startswith("제159조제1항제1호")
    assert T.check_resubmission("구성성분 함유량")["basis"].startswith("제159조제1항제2호")
    assert T.check_resubmission("건강 및 환경에 대한 유해성")["basis"].startswith("제159조제1항제3호")
    assert T.check_resubmission("법적 규제현황")["resubmission_required"] is False


def test_assess_update_each_event():
    u1 = T.assess_update("U-01")
    assert [a["product_id"] for a in u1["affected"]] == ["P-001", "P-003", "P-005"]
    assert all(not a["resubmission"]["resubmission_required"] for a in u1["affected"])
    u2 = T.assess_update("U-02")["affected"][0]
    assert (u2["product_id"], u2["sections"], u2["resubmission"]["resubmission_required"]) == ("P-002", ["3"], True)
    u3 = T.assess_update("U-03")["affected"][0]
    assert (u3["product_id"], u3["sections"]) == ("P-004", ["2"])
    u4 = T.assess_update("U-04")["affected"][0]
    assert (u4["product_id"], u4["sections"]) == ("P-006", ["1"])


def test_search_law_returns_applicable_and_upcoming(monkeypatch):
    monkeypatch.setenv("MSDS_RERANK", "0")
    # (기존 코드) from src import retriever
    from src.regulation import retriever

    retriever.get_index.cache_clear()
    monkeypatch.setattr(retriever.HybridIndex, "vector_ranks", lambda self, q, embed=None, top=20: [])
    r = T.search_law("MSDS 변경 시 다시 제출해야 하는 사항", as_of="2026-11-12")
    assert r["as_of"] == "2026-11-12"
    assert "law:산안법시행규칙:159" in [c["doc_id"] for c in r["applicable"][:3]]
    assert set(r["applicable"][0]) == {"doc_id", "title", "text", "effective_from"}
    assert r["upcoming"] == []         # 현재 데이터에는 내용이 바뀌는 예정 조문이 없음


def test_get_substance_toluene():
    s = T.get_substance("108-88-3")
    assert s["name"] == "톨루엔" and s["doc_id"] == "substance:108-88-3"
    assert any(g.startswith("인화성 액체") for g in s["ghs"])
    assert set(s["regulations"]) <= set(T.DOMESTIC_REG_KEYS)
    assert "유독물질" not in str(s["regulations"])             # 공단 자료에도 유독물질 표기 없음 (U-01과 일치)
    assert "error" in T.get_substance("111-76-2")               # 영업비밀 실제 CAS는 수집하지 않음


def test_hazard_class_normalization():
    assert T._hazard_class("인화성 액체 : 구분2") == T._hazard_class("인화성 액체 구분2") == "인화성액체"
    assert T._hazard_class("피부 부식성/피부 자극성 : 구분2") == T._hazard_class("피부 부식성/자극성 구분2")


def test_classify_mixture_review_list():
    r = T.classify_mixture("P-001")
    s = json.dumps(r, ensure_ascii=False)
    assert "2-부톡시에탄올" not in s and "111-76-2" not in s and "7.2%" not in s
    assert any("세정보조제 HB-7" in x for x in r["skipped"])
    tol = [h for h in r["component_hazards"] if h["hazard_class"] == "인화성 액체"][0]
    assert {c["component"] for c in tol["components"]} >= {"톨루엔", "아세톤"}
    assert tol["in_product_section2"] is True
    assert "확인 필요" in r["note"]
    assert "msds:P-001" in r["doc_ids"] and "substance:108-88-3" in r["doc_ids"]
    assert "error" in T.classify_mixture("P-009")


def test_tools_exposed_to_langchain():
    names = [t.name for t in T.TOOLS]
    assert names == [f.__name__ for f in T.ALL_FUNCTIONS]
    assert "search_law" in names and "list_products" in names

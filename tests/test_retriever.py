"""src/retriever.py 단위 테스트."""

import csv
from datetime import date

import numpy as np
import pytest

# (기존 코드) from src import retriever as R
from src.regulation import retriever as R
# (기존 코드) from src.config import ROOT
from src.shared.config import ROOT

CUR = """---
law: 테스트법
short: 테법
status: 현행
effective: 2026-10-27
---

## [law:테법:110] 제110조(물질안전보건자료의 작성)
① 물질안전보건자료를 작성하여 제출하여야 한다.

## [law:테법:111] 제111조(물질안전보건자료의 제공)
① 양도하거나 제공하는 자는 상대방에게 제공하여야 한다.

## [law:테법:112] 제112조(일부 비공개 승인)
① 영업비밀과 관련된 화학물질은 대체자료로 적을 수 있다.

## [law:테법:113] 제113조(국외제조자)
① 국외제조자는 선임한 자를 통해 정보를 낼 수 있다.

## [law:테법:115] 제115조(경고표시)
① 용기 및 포장에 경고표시를 하여야 한다.
"""

UP = """---
law: 테스트법
short: 테법
status: 시행예정
effective: 2027-04-28
---

## [law:테법:110@2027-04-28] 제110조(물질안전보건자료의 작성)
① 물질안전보건자료를 전자적으로 작성하여 제출하여야 한다.
"""


@pytest.fixture
def law_dir(tmp_path):
    (tmp_path / "테스트법@20261027.md").write_text(CUR, encoding="utf-8")
    (tmp_path / "테스트법@20270428.md").write_text(UP, encoding="utf-8")
    R._load_chunks_cached.cache_clear()
    yield tmp_path
    R._load_chunks_cached.cache_clear()


def test_parse_and_effective_to(law_dir):
    chunks = R.load_chunks(law_dir)
    by_id = {c.doc_id: c for c in chunks}
    assert set(by_id) == {"law:테법:110", "law:테법:111", "law:테법:112", "law:테법:113", "law:테법:115",
                          "law:테법:110@2027-04-28"}
    cur = by_id["law:테법:110"]
    assert cur.effective_from == date(2026, 10, 27)
    assert cur.effective_to == date(2027, 4, 27)          # 다음 판 시행일 전날
    assert by_id["law:테법:111"].effective_to is None
    assert by_id["law:테법:110@2027-04-28"].group == "law:테법:110"
    assert cur.text.startswith("제110조(물질안전보건자료의 작성)\n①")


def test_choose_version_by_as_of(law_dir):
    versions = [c for c in R.load_chunks(law_dir) if c.group == "law:테법:110"]
    cur, fut = R.choose_version(versions, date(2026, 11, 12))
    assert cur.doc_id == "law:테법:110" and [c.doc_id for c in fut] == ["law:테법:110@2027-04-28"]
    cur, fut = R.choose_version(versions, date(2027, 5, 1))
    assert cur.doc_id == "law:테법:110@2027-04-28" and fut == []
    cur, fut = R.choose_version(versions, date(2027, 4, 28))   # 시행일 당일부터 적용
    assert cur.doc_id == "law:테법:110@2027-04-28"


def fake_embed(text):
    # '제공'이 들어가면 2번 축, 아니면 1번 축 → 결정적인 가짜 임베딩
    return [0.0, 1.0] if "제공" in text else [1.0, 0.0]


def test_search_splits_applicable_and_upcoming(law_dir):
    chunks = R.load_chunks(law_dir)
    idx = R.HybridIndex(chunks, vectors=[fake_embed(c.text) for c in chunks])
    r = R.search("물질안전보건자료 작성 제출", k=1, as_of=date(2026, 11, 12), index=idx, embed=fake_embed)
    assert r.method == "bm25+faiss"
    assert [c.doc_id for c in r.applicable] == ["law:테법:110"]
    assert [c.doc_id for c in r.upcoming] == ["law:테법:110@2027-04-28"]
    ctx = R.to_contexts(r)
    assert ctx[0] == {"doc_id": "law:테법:110", "text": r.applicable[0].text}
    assert ctx[1]["text"].startswith("[시행 예정 2027-04-28] 제110조")
    assert set(ctx[1]) == {"doc_id", "text"}                  # API Spec 필드 그대로

    r2 = R.search("물질안전보건자료 작성 제출", k=1, as_of=date(2027, 6, 1), index=idx, embed=fake_embed)
    assert [c.doc_id for c in r2.applicable] == ["law:테법:110@2027-04-28"] and r2.upcoming == []


def test_search_before_earliest_snapshot_adds_note(law_dir):
    idx = R.HybridIndex(R.load_chunks(law_dir))
    r = R.search("양도 제공 상대방", k=1, as_of=date(2020, 1, 1), index=idx)
    assert r.applicable[0].doc_id == "law:테법:111"
    assert r.notes and "수집하지 않아" in r.notes[0]


def test_vector_failure_falls_back_to_bm25(law_dir):
    chunks = R.load_chunks(law_dir)
    idx = R.HybridIndex(chunks, vectors=[fake_embed(c.text) for c in chunks])

    def broken(_):
        raise ConnectionError("down")

    r = R.search("상대방에게 제공", k=1, as_of=date(2026, 11, 12), index=idx, embed=broken)
    assert r.method.startswith("bm25 (벡터 검색 실패")
    assert r.applicable[0].doc_id == "law:테법:111"


class FakeRanker:
    """with_structured_output(...).invoke(...) 흉내: 정해진 순서를 돌려줌."""

    def __init__(self, order, fail=False):
        self.order, self.fail = order, fail

    def with_structured_output(self, schema):
        outer = self

        class _R:
            def invoke(self, prompt):
                if outer.fail:
                    raise TimeoutError("llm down")
                return schema(doc_ids=outer.order)
        return _R()


def test_rerank_reorders_and_ignores_unknown_ids(law_dir):
    idx = R.HybridIndex(R.load_chunks(law_dir))
    r = R.search("물질안전보건자료 작성 제출", k=1, as_of=date(2026, 11, 12), index=idx,
                 rerank=True, rerank_model=FakeRanker(["law:없는조문", "law:테법:111"]))
    assert r.method.endswith("+rerank")
    assert [c.doc_id for c in r.applicable] == ["law:테법:111"]


def test_rerank_failure_keeps_original_order(law_dir):
    idx = R.HybridIndex(R.load_chunks(law_dir))
    r = R.search("물질안전보건자료 작성 제출", k=1, as_of=date(2026, 11, 12), index=idx,
                 rerank=True, rerank_model=FakeRanker([], fail=True))
    assert "리랭크 실패" in r.method
    assert [c.doc_id for c in r.applicable] == ["law:테법:110"]


def test_rrf_rewards_agreement():
    s = R.rrf([[0, 1, 2], [1, 0]])
    assert s[0] == s[1] > s[2]


def test_expand_query_terms_and_cas_alias():
    q = R.expand_query("MSDS에 톨루엔 넣으면?")
    assert "물질안전보건자료" in q and "108-88-3" in q
    assert "톨루엔" in R.expand_query("108-88-3 포함 제품")
    assert "7732-18-5" not in R.expand_query("물질안전보건자료 작성")   # '물'(물의 성분명)이 '물질'에 걸리지 않음
    assert "71-43-2" not in R.expand_query("폴리벤젠 수지")              # 다른 단어의 일부는 확장하지 않음
    assert "71-43-2" in R.expand_query("벤젠이 들어간 제품")
    # 영업비밀 성분의 실명·CAS는 확장 사전에 없어야 함
    aliases = R._substance_aliases()
    assert "2-부톡시에탄올" not in aliases and "111-76-2" not in aliases and "영업비밀" not in aliases


def test_tokenize_keeps_content_words():
    toks = R.tokenize("MSDS 변경 시 다시 제출해야 하는 항목은? CAS 108-88-3")
    assert {"msds", "변경", "제출", "항목", "108-88-3"} <= set(toks)
    assert "은" not in toks


# ---------------------------------------------------------------- 실제 데이터 (BM25만, 네트워크 없음)
def test_real_data_loaded_with_versions():
    R._load_chunks_cached.cache_clear()
    chunks = R.load_chunks()
    ids = {c.doc_id for c in chunks}
    assert {"law:산안법:110", "law:산안법:111", "law:산안법:114", "law:산안법시행규칙:159", "law:화관법:2"} <= ids
    assert all(c.effective_from for c in chunks)


def _v1_rows():
    """기대 doc_id 중 법령 조문(law:)만 남깁니다. 제품 MSDS(msds:)는 검색기가 아니라 도구가 찾습니다."""
    rows = []
    with open(ROOT / "evaluation" / "test_queries.v1.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            laws = [d for d in r["expected_doc_ids"].split(";") if d.startswith("law:")]
            if laws:
                rows.append({**r, "expected_doc_ids": ";".join(laws)})
    return rows


def test_real_data_bm25_recall_at_3():
    """옛 평가셋 v1에서 기대 조문이 상위 3개 안에 드는 비율 (BM25만으로 80% 이상)."""
    R._load_chunks_cached.cache_clear()
    idx = R.HybridIndex(R.load_chunks())
    rows = _v1_rows()
    hit = 0
    for r in rows:
        expected = set(r["expected_doc_ids"].split(";"))
        got = {c.doc_id for c in R.search(r["question"], k=3, index=idx, as_of=date(2026, 11, 12)).applicable}
        hit += bool(expected & got)
    assert hit / len(rows) >= 0.8, f"{hit}/{len(rows)}"


@pytest.mark.live
def test_live_hybrid_top1():
    """index/ 를 만든 뒤 실제 Titan 임베딩으로 하이브리드 1순위 정확도 확인."""
    R._load_chunks_cached.cache_clear()
    R.get_index.cache_clear()
    idx = R.get_index()
    assert idx.faiss is not None, "먼저 python -m scripts.build_index 를 실행하세요"
    rows = _v1_rows()
    for rerank in (False, True):
        top1 = sum(R.search(r["question"], k=1, index=idx, rerank=rerank).applicable[0].doc_id
                   in r["expected_doc_ids"].split(";") for r in rows)
        print(f"hybrid{'+rerank' if rerank else ''} top1 {top1}/{len(rows)}")
    assert top1 / len(rows) >= 0.8   # 리랭킹 적용 결과 기준

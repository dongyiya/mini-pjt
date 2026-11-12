"""src/law_refresh.py 단위 테스트 — 가짜 수집·인덱스 함수로 '법령 갱신' 명령 확인 (네트워크·LLM 없음)."""

import threading

import pytest

# (기존 코드) from src import law_refresh as LR
from src.regulation import refresh as LR
# (기존 코드) from src import retriever
from src.regulation import retriever

HEAD = "---\nlaw: 테스트법\nshort: 테법\nstatus: {status}\neffective: {eff}\n---\n\n"


def law_file(status, eff, body):
    return HEAD.format(status=status, eff=eff) + body


@pytest.fixture
def law_dir(tmp_path):
    (tmp_path / "테스트법@20261027.md").write_text(
        law_file("현행", "2026-10-27", "## [law:테법:110] 제110조(작성)\n① 작성한다.\n\n"
                                        "## [law:테법:111] 제111조(제공)\n① 제공한다.\n"), encoding="utf-8")
    yield tmp_path
    retriever._load_chunks_cached.cache_clear()
    retriever.get_index.cache_clear()


OK = [{"law": "테스트법", "ok": True, "error": None,
       "versions": [{"status": "현행", "effective": "2026-10-27", "articles": ["110", "111"]}]}]


@pytest.mark.parametrize("q, ok", [("법령 갱신", True), ("법령 가져오기", True), ("법령 업데이트 해줘", True),
                                   (" 법령갱신 ", True), ("법령 갱신 주기는?", False), ("MSDS 법령 알려줘", False)])
def test_command(q, ok):
    assert LR.is_refresh_command(q) is ok


def test_no_change_keeps_index(law_dir, monkeypatch):
    built = []
    monkeypatch.setattr(retriever, "INDEX_DIR", law_dir)            # vectors.npy 가 있는 것처럼
    (law_dir / "vectors.npy").write_bytes(b"x")
    r = LR.refresh(collect=lambda: OK, build=lambda: built.append(1) or 0, law_dir=law_dir)
    assert built == []
    assert set(r) == {"answer", "contexts", "trace"} and r["contexts"] == []
    assert "바뀐 조문은 없습니다" in r["answer"]
    assert "현행 2026-10-27 시행 판(조문 2개)" in r["answer"]
    assert [t["step"] for t in r["trace"]] == ["law_refresh_collect", "law_refresh_diff", "law_refresh_index"]


def test_changed_and_upcoming_rebuilds_index(law_dir):
    built = []

    def collect():
        (law_dir / "테스트법@20261027.md").write_text(
            law_file("현행", "2026-10-27", "## [law:테법:110] 제110조(작성)\n① 전자적으로 작성한다.\n\n"
                                            "## [law:테법:111] 제111조(제공)\n① 제공한다.\n"), encoding="utf-8")
        (law_dir / "테스트법@20270428.md").write_text(
            law_file("시행예정", "2027-04-28", "## [law:테법:111@2027-04-28] 제111조(제공)\n① 즉시 제공한다.\n"),
            encoding="utf-8")
        return [{"law": "테스트법", "ok": True, "error": None, "versions": [
            {"status": "현행", "effective": "2026-10-27", "articles": ["110", "111"]},
            {"status": "시행예정", "effective": "2027-04-28", "articles": ["111"]}]}]

    r = LR.refresh(collect=collect, build=lambda: built.append(1) or 0, law_dir=law_dir)
    assert built == [1]
    assert [c["doc_id"] for c in r["contexts"]] == ["law:테법:111@2027-04-28", "law:테법:110"]
    assert "추가 law:테법:111@2027-04-28" in r["answer"] and "변경 law:테법:110" in r["answer"]
    assert "시행 예정 2027-04-28 시행 판(바뀌는 조문 111)" in r["answer"]
    assert "검색 인덱스를 다시 만들었습니다" in r["answer"]


def test_failed_law_and_failed_index(law_dir):
    def collect():
        (law_dir / "테스트법@20261027.md").unlink()
        return [{"law": "다른법", "ok": False, "versions": [], "error": "ConnectionError: down"}]

    r = LR.refresh(collect=collect, build=lambda: 1, law_dir=law_dir)
    assert "다른법: 가져오기 실패, 기존 조문을 그대로 씁니다" in r["answer"]
    assert "삭제 law:테법:110, law:테법:111" in r["answer"]
    assert "키워드 검색(BM25)만" in r["answer"]


def test_concurrent_refresh_is_refused(law_dir):
    gate, started = threading.Event(), threading.Event()

    def slow():
        started.set()
        gate.wait(5)
        return OK

    t = threading.Thread(target=LR.refresh, kwargs={"collect": slow, "build": lambda: 0, "law_dir": law_dir})
    t.start()
    started.wait(5)
    r = LR.refresh(collect=lambda: OK, build=lambda: 0, law_dir=law_dir)
    gate.set()
    t.join()
    assert "이미 진행 중" in r["answer"]


def test_missing_api_key(monkeypatch):
    monkeypatch.setenv("LAW_API_OC", "")
    r = LR.refresh()
    assert "LAW_API_OC" in r["answer"]


def test_run_query_routes_refresh_command(monkeypatch):
    # (기존 코드) from src import agent as A
    from src.workflows import graph as A
    from tests.test_agent import FakeBrains, graph

    monkeypatch.setattr(LR, "refresh", lambda: {"answer": "갱신됨", "contexts": [], "trace": []})
    b = FakeBrains("regulation")
    assert A.run_query("법령 갱신", graph(b))["answer"] == "갱신됨"
    assert b.calls == []                                  # 가드·LLM을 거치지 않음

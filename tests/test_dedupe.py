"""src/revision/dedupe.py 단위 테스트 — 같은 변경의 승인 요청 중복 방지·정리 (LLM 없음)."""

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.agents.schemas import ProductRevision, RevisionJudgment
from src.revision import dedupe
from src.workflows import graph as A
from tests.test_agent import FakeBrains, judgment_u02, steps


def judgment_u03():
    return RevisionJudgment(
        revision_needed=True,
        products=[ProductRevision(product_id="P-004", product_name="에코코트 W-30", sections=["2"],
                                  changes=["2번 유해성 분류: 피부 과민성 구분1 추가"], resubmission_required=True)],
        reasons=["유해성 분류 변경, 시행규칙 제159조제1항제3호"], legal_basis=["law:산안법시행규칙:159"],
        draft="[P-004] 2번 피부 과민성 구분1 추가")


def graph(judgment):
    return A.build_graph(FakeBrains("revision", [AIMessage("정리")], judgment), checkpointer=InMemorySaver())


def req_of(resp):
    return next(t["input"] for t in resp["trace"] if t["step"] == "hitl_interrupt")


def test_signature_same_change_different_question():
    j = judgment_u02().model_dump()
    assert dedupe.signature("U-02 배합 변경 후 P-002 MSDS를 다시 제출해야 하나요?", j) == \
        dedupe.signature("U-01과 U-02를 모두 반영하면 P-002 MSDS는 어떻게 되나요?", j)
    assert dedupe.signature("U-02 반영하려면?", j) != dedupe.signature("U-03 반영하려면?", judgment_u03().model_dump())


def test_second_same_request_reuses_existing_req():
    g = graph(judgment_u02())
    first = A.run_query("U-02 배합 변경 후 P-002 MSDS를 다시 제출해야 하나요?", g)
    req = req_of(first)
    second = A.run_query("U-02 반영 후 P-002 재제출해야 해?", g)
    assert second["answer"].startswith(f"같은 변경의 승인 대기 건({req})이 이미 있어")
    assert f"승인 대기 상태입니다 ({req})" in second["answer"]
    assert "duplicate_check" in steps(second) and req_of(second) == req
    assert [p["id"] for p in dedupe.pending_with_signature(g)] == [req]          # 대기 건은 하나뿐
    assert set(second) == {"answer", "contexts", "trace"}                       # API Spec 모양 유지


def test_different_change_is_not_duplicate():
    g = A.build_graph(FakeBrains("revision", [AIMessage("정리")], judgment_u02()), checkpointer=InMemorySaver())
    a = req_of(A.run_query("U-02 반영하려면?", g))
    g2 = A.build_graph(FakeBrains("revision", [AIMessage("정리")], judgment_u03()), checkpointer=g.checkpointer)
    r = A.run_query("U-03 때문에 P-004 MSDS에서 무엇을 해야 하나요?", g2)
    assert "duplicate_check" not in steps(r)
    assert {p["id"] for p in dedupe.pending_with_signature(g2)} == {a, req_of(r)}


def test_close_existing_duplicates_keeps_latest():
    g = graph(judgment_u02())
    ids = []
    for rid in ("REQ-0001", "REQ-0002", "REQ-0003"):      # run_query 를 거치지 않고 예전처럼 중복 대기 건을 만듦
        g.invoke({"question": "U-02 반영하려면?", "req_id": rid}, {"configurable": {"thread_id": rid}})
        ids.append(rid)
    closed = dedupe.close_existing_duplicates(g)
    left = [p["id"] for p in dedupe.pending_with_signature(g)]
    assert len(left) == 1 and len(closed) == 2
    assert all(kept == left[0] for _, kept in closed)
    assert sorted(dedupe.closed_duplicate_ids(g)) == sorted(c for c, _ in closed)
    assert "승인 대기 건이 없습니다" in A.run_query(f"승인 {closed[0][0]}", g)["answer"]
    assert dedupe.close_existing_duplicates(g) == []                            # 다시 돌려도 변화 없음

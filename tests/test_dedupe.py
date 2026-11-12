"""src/revision/dedupe.py 단위 테스트 — 같은 변경의 승인 요청 중복 방지·정리 (LLM 없음)."""

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.agents.schemas import ProductRevision, RevisionJudgment
from src.revision import dedupe
from src.workflows import graph as A
# (기존 코드) from tests.test_agent import FakeBrains, judgment_u02, steps
from tests.test_agent import FakeBrains, draft_of, judgment_u02, steps, submit


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


# (기존 코드) 질문 때 중복이면 새 요청을 닫고 기존 번호로 안내 — 승인 요청('승인 요청 REQ-xxxx') 때 중복을 알리도록 바뀌어 교체
# def test_second_same_request_reuses_existing_req():
#     g = graph(judgment_u02())
#     first = A.run_query("U-02 배합 변경 후 P-002 MSDS를 다시 제출해야 하나요?", g)
#     req = req_of(first)
#     second = A.run_query("U-02 반영 후 P-002 재제출해야 해?", g)
#     assert second["answer"].startswith(f"같은 변경의 승인 대기 건({req})이 이미 있어")
#     assert f"승인 대기 상태입니다 ({req})" in second["answer"]
#     assert "duplicate_check" in steps(second) and req_of(second) == req
#     assert [p["id"] for p in dedupe.pending_with_signature(g)] == [req]          # 대기 건은 하나뿐
#     assert set(second) == {"answer", "contexts", "trace"}                       # API Spec 모양 유지
def test_request_duplicate_of_pending_is_reported():
    g = graph(judgment_u02())
    _, asked, req = submit("U-02 배합 변경 후 P-002 MSDS를 다시 제출해야 하나요?", g)
    assert req_of(asked) == req
    draft2 = draft_of(A.run_query("U-02 반영 후 P-002 재제출해야 해?", g))       # 질문은 다르지만 같은 변경
    dup = A.run_query(f"승인 요청 {draft2}", g)
    assert dup["answer"].startswith(f"중복입니다. 같은 변경의 승인 요청 {req} 건이 이미 승인 대기 중")
    assert "duplicate_check" in steps(dup) and "hitl_interrupt" not in steps(dup)
    assert [p["id"] for p in dedupe.pending_with_signature(g)] == [req]          # 대기 건은 하나뿐
    assert set(dup) == {"answer", "contexts", "trace"}                          # API Spec 모양 유지


def test_question_alone_does_not_create_pending():
    g = graph(judgment_u02())
    for _ in range(3):
        A.run_query("U-02 반영하려면?", g)
    assert dedupe.pending_with_signature(g) == []                               # 승인 요청 전에는 대기 건 없음


def test_request_duplicate_of_approved_and_after_reset(monkeypatch, tmp_path):
    from src.revision import msds_apply as M

    g = graph(judgment_u02())
    _, _, req = submit("U-02 반영하려면?", g)
    assert "승인 완료" in A.run_query(f"승인 {req}", g)["answer"]               # 실제 파일은 conftest 가 되돌림
    assert req in dedupe.applied_requests()
    draft2 = draft_of(A.run_query("U-02 반영 후 P-002 재제출해야 해?", g))
    dup = A.run_query(f"승인 요청 {draft2}", g)
    assert dup["answer"].startswith(f"중복입니다. 같은 변경이 이미 {req} 건으로 승인되어 제품 MSDS에 반영돼 있습니다")
    assert dedupe.pending_with_signature(g) == []
    monkeypatch.setattr(M, "LOG_PATH", tmp_path / "revision_log.json")         # MSDS 원복 = 반영 기록 없음
    again = A.run_query(f"승인 요청 {draft2}", g)
    assert again["answer"].startswith(f"{draft2} 승인 요청을 올렸습니다")


def test_rejected_change_can_be_requested_again():
    g = graph(judgment_u02())
    _, _, req = submit("U-02 반영하려면?", g)
    A.run_query(f"반려 {req} 함유량 재확인", g)
    _, asked, req2 = submit("U-02 반영하려면?", g)
    assert asked["answer"].startswith(f"{req2} 승인 요청을 올렸습니다")


# (기존 코드) def test_different_change_is_not_duplicate():
#     g = A.build_graph(FakeBrains("revision", [AIMessage("정리")], judgment_u02()), checkpointer=InMemorySaver())
#     a = req_of(A.run_query("U-02 반영하려면?", g))
#     g2 = A.build_graph(FakeBrains("revision", [AIMessage("정리")], judgment_u03()), checkpointer=g.checkpointer)
#     r = A.run_query("U-03 때문에 P-004 MSDS에서 무엇을 해야 하나요?", g2)
#     assert "duplicate_check" not in steps(r)
#     assert {p["id"] for p in dedupe.pending_with_signature(g2)} == {a, req_of(r)}
def test_different_change_is_not_duplicate():
    g = A.build_graph(FakeBrains("revision", [AIMessage("정리")], judgment_u02()), checkpointer=InMemorySaver())
    _, _, a = submit("U-02 반영하려면?", g)
    g2 = A.build_graph(FakeBrains("revision", [AIMessage("정리")], judgment_u03()), checkpointer=g.checkpointer)
    _, r, b = submit("U-03 때문에 P-004 MSDS에서 무엇을 해야 하나요?", g2)
    assert "duplicate_check" not in steps(r)
    assert {p["id"] for p in dedupe.pending_with_signature(g2)} == {a, b}


def test_close_existing_duplicates_keeps_latest():
    g = graph(judgment_u02())
    ids = []
    # (기존 코드) 질문만으로 승인 대기가 되던 시기 — 이제는 승인 요청(confirm) 단계를 거쳐야 승인 대기가 됨
    # for rid in ("REQ-0001", "REQ-0002", "REQ-0003"):      # run_query 를 거치지 않고 예전처럼 중복 대기 건을 만듦
    #     g.invoke({"question": "U-02 반영하려면?", "req_id": rid}, {"configurable": {"thread_id": rid}})
    #     ids.append(rid)
    for rid in ("REQ-0001", "REQ-0002", "REQ-0003"):      # run_query 를 거치지 않고 예전처럼 중복 대기 건을 만듦
        cfg = {"configurable": {"thread_id": rid}}
        g.invoke({"question": "U-02 반영하려면?", "req_id": rid}, cfg)
        g.invoke(Command(resume={"confirm": True}), cfg)
        ids.append(rid)
    closed = dedupe.close_existing_duplicates(g)
    left = [p["id"] for p in dedupe.pending_with_signature(g)]
    assert len(left) == 1 and len(closed) == 2
    assert all(kept == left[0] for _, kept in closed)
    assert sorted(dedupe.closed_duplicate_ids(g)) == sorted(c for c, _ in closed)
    assert "승인 대기 건이 없습니다" in A.run_query(f"승인 {closed[0][0]}", g)["answer"]
    assert dedupe.close_existing_duplicates(g) == []                            # 다시 돌려도 변화 없음

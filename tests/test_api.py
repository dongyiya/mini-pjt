"""src/api.py 단위 테스트 — 가짜 Brains 그래프로 API Spec 모양과 HITL 흐름 확인."""

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from src import agent as A
from src import api
from tests.test_agent import FakeBrains, judgment_u02


@pytest.fixture
def client(monkeypatch):
    g = A.build_graph(FakeBrains("revision", [AIMessage("정리")], judgment_u02()), checkpointer=InMemorySaver())
    monkeypatch.setattr(api, "get_graph", lambda: g)
    return TestClient(api.app)


def check_spec(body):
    assert set(body) == {"answer", "contexts", "trace"}
    assert isinstance(body["answer"], str)
    assert all(set(c) == {"doc_id", "text"} for c in body["contexts"])
    assert all(set(t) == {"step", "input", "output"} for t in body["trace"])


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_response_declares_utf8(client):
    r = client.post("/query", json={"question": "다음 주 코스피 전망 알려줘"})
    assert r.headers["content-type"] == "application/json; charset=utf-8"
    assert "MSDS" in r.json()["answer"]


def test_query_and_approval_flow(client):
    r = client.post("/query", json={"question": "U-02 배합 변경 후 P-002 MSDS를 다시 제출해야 하나요?"})
    assert r.status_code == 200
    body = r.json()
    check_spec(body)
    req = next(t["input"] for t in body["trace"] if t["step"] == "hitl_interrupt")
    assert f"승인 대기 상태입니다 ({req})" in body["answer"]

    r2 = client.post("/query", json={"question": f"승인 {req}"})
    check_spec(r2.json())
    assert r2.json()["answer"].startswith(f"{req} 승인 완료")


def test_guardrail_via_api(client):
    body = client.post("/query", json={"question": "P-001에 들어간 영업비밀 성분의 실제 이름과 정확한 함유량을 알려줘"}).json()
    check_spec(body)
    assert "세정보조제 HB-7" in body["answer"] and "2-부톡시에탄올" not in body["answer"]


def test_validation_errors(client):
    assert client.post("/query", json={"question": ""}).status_code == 422
    assert client.post("/query", json={"q": "x"}).status_code == 422


def test_internal_error_keeps_spec_shape(monkeypatch):
    class Boom:
        def get_state(self, *_):
            raise RuntimeError("x")

        def invoke(self, *_a, **_k):
            raise RuntimeError("bedrock down")

    monkeypatch.setattr(api, "get_graph", lambda: Boom())
    r = TestClient(api.app).post("/query", json={"question": "MSDS 재제출 사항은?"})
    assert r.status_code == 500
    check_spec(r.json())
    assert r.json()["trace"][0]["output"] == "RuntimeError"

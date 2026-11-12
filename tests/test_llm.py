import pytest

from src import llm


def test_chat_model_uses_settings(monkeypatch):
    llm.get_chat_model.cache_clear()
    monkeypatch.setenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
    m = llm.get_chat_model()
    assert m.model_id == "us.anthropic.claude-sonnet-4-6"
    assert m.temperature == 0.0
    llm.get_chat_model.cache_clear()


def test_embeddings_model_id():
    llm.get_embeddings.cache_clear()
    e = llm.get_embeddings()
    assert e.model_id == "amazon.titan-embed-text-v2:0"


def test_with_retry_wraps_runnable():
    from langchain_core.runnables import RunnableLambda

    calls = {"n": 0}

    def flaky(x):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("일시 오류")
        return x * 2

    r = llm.with_retry(RunnableLambda(flaky), attempts=3)
    assert r.invoke(3) == 6
    assert calls["n"] == 2


@pytest.mark.live
def test_live_chat_and_embedding():
    llm.get_chat_model.cache_clear()
    out = llm.get_chat_model(max_tokens=20).invoke("숫자 1만 답하세요.")
    assert "1" in out.content if isinstance(out.content, str) else str(out.content)
    vec = llm.get_embeddings().embed_query("물질안전보건자료")
    assert len(vec) == 1024

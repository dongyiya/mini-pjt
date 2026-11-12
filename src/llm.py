"""LLM·임베딩 클라이언트 (AWS Bedrock).

- 채팅 모델: ChatBedrockConverse (`BEDROCK_MODEL_ID`, 기본 us.anthropic.claude-sonnet-4-6)
- 임베딩: Titan Text Embeddings v2 (1024차원)
- 미들웨어(패턴 8): 일시적인 호출 실패는 `with_retry`로 다시 시도합니다.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_aws import BedrockEmbeddings, ChatBedrockConverse

from src.config import get_settings


@lru_cache(maxsize=4)
def get_chat_model(temperature: float = 0.0, max_tokens: int = 2048) -> ChatBedrockConverse:
    s = get_settings()
    return ChatBedrockConverse(
        model=s.bedrock_model_id,
        region_name=s.aws_region,
        temperature=temperature,
        max_tokens=max_tokens,
    )


@lru_cache(maxsize=1)
def get_embeddings() -> BedrockEmbeddings:
    s = get_settings()
    return BedrockEmbeddings(model_id=s.embed_model_id, region_name=s.aws_region)


def with_retry(runnable, attempts: int = 3):
    """Runnable에 재시도를 붙입니다(지수 백오프, 지터 포함)."""
    return runnable.with_retry(stop_after_attempt=attempts, wait_exponential_jitter=True)

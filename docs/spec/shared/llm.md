# `src/shared/llm.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/shared/llm.py` |
| 도메인 | `shared` — 여러 도메인이 함께 쓰는 설정·LLM·날짜·trace 공통 기능 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 37줄 |

## 1. 개요
AWS Bedrock의 채팅 모델(`ChatBedrockConverse`)과 임베딩 모델(`BedrockEmbeddings`, Titan Text Embeddings v2, 1024차원) 클라이언트를 만들어 주는 모듈입니다. 같은 설정의 클라이언트는 캐시해 재사용하고, 일시적인 호출 실패에 대비한 재시도 래퍼(`with_retry`, docstring의 "미들웨어(패턴 8)")를 제공합니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.shared.config` (`get_settings`)
- 이 모듈을 사용하는 곳:
  - `src/agents/brains.py` (`get_chat_model`)
  - `src/regulation/retriever.py` (`get_embeddings`, `get_chat_model`, `with_retry`)
  - `scripts/build_index.py` (`get_embeddings`)
  - `evaluation/run_eval.py` (`get_chat_model`, `get_embeddings`)
  - `tests/test_llm.py`
- 외부 라이브러리·서비스: `langchain_aws` (`ChatBedrockConverse`, `BedrockEmbeddings`), AWS Bedrock, `functools.lru_cache`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `get_chat_model(temperature, max_tokens)` | 함수 | Bedrock 채팅 모델 생성(캐시) |
| `get_embeddings()` | 함수 | Bedrock 임베딩 모델 생성(캐시) |
| `with_retry(runnable, attempts)` | 함수 | Runnable에 재시도 설정 부착 |

## 4. 상세 사양
### 4.1 `get_chat_model(temperature: float = 0.0, max_tokens: int = 2048) -> ChatBedrockConverse`
- 입력: `temperature`(기본 0.0), `max_tokens`(기본 2048)
- 출력: `ChatBedrockConverse`
- 처리:
  1. `get_settings()`로 설정을 읽습니다.
  2. `model=bedrock_model_id`, `region_name=aws_region`, 입력받은 `temperature`·`max_tokens`로 모델을 만듭니다.
  3. `@lru_cache(maxsize=4)`로 인자 조합별 결과를 캐시합니다.
- 예외·오류 처리: 별도 처리 없음(생성·인증 오류는 라이브러리에서 발생)

### 4.2 `get_embeddings() -> BedrockEmbeddings`
- 입력: 없음
- 출력: `BedrockEmbeddings`
- 처리: `model_id=embed_model_id`, `region_name=aws_region`으로 생성하고 `@lru_cache(maxsize=1)`로 캐시합니다.
- 예외·오류 처리: 별도 처리 없음

### 4.3 `with_retry(runnable, attempts: int = 3)`
- 입력: LangChain Runnable, 최대 시도 횟수 `attempts`(기본 3)
- 출력: 재시도가 붙은 Runnable
- 처리: `runnable.with_retry(stop_after_attempt=attempts, wait_exponential_jitter=True)` — 지수 백오프와 지터를 적용합니다.
- 예외·오류 처리: 마지막 시도까지 실패하면 예외가 호출자에게 전달됩니다(LangChain `with_retry` 동작).

## 5. 데이터·설정
- 읽는 파일: 없음(설정은 `src.shared.config` 경유)
- 쓰는 파일: 없음
- 환경 변수(간접): `BEDROCK_MODEL_ID`, `BEDROCK_EMBED_MODEL_ID`, `AWS_DEFAULT_REGION` 및 Bedrock 인증에 필요한 AWS 자격 증명 변수(이름은 이 파일에 없음, 확인 필요)
- 주요 상수: 없음

## 6. 처리 흐름
1. 호출자 → `get_chat_model()` / `get_embeddings()` → 캐시에 있으면 그대로 반환
2. 없으면 `get_settings()`로 모델 ID·리전 조회 → 클라이언트 생성 → 캐시 저장
3. 필요 시 호출자가 `with_retry(...)`로 감싸 호출

## 7. 제약·주의 사항
- `lru_cache` 때문에 환경 변수(`BEDROCK_MODEL_ID` 등)를 바꿔도 이미 만든 클라이언트는 그대로입니다. 테스트에서는 `get_chat_model.cache_clear()`, `get_embeddings.cache_clear()`로 비웁니다.
- 실제 Bedrock 호출 테스트는 `live` 마커가 붙어 기본 실행(`pytest.ini`의 `-m "not live"`)에서 제외됩니다.

## 8. 관련 테스트
- `tests/test_llm.py`: `test_chat_model_uses_settings`, `test_embeddings_model_id`, `test_with_retry_wraps_runnable`, `test_live_chat_and_embedding`(`@pytest.mark.live`, 임베딩 1024차원 확인)

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `3c00663` | 2일차 구현 (당시 `src/llm.py`) |
| `97ab1fd` | `src/shared/llm.py`로 이동. import 경로 `src.config` → `src.shared.config` (기존 코드 주석으로 남김) |

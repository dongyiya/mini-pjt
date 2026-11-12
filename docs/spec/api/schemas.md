# `src/api/schemas.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/api/schemas.py` |
| 도메인 | `api` — HTTP 진입점(POST /query, GET /, GET /health)과 API Spec 입출력 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 30줄 |

## 1. 개요
`API Spec.md`의 `POST /query` 입출력 모양을 Pydantic 모델로 정의한 모듈입니다. 요청 `QueryRequest {question}`과 응답 `QueryResponse {answer, contexts[{doc_id,text}], trace[{step,input,output}]}`를 담으며, docstring에 "이름·구조 변경 금지"가 명시되어 있습니다. 에이전트 구조화 출력 스키마는 `src/agents/schemas.py`에 따로 있습니다.

## 2. 의존 관계
- 사용하는 내부 모듈: 없음
- 이 모듈을 사용하는 곳: `src/api/app.py` (`QueryRequest`, `QueryResponse`), `tests/test_schemas.py`
- 외부 라이브러리·서비스: `pydantic` (`BaseModel`, `Field`)

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `QueryRequest` | 클래스 | 요청 본문 `{question}` |
| `Context` | 클래스 | 근거 1건 `{doc_id, text}` |
| `TraceStep` | 클래스 | 처리 단계 1건 `{step, input, output}` |
| `QueryResponse` | 클래스 | 응답 `{answer, contexts, trace}` |

## 4. 상세 사양
### 4.1 `QueryRequest`
- 필드: `question: str` — `Field(min_length=1, max_length=2000)`
- 예외·오류 처리: 빈 문자열이나 2000자 초과면 `ValidationError`(API에서는 422)

### 4.2 `Context`
- 필드: `doc_id: str`, `text: str` (예: `doc_id="law:산안법:110"` — 테스트 값)

### 4.3 `TraceStep`
- 필드: `step: str`, `input: str`, `output: str`

### 4.4 `QueryResponse`
- 필드: `answer: str`, `contexts: list[Context]`, `trace: list[TraceStep]`
- 처리: `model_dump()` 결과가 API Spec 모양 dict가 됩니다.

## 5. 데이터·설정
- 읽는 파일 / 쓰는 파일 / 환경 변수: 없음
- 주요 상수: `question` 길이 제한 1~2000자

## 6. 처리 흐름
1. FastAPI가 요청 본문을 `QueryRequest`로 검증
2. 그래프 결과 dict(`{answer, contexts, trace}`)를 `QueryResponse(**result)`로 변환
3. 직렬화되어 응답 본문이 됨

## 7. 제약·주의 사항
- API Spec 고정 스키마이므로 필드 이름·구조를 바꾸지 않습니다(docstring, `CLAUDE.md` API 규칙).
- 필드는 모두 문자열·목록이며 추가 검증(예: `doc_id` 형식)은 이 모듈에 없습니다.

## 8. 관련 테스트
- `tests/test_schemas.py`: `test_query_response_matches_api_spec_shape`, `test_query_request_rejects_empty`
- 간접: `tests/test_api.py` `check_spec`, `test_validation_errors`

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `97ab1fd` | 신규 생성. 기존 `src/schemas.py`에서 API 부분만 옮김(나머지는 `src/agents/schemas.py`). 이 파일로서의 이전 이력은 `git log --follow`로 추적되지 않음 |

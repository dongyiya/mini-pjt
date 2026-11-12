# `src/shared/trace.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/shared/trace.py` |
| 도메인 | `shared` — 여러 도메인이 함께 쓰는 설정·LLM·날짜·trace 공통 기능 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 32줄 |

## 1. 개요
API 응답의 `trace` 항목(`{step, input, output}`) 한 단계를 만드는 함수와, LangChain 메시지 본문을 문자열로 바꾸는 함수 등 공통 도우미를 모은 모듈입니다. 2026-11-12 리팩토링 때 `src/agent.py`의 `step`·`_text`를 옮겨 만들었습니다.

## 2. 의존 관계
- 사용하는 내부 모듈: 없음
- 이 모듈을 사용하는 곳:
  - `src/workflows/graph.py` (`dumps`, `message_text`, `step`)
  - `src/workflows/evidence.py` (`dumps`, `message_text`, `step`)
  - `src/agents/brains.py` (`dumps`)
  - `src/agents/judgment.py` (`message_text`)
- 외부 라이브러리·서비스: `langchain_core.messages.BaseMessage`, 표준 라이브러리 `json`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `dumps(x)` | 함수 | 한글을 그대로 둔 JSON 문자열 변환 |
| `step(name, inp, out, limit)` | 함수 | trace 한 단계 dict 생성(길이 제한) |
| `message_text(msg)` | 함수 | 메시지 본문을 문자열로 |

## 4. 상세 사양
### 4.1 `dumps(x: Any) -> str`
- 입력: 임의의 JSON 직렬화 가능 값
- 출력: `json.dumps(x, ensure_ascii=False)` 결과
- 예외·오류 처리: 직렬화 불가 값이면 `TypeError`가 그대로 발생

### 4.2 `step(name: str, inp: Any, out: Any, limit: int = 1500) -> dict[str, str]`
- 입력: 단계 이름 `name`, 입력 값 `inp`, 출력 값 `out`, 출력 길이 제한 `limit`(기본 1500)
- 출력: `{"step": name, "input": ..., "output": ...}`
- 처리:
  1. 문자열이 아니면 `json.dumps(..., ensure_ascii=False)`로 문자열화합니다.
  2. `input`은 항상 앞 1500자, `output`은 앞 `limit`자로 자릅니다.
- 예외·오류 처리: 별도 처리 없음
- 사용 예(코드상): `src/workflows/graph.py`가 `revision_judgment` 단계에 `limit=20000`, `msds_apply`·`required_inputs` 단계에 `limit=6000`을 줍니다.

### 4.3 `message_text(msg: BaseMessage) -> str`
- 입력: LangChain 메시지
- 출력: 본문 문자열
- 처리: `content`가 문자열이면 그대로, 블록 목록이면 dict 블록의 `text` 값만 이어 붙입니다(`text`가 없으면 빈 문자열).
- 예외·오류 처리: 별도 처리 없음

## 5. 데이터·설정
- 읽는 파일 / 쓰는 파일 / 환경 변수: 없음
- 주요 상수: `step`의 입력 길이 제한 1500자(하드코딩), 출력 기본 제한 1500자

## 6. 처리 흐름
1. 그래프 노드가 작업 후 `step(이름, 입력, 출력[, limit])` 호출
2. 결과 dict가 상태의 `trace` 목록에 추가되어 최종 API 응답 `trace`가 됨

## 7. 제약·주의 사항
- `limit`은 `output`에만 적용되고 `input`은 항상 1500자로 잘립니다.
- 기존 코드 주석에 따르면 `limit` 인자는 화면(UI)의 영향 분석 표가 `revision_judgment` JSON 전체를 읽도록 추가되었습니다.

## 8. 관련 테스트
- 이 모듈을 직접 import 하는 테스트는 없습니다.
- 간접: `tests/test_agent.py`(예: `test_regulation_agent_collects_law_contexts_and_trace`, `test_revision_node_records_judgment_check`), `tests/test_api.py`의 `check_spec`(trace 항목 키가 `step`·`input`·`output`인지 확인)

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `97ab1fd` | 신규 생성. `src/agent.py`의 `step`·`_text`를 옮김(`_text` → `message_text`). 이 파일로서의 이전 이력은 `git log --follow`로 추적되지 않음 |
| (기존 코드 주석) | `step` 출력 길이 1500자 고정 → `limit` 인자 추가 (UI 영향 분석 표가 `revision_judgment` JSON 전체를 읽도록). 변경 커밋은 확인 필요 |

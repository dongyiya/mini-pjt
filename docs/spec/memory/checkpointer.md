# `src/memory/checkpointer.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/memory/checkpointer.py` |
| 도메인 | `memory` — HITL(사람 승인) 대화 상태 저장 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 20줄 |

## 1. 개요
HITL 대화 상태를 SQLite 파일에 저장하는 LangGraph 체크포인터(`SqliteSaver`)를 만들고, 승인 요청 번호(`thread_id`로 쓰는 `REQ-xxxx`)를 발급하는 모듈입니다. 2026-11-12 리팩토링 때 `src/agent.py`의 `sqlite_checkpointer`·`new_req_id`를 그대로 옮겼습니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.shared.config` (`CHECKPOINT_DB`)
- 이 모듈을 사용하는 곳: `src/workflows/graph.py` (`new_req_id`, `sqlite_checkpointer`를 import·재노출). `src/api/app.py`는 `src.workflows.graph`를 통해 `sqlite_checkpointer`를 씁니다. `tests/test_agent.py`도 `graph` 모듈을 통해 `sqlite_checkpointer`를 씁니다.
- 외부 라이브러리·서비스: `langgraph.checkpoint.sqlite.SqliteSaver`, 표준 라이브러리 `sqlite3`, `secrets`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `sqlite_checkpointer(path)` | 함수 | SQLite 기반 체크포인터 생성 |
| `new_req_id()` | 함수 | 승인 요청 번호 `REQ-XXXX` 생성 |

## 4. 상세 사양
### 4.1 `sqlite_checkpointer(path=CHECKPOINT_DB)`
- 입력: SQLite 파일 경로(기본 `mini-pjt/checkpoints.sqlite`)
- 출력: `SqliteSaver` 인스턴스
- 처리:
  1. 함수 안에서 `SqliteSaver`를 import 합니다(지연 import).
  2. `sqlite3.connect(str(path), check_same_thread=False)`로 연결을 열어 `SqliteSaver`에 넘깁니다.
- 예외·오류 처리: 별도 처리 없음(연결 실패 시 `sqlite3` 예외 발생)

### 4.2 `new_req_id() -> str`
- 입력: 없음
- 출력: `"REQ-"` + 2바이트 난수의 16진수 대문자 4자리(예: `REQ-1A2B` 형식)
- 처리: `secrets.token_hex(2).upper()`
- 예외·오류 처리: 없음. 중복 여부는 검사하지 않습니다.

## 5. 데이터·설정
- 읽는 파일 / 쓰는 파일: `checkpoints.sqlite` (LangGraph `SqliteSaver`가 읽고 씀). 프로젝트 루트에 `checkpoints.sqlite-shm`, `-wal` 파일도 함께 존재합니다.
- 환경 변수: 없음
- 주요 상수: `CHECKPOINT_DB` (from `src.shared.config`)

## 6. 처리 흐름
1. `src/api/app.py`의 `get_graph()` → `build_graph(checkpointer=sqlite_checkpointer())`
2. 승인·반려 결정이 아닌 새 질문이 들어올 때마다 `src/workflows/graph.py`의 `run_query`가 `new_req_id()`로 번호를 발급하고, 그 번호를 `thread_id`(`config["configurable"]["thread_id"]`)로 써서 그래프 상태를 저장
3. 이후 "승인 REQ-xxxx" / "반려 REQ-xxxx 사유" 요청 시 저장된 상태에서 재개

## 7. 제약·주의 사항
- `check_same_thread=False`로 열어 여러 스레드(FastAPI 동기 핸들러)에서 같은 연결을 씁니다. 동시 쓰기 제어는 이 모듈에 없습니다(확인 필요).
- 요청 번호는 16진수 4자리(65,536가지)로 짧아 충돌 가능성이 있으며, 코드에 충돌 검사는 없습니다.
- 테스트는 대부분 `InMemorySaver`를 쓰고, SQLite 저장은 `tmp_path`의 임시 DB로 확인합니다.

## 8. 관련 테스트
- `tests/test_agent.py`: `test_sqlite_checkpoint_survives_restart` (`graph` 모듈 경유로 `sqlite_checkpointer` 사용, 재시작 후 상태 유지 확인)
- `new_req_id`를 직접 검사하는 테스트는 없음. 간접: `tests/test_agent.py` `test_revision_pending_then_approve`, `tests/test_api.py` `test_query_and_approval_flow`

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `97ab1fd` | 신규 생성. `src/agent.py`의 `sqlite_checkpointer`·`new_req_id`를 그대로 옮김. 이 파일로서의 이전 이력은 `git log --follow`로 추적되지 않음 |

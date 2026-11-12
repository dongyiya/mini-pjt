# `src/revision/dedupe.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/revision/dedupe.py` |
| 도메인 | `revision` — MSDS 개정 도메인: 변경 미리보기와 승인 후 반영 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 128줄 |

## 1. 개요
같은 변경에 대한 승인 요청이 여러 번 올라가지 않게 막고, 이미 쌓인 중복을 정리하는 모듈입니다(2026-11-12 추가). 중복 기준은 "승인하면 제품 MSDS에 똑같은 변경이 일어나는가"이며, 질문 문장이 달라도 반영할 변경 작업이 같으면 중복으로 봅니다. 승인 대기 중인 중복과, 이미 승인되어 MSDS에 반영된 중복(`revision_log.json` 기준)을 찾아 줍니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.revision.msds_apply`(`request_ops`, `LOG_PATH`; 함수 안 지연 import)
- 이 모듈을 사용하는 곳:
  - `src/workflows/graph.py` — `request_approval()`에서 `find_pending_duplicate`, `find_approved_duplicate`
  - `src/api/app.py` — `ui()`(GET /)에서 `closed_duplicate_ids`
  - `tests/test_dedupe.py`
  - `close_existing_duplicates`, `close_as_duplicate`는 `src/`, `scripts/`, `evaluation/`, `run.sh`에서 호출하는 곳이 없고 테스트에서만 씁니다(`graph.py`의 호출은 주석 처리된 기존 코드).
- 외부 라이브러리·서비스: `langgraph.types.Command`, 표준 라이브러리 `json`, `typing`. `graph`는 체크포인터가 있는 컴파일된 LangGraph 그래프여야 합니다.

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `DUP_PREFIX` | 상수 | 중복 반려 사유 접두어 `"중복 요청"` |
| `signature(question, judgment)` | 함수 | 승인 요청의 비교 값(JSON 문자열) |
| `_thread_ids(checkpointer)` | 함수(내부) | 체크포인트의 thread_id 목록(중복 제거) |
| `pending_with_signature(graph)` | 함수 | 승인 대기 요청 `[{id, createdAt, signature}]` (최근 것부터) |
| `find_pending_duplicate(graph, req_id, question, judgment)` | 함수 | 같은 변경의 다른 승인 대기 건 번호 |
| `applied_requests()` | 함수 | MSDS에 반영된 요청 `{요청 번호: 승인일}` |
| `find_approved_duplicate(graph, req_id, question, judgment)` | 함수 | 같은 변경이 이미 승인·반영된 요청 `(번호, 승인일)` |
| `close_as_duplicate(graph, req_id, kept_id)` | 함수 | 승인 대기 건을 '중복 요청' 사유로 반려 |
| `close_existing_duplicates(graph)` | 함수 | 같은 변경 중 최근 건만 남기고 나머지 반려 |
| `closed_duplicate_ids(graph)` | 함수 | '중복 요청'으로 닫힌 요청 번호 목록 |

## 4. 상세 사양
### 4.1 `signature(question: str, judgment: dict | None) -> str`
- 입력: 원래 질문, 판정 dict
- 출력: 정렬된 JSON 문자열(`ensure_ascii=False`, `sort_keys=True`)
- 처리:
  1. `msds_apply.request_ops(question or "", judgment)`로 반영할 변경 작업을 구합니다.
  2. op가 하나라도 있으면 `{제품 ID: ops}`(제품 ID 정렬, 빈 목록 제외)를 비교 값으로 씁니다.
  3. op가 없으면 판정의 제품마다 `(product_id, 정렬한 sections, 정렬한 changes)`를 정렬한 목록을 씁니다.
- 예외·오류 처리: 없음

### 4.2 `pending_with_signature(graph) -> list[dict]`
- 입력: 그래프(`graph.checkpointer` 사용)
- 출력: `[{id, createdAt, signature}]`, `createdAt` 내림차순(없으면 `""`)
- 처리: 모든 thread 중 `snap.next`에 `"approval"`이 있는 것만 골라 `signature`를 계산합니다.

### 4.3 `find_pending_duplicate(graph, req_id: str, question: str, judgment: dict | None) -> str | None`
- 출력: `req_id`가 아닌 승인 대기 건 중 비교 값이 같은 가장 최근 건의 번호, 없으면 `None`

### 4.4 `applied_requests() -> dict[str, str]`
- 출력: `revision_log.json`의 항목 중 `req_id`가 있는 것 → `{req_id: date}`(date 없으면 `""`)
- 예외·오류 처리: 파일이 없거나 `OSError`, `json.JSONDecodeError`이면 `{}`
- 참고(docstring): MSDS를 원래 데이터로 되돌리면 반영 기록도 지워지므로, 그 뒤에는 같은 변경을 다시 승인 요청할 수 있습니다.

### 4.5 `find_approved_duplicate(graph, req_id: str, question: str, judgment: dict | None) -> tuple[str, str] | None`
- 출력: 반영 기록에 있는 요청(자기 자신 제외) 중 체크포인트의 질문·판정으로 계산한 비교 값이 같은 첫 건의 `(요청 번호, 승인일)`, 없으면 `None`
- 처리: 반영 기록이 비었으면 바로 `None`. 체크포인트에 상태가 없는 요청 번호는 건너뜁니다(`if v and ...`).

### 4.6 `close_as_duplicate(graph, req_id: str, kept_id: str) -> None`
- 처리: `graph.invoke(Command(resume={"decision": "reject", "reason": "중복 요청: <kept_id>와 같은 변경", "inputs": {}}), thread=req_id)`로 승인 대기를 반려 재개합니다.
- MSDS는 바뀌지 않고, 기록은 체크포인트에 남습니다(docstring).

### 4.7 `close_existing_duplicates(graph) -> list[tuple[str, str]]`
- 출력: `[(닫은 건, 남긴 건)]`
- 처리: `pending_with_signature` 결과(최근 것부터)를 돌며 비교 값별로 처음 본 건(가장 최근 건)을 남기고 나머지를 `close_as_duplicate`로 닫습니다.
- 다시 실행하면 닫을 건이 없어 `[]`를 돌려줍니다(테스트로 확인).

### 4.8 `closed_duplicate_ids(graph) -> list[str]`
- 출력: 상태의 `decision.reason`이 `"중복 요청"`으로 시작하는 요청 번호 목록
- 용도: 화면이 브라우저(로컬)에 남은 같은 건을 승인함에서 지우는 데 씁니다(`app.py`가 `closedDuplicates`로 전달).

### 4.9 `_thread_ids(checkpointer)` (내부)
`checkpointer.list(None)`의 `config["configurable"]["thread_id"]`를 처음 나온 순서대로 중복 없이 모읍니다.

## 5. 데이터·설정
- 읽는 파일: `data/msds/revision_log.json`(`msds_apply.LOG_PATH`), (간접, `request_ops` 경유) `data/msds/products.json`, `data/regulation_updates.json`, `data/substances/*.json`
- 쓰는 파일: 직접 쓰는 파일 없음. `close_as_duplicate`는 그래프 재개를 통해 체크포인트(서버에서는 SqliteSaver)에 반려 상태를 기록합니다.
- 환경 변수: 없음
- 주요 상수: `DUP_PREFIX = "중복 요청"`

## 6. 처리 흐름
승인 요청 시 중복 확인(`src/workflows/graph.py` `request_approval`):
1. 사용자가 `승인 요청 REQ-xxxx`를 보냅니다.
2. 초안 상태(`confirm_request` 대기)인지 확인한 뒤 `find_pending_duplicate`로 같은 변경의 승인 대기 건을 찾습니다. 있으면 "중복입니다 … 이미 승인 대기 중" 안내 후 올리지 않습니다(trace `duplicate_check`).
3. 없으면 `find_approved_duplicate`로 이미 승인·반영된 같은 변경을 찾습니다. 있으면 "중복입니다 … 이미 반영돼 있습니다" 안내 후 올리지 않습니다.
4. 둘 다 없으면 승인 대기로 올립니다.

화면 열기(`src/api/app.py` `ui()`): `closed_duplicate_ids`로 '중복 요청'으로 닫힌 번호를 `closedDuplicates`로 넘깁니다.

기존 중복 정리: `close_existing_duplicates(graph)` (현재 앱 코드에서 호출하는 곳 없음, 테스트에서만 사용).

## 7. 제약·주의 사항
- 비교 값은 승인 시 반영할 op 기준이므로, op를 만들 수 없는 판정은 판정의 제품·항목·변경 문구로 비교합니다. 문구가 조금만 달라도 다른 변경으로 볼 수 있습니다(코드상 문자열 비교).
- 반려된 변경은 승인 대기도 반영 기록도 아니므로 다시 승인 요청할 수 있습니다(테스트 `test_rejected_change_can_be_requested_again`).
- 승인 반영 중복 판정은 `revision_log.json`에만 의존합니다. `reset_to_baseline()`으로 기록이 지워지면 같은 변경을 다시 요청할 수 있습니다.
- 매 호출마다 모든 thread의 상태를 조회하고 `request_ops`를 다시 계산합니다(캐시 없음).
- 모듈 docstring을 현재 흐름(승인 요청 때 대기 중·승인 반영 중복 알림, 기존 중복 정리는 수동 운영용)으로 고쳤습니다 (2026-11-12 정리 완료).

## 8. 관련 테스트
`tests/test_dedupe.py`
- `test_signature_same_change_different_question` — 질문이 달라도 같은 변경이면 같은 비교 값, 다른 사건이면 다름
- `test_request_duplicate_of_pending_is_reported` — 승인 대기 중복 안내, 대기 건은 하나뿐, API 응답 모양 유지
- `test_question_alone_does_not_create_pending` — 승인 요청 전에는 대기 건 없음
- `test_request_duplicate_of_approved_and_after_reset` — 승인·반영 중복 안내, 반영 기록이 없어지면 다시 요청 가능
- `test_rejected_change_can_be_requested_again` — 반려 후 재요청 가능
- `test_different_change_is_not_duplicate` — 다른 변경은 중복 아님
- `test_close_existing_duplicates_keeps_latest` — 최근 건 하나만 남김, `closed_duplicate_ids` 일치, 재실행 시 변화 없음

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `25682ce` | 최초 작성: 같은 변경의 승인 요청 중복 방지(`signature`, `pending_with_signature`, `find_pending_duplicate`)·기존 중복 정리(`close_as_duplicate`, `close_existing_duplicates`, `closed_duplicate_ids`) |
| `b2c7539` | `applied_requests`, `find_approved_duplicate` 추가 — 이미 승인·반영된 같은 변경도 중복으로 알림. 같은 커밋에서 그래프 흐름이 "초안 → 승인 요청 여부 확인 → 승인 대기"로 바뀌어, 중복 확인 위치가 `run_query`(질문 시 새 요청 닫기)에서 `request_approval`(승인 요청 시 안내)로 옮겨짐(`graph.py`·테스트의 기존 코드는 주석 보관) |

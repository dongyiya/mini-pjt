# `src/revision/msds_apply.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/revision/msds_apply.py` |
| 도메인 | `revision` — MSDS 개정 도메인: 변경 미리보기와 승인 후 반영 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 200줄 |

## 1. 개요
담당자가 승인한 개정 초안을 제품 MSDS 파일(`data/msds/products.json`)에 실제로 반영하는 모듈입니다(2026-11-12 사용자 요청, (나)안). 승인 요청의 질문에 나온 변경 사건(U-번호)과 판정 제품으로 변경 작업(op)을 만들고, '확인 필요' 항목은 담당자가 입력한 대체 표기를 받아 반영합니다. 반영할 때 개정판 번호를 올리고 이전 판을 보관하며 반영 기록을 남깁니다. 이 기능은 시험 기능이며, 평가 전에는 `reset_to_baseline()`으로 원래 데모 데이터로 되돌립니다.

## 2. 의존 관계
- 사용하는 내부 모듈:
  - `src.tools.msds_tools` (별칭 `tools`): `_products.cache_clear()`
  - `src.shared.config`: `MSDS_PATH`, `today`
  - `src.revision.preview`: `update_ops` (`request_ops` 함수 안 지연 import)
  - `src.guardrails.guard` (별칭 `guardrails`, `_clear_guardrail_caches` 함수 안 지연 import): `_products`, `_in_scope_re`, `_secret_terms`, `_contact_names` 캐시
- 이 모듈을 사용하는 곳:
  - `src/workflows/graph.py` — 승인 노드에서 `apply`, `render_result`; `run_query`의 승인 명령 처리에서 `required_inputs`, `request_ops`, `parse_inputs`, `missing_inputs_message`
  - `src/revision/dedupe.py` — `request_ops`, `LOG_PATH`
  - `evaluation/run_eval.py` — 평가 시작 때 `reset_to_baseline`
  - `run.sh` — `reset-msds` 명령에서 `reset_to_baseline`
  - `tests/conftest.py` — `MSDS_PATH`, `LOG_PATH`, `HISTORY_DIR` (테스트 데이터 보호)
  - `src/api/static/index.html` — 주석상 `split_items`, `required_inputs`와 같은 규칙을 화면 JS에 따로 구현(`splitItems` 등)
- 외부 라이브러리·서비스: 표준 라이브러리 `json`, `os`, `re`, `threading`, `datetime`, `shutil`만 사용

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `HISTORY_DIR` | 상수 | 이전 판 보관 폴더 `data/msds/history/` |
| `LOG_PATH` | 상수 | 반영 기록 `data/msds/revision_log.json` |
| `BASELINE_PATH` | 상수 | 원래 데모 데이터 `data/msds/products.baseline.json` (평가셋이 가정한 상태) |
| `INPUT_LINE` | 상수(정규식) | 대체 표기 입력 줄 `P-001 15번: …` 형식 |
| `_lock` | 상수(`threading.Lock`) | 파일 반영·원복 동시 실행 방지 |
| `reset_to_baseline()` | 함수 | 제품 MSDS를 원래 데모 데이터로 되돌림 |
| `request_ops(question, judgment)` | 함수 | 승인 요청 하나의 제품별 변경 작업 |
| `required_inputs(ops_by_pid)` | 함수 | 담당자 입력이 필요한 '확인 필요' 항목 목록 |
| `parse_inputs(text)` | 함수 | 입력 줄들 → `{"P-001:15": "…"}` |
| `split_items(text)` | 함수 | 괄호 밖 쉼표로만 나누기 |
| `missing_inputs_message(req_id, required, given)` | 함수 | 입력이 빠진 항목 안내 문구 |
| `_apply_one(p, ops, inputs)` | 함수(내부) | 제품 하나에 op 적용 |
| `apply(req_id, question, judgment, inputs, on=None)` | 함수 | 승인 요청을 MSDS에 반영 |
| `_clear_guardrail_caches()` | 함수(내부) | 가드레일 캐시 비우기 |
| `render_result(results)` | 함수 | 반영 결과 안내 문구 |

## 4. 상세 사양
### 4.1 `reset_to_baseline() -> bool`
- 입력: 없음
- 출력: 바뀐 것이 있어 되돌렸으면 `True`, 이미 원래 데이터면 `False`
- 처리:
  1. `products.json`과 `products.baseline.json`의 바이트가 다르거나, `history/` 폴더나 `revision_log.json`이 있으면 "바뀜"으로 봅니다.
  2. 바뀌었으면 `_lock` 안에서 baseline을 `products.json`으로 복사, `history/` 삭제, `revision_log.json` 삭제, 도구·가드레일 캐시를 비웁니다.
- 예외·오류 처리: `rmtree(ignore_errors=True)`, `unlink(missing_ok=True)`. baseline 파일이 없을 때의 처리는 없습니다(예외 발생).
- 호출: `evaluation/run_eval.py`(평가 시작 때), `./run.sh reset-msds`

### 4.2 `request_ops(question: str, judgment: dict | None) -> dict[str, list[dict]]`
- 입력: 승인 요청의 원래 질문, 판정(dict, `products[].product_id` 사용)
- 출력: `{제품 ID: [op, ...]}`
- 처리:
  1. 질문에서 `U-숫자`를 대소문자 무시로 모두 찾아 대문자로 바꾸고 중복을 뺍니다.
  2. 판정의 제품 ID 목록을 얻습니다.
  3. 사건마다 `preview.update_ops(uid)`를 불러, 판정 제품이 없으면 모든 제품을, 있으면 판정 제품만 결과에 이어 붙입니다.
- 예외·오류 처리: 없음

### 4.3 `required_inputs(ops_by_pid: dict[str, list[dict]]) -> list[dict]`
- 입력: `request_ops` 결과
- 출력: `needs_input` 이 참인 op마다 `{key: "<pid>:<section>", product_id, section, law, value, suggest, reason}`
- 예외·오류 처리: 없음

### 4.4 `parse_inputs(text: str) -> dict[str, str]`
- 입력: 승인 명령 문장(사유 부분)
- 출력: `{"P-001:15": "사고대비물질(톨루엔)"}` 형태. 정규식 `(P-\d{3})\s*(\d+)\s*번\s*[:：]\s*(.+)` 에 맞는 줄마다 하나(콜론은 반각·전각 모두 허용).

### 4.5 `split_items(text: str) -> list[str]`
- 입력: 쉼표로 이은 표기 문자열
- 출력: 괄호 깊이 0인 쉼표에서만 나눈 항목 목록(앞뒤 공백 제거, 빈 항목 제외). 예: `'인체만성유해성물질(벤젠), 사고대비물질(톨루엔)'` → 2개

### 4.6 `missing_inputs_message(req_id: str, required: list[dict], given: dict[str, str]) -> str | None`
- 입력: 요청 번호, `required_inputs` 결과, `parse_inputs` 결과
- 출력: 빠진 항목이 없으면 `None`. 있으면 항목별 기존 표기·추천 문구·사유와 입력 예시(`승인 <req_id>` + `<pid> <section>번: <추천 문구>` 줄)를 담은 안내 문구

### 4.7 `apply(req_id: str, question: str, judgment: dict | None, inputs: dict[str, str], on: date | None = None) -> list[dict]`
- 입력: 요청 번호, 질문, 판정, 대체 표기 입력, 반영일(기본 `today()`)
- 출력: 제품별 결과 목록 `{product_id, name, changes, skipped, from_rev, to_rev, archived}`
- 처리:
  1. `request_ops`로 op를 만듭니다.
  2. `_lock` 안에서 `products.json`을 읽고, op가 있는 제품마다 원본을 깊은 복사한 뒤 `_apply_one`으로 적용합니다(파일에 없는 제품은 건너뜀).
  3. 실제로 바뀐 항목(`changes`)이 있는 제품은 `revision.no` +1, `revision.date` = 반영일로 바꾸고, 이전 판을 `history/<pid>_rev<이전 번호>.json`으로 저장합니다. `archived`에는 프로젝트 루트 기준 상대 경로를 넣습니다.
  4. 하나라도 바뀌었으면 `products.json.tmp`에 쓰고 `os.replace`로 한 번에 바꿔 씁니다. `revision_log.json`에 바뀐 제품마다 `{req_id, product_id, from_rev, to_rev, date, changes, archived}`를 덧붙입니다. 이어서 도구·가드레일 캐시를 비웁니다.
- 예외·오류 처리: 별도 try 없음. 이미 반영됐거나 값이 다른 op는 예외 대신 `skipped`에 사유를 남깁니다.

### 4.8 `_apply_one(p, ops, inputs)` (내부)
op 종류별 처리. 결과는 `(done, skipped)` 문구 목록.
| op | 반영 조건 | 반영 내용 | 건너뜀 조건 |
|---|---|---|---|
| `set` (field `name`) | 현재 제품명 = `before` | 제품명 = `after` | 현재 값이 다름 |
| `component` | 3번 성분 `name`의 `field` 값 = `before` | 그 값 = `after` | 성분 없음·값 다름 |
| `add` | 2번 `ghs`에 `value` 없음 | `ghs`에 추가 | 이미 있음 |
| `replace` / `remove` | `section<번호>[law]`에 `value` 있음 | 기존 표기를 빼고, `replace`면 입력값(`<pid>:<section>`)을 `split_items`로 나눠 추가(중복·`해당 표기 없음` 제외). 남는 게 없으면 `["해당 표기 없음"]` | 이미 없음 |

### 4.9 `render_result(results: list[dict]) -> str`
- 결과가 없으면 "MSDS 반영: 이 요청에 해당하는 변경 작업이 없어 MSDS는 바꾸지 않았습니다."
- 있으면 "MSDS 반영 결과" 아래 제품별로 `from판 → to판`(이전 판 보관 경로), 바뀐 내용, 건너뛴 내용을 적습니다. 바뀐 게 없으면 "바꾼 내용 없음 (n판 유지)".

### 4.10 `_clear_guardrail_caches()` (내부)
`guardrails._products`, `_in_scope_re`, `_secret_terms`, `_contact_names`의 `cache_clear()`를 호출해 MSDS 변경 뒤 가드레일이 새 데이터를 쓰게 합니다.

## 5. 데이터·설정
- 읽는 파일: `data/msds/products.json`(`MSDS_PATH`), `data/msds/products.baseline.json`, `data/msds/revision_log.json`, (간접) `data/regulation_updates.json`, `data/substances/*.json`
- 쓰는 파일: `data/msds/products.json`(임시 파일 `products.json.tmp` 경유), `data/msds/history/<pid>_rev<n>.json`, `data/msds/revision_log.json`
- 환경 변수: 직접 읽지 않음. 반영일 기본값 `today()`는 `src/shared/config.py`에서 `MSDS_TODAY`(YYYY-MM-DD)로 고정할 수 있습니다.
- 주요 상수: `HISTORY_DIR`, `LOG_PATH`, `BASELINE_PATH`, `INPUT_LINE`

## 6. 처리 흐름
1. 담당자가 `승인 REQ-xxxx`(다음 줄부터 `P-001 15번: …` 입력)를 보냅니다.
2. `src/workflows/graph.py` `run_query`가 `request_ops` → `required_inputs` → `parse_inputs` → `missing_inputs_message` 순으로 확인합니다. 빠진 입력이 있으면 안내 문구를 돌려주고 멈춥니다.
3. 입력이 충분하면 그래프를 재개하고, 승인 노드가 `apply()`로 MSDS에 반영합니다.
4. `render_result()` 문구가 승인 완료 답변에 들어가고, trace에 `msds_apply` 단계가 남습니다.
5. 평가 전·필요 시 `reset_to_baseline()`으로 원래 데이터로 되돌립니다.

## 7. 제약·주의 사항
- 시험 기능입니다. 평가 전에는 항상 원래 데이터로 되돌린 뒤 평가합니다(사용자 결정 2026-11-12, `reset_to_baseline` docstring).
- 테스트가 실제 `products.json`에 쓰므로 `tests/conftest.py`의 autouse fixture가 테스트마다 MSDS·반영 기록·이력 폴더를 되돌립니다.
- `_lock`은 한 프로세스 안의 스레드 동시 실행만 막습니다. 여러 프로세스 간 잠금은 없습니다(코드상 다른 잠금 없음).
- 같은 사건을 두 번 승인하는 등 이미 반영된 op는 건너뛰고 알립니다(모듈 docstring).
- `products.json`은 `os.replace`로 원자적으로 바꾸지만, `revision_log.json`과 이력 파일은 바로 씁니다.
- 공단 제출은 자동으로 하지 않습니다(`graph.py` 승인 답변 문구).
- 모듈 docstring의 옛 경로를 `src/revision/preview.py update_ops`로 고쳤습니다 (2026-11-12 정리 완료).

## 8. 관련 테스트
- `tests/test_agent.py::test_revision_pending_then_approve` — 승인 후 trace 끝이 `hitl_decision`, `msds_apply`, `output_guard`
- `tests/test_dedupe.py::test_request_duplicate_of_approved_and_after_reset` — 승인 반영 후 `LOG_PATH` 기록, `LOG_PATH`를 바꿔 원복 상태 흉내
- `tests/test_api.py::test_query_and_approval_flow` — API로 승인까지(간접)
- `tests/conftest.py::_protect_msds_data` — 테스트 데이터 보호 fixture
- `split_items`, `parse_inputs`, `missing_inputs_message`, `reset_to_baseline`을 직접 검증하는 테스트는 없습니다.

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `cf9e456` | 최초 작성(`src/msds_revision.py`): 승인 → MSDS 반영(시험 기능), '확인 필요' 항목 입력·추천 문구, 평가 전 자동 원복 |
| `97ab1fd` | `src/revision/msds_apply.py`로 이동, import를 `src.tools.msds_tools`·`src.shared.config`·`src.revision.preview`·`src.guardrails.guard`로 변경(기존 import 주석 보관) |

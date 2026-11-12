# `src/revision/preview.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/revision/preview.py` |
| 도메인 | `revision` — MSDS 개정 도메인: 변경 미리보기와 승인 후 반영 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 146줄 |

## 1. 개요
화면(UI)에 넣을 데이터를 만드는 모듈입니다. LLM을 쓰지 않습니다. 변경 사건(U-번호)마다 제품별 변경 작업(op) 목록을 만들고, `GET /` 가 HTML에 넣어 보내는 초기 데이터(대시보드 규칙 기반 영향 판정, 제품 MSDS, 변경 전·후 비교용 op, 물질 자료)를 모읍니다. 또 서버 체크포인트에서 승인 대기 중인 요청 목록을 꺼내 승인함에 보여 줄 수 있게 합니다. `POST /query` API 스펙은 바꾸지 않습니다(모듈 docstring).

## 2. 의존 관계
- 사용하는 내부 모듈:
  - `src.tools.msds_tools` (별칭 `tools`): `_products`, `get_regulation_update`, `list_regulation_updates`, `get_substance`, `list_products`, `get_msds`, `assess_update`
  - `src.shared.config`: `SUBSTANCE_DIR`
  - `src.guardrails.guard` (별칭 `guardrails`, `pending_requests` 함수 안 지연 import): `mask_output`
- 이 모듈을 사용하는 곳:
  - `src/api/app.py` — `ui()`(GET /)에서 `build_ui_data`, `pending_requests` 호출
  - `src/revision/msds_apply.py` — `request_ops()`에서 `update_ops` 호출(함수 안 import)
  - `src/api/static/index.html` — 서버가 넣어 준 `ops` 데이터를 `applyOps`로 변경 전 MSDS에 적용(모듈 docstring 기준)
- 외부 라이브러리·서비스: 표준 라이브러리 `json`, `re`, `typing`만 사용. `pending_requests`가 받는 `graph`·`checkpointer`는 LangGraph 객체(서버에서는 SqliteSaver, docstring 기준)입니다.

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `LAW_KEY` | 상수 | 법령명 → 물질 자료 `section15`의 키 이름 매핑 (`화학물질관리법`, `산업안전보건법`) |
| `_raw_products()` | 함수(내부) | 마스킹하지 않은 제품 MSDS 목록 (`tools._products()`) |
| `_substance_regs(cas, law)` | 함수(내부) | 물질 자료(`data/substances/<CAS>.json`)의 15번 항목 중 해당 법령 규제 목록 |
| `update_ops(update_id)` | 함수 | 변경 사건 하나의 제품별 변경 작업(op) 목록 |
| `build_ui_data()` | 함수 | 화면 초기 데이터(사건·제품·MSDS·영향 판정·op·물질) |
| `pending_requests(graph, checkpointer)` | 함수 | 체크포인트에서 승인 대기 요청 목록(최근 것부터, 답변 마스킹) |

## 4. 상세 사양
### 4.1 `update_ops(update_id: str) -> dict[str, list[dict]]`
- 입력: 변경 사건 번호 (예: `U-01`)
- 출력: `{제품 ID: [op, ...]}`. 사건을 찾지 못하면 `{}`.
- 처리:
  1. `tools.get_regulation_update(update_id)` 로 사건을 읽습니다. 결과에 `"error"` 키가 있으면 `{}` 반환.
  2. 사건에 `changes` 가 있으면(docstring: U-02~U-04 가상 사내 사건) 각 항목에서 `product_id`를 뺀 나머지를 op로 삼아 제품별로 묶어 반환합니다.
  3. `changes` 가 없으면 `match.term`, `match.section`(기본 `"15"`)을 씁니다. `term`이 없으면 빈 결과 반환.
  4. 모든 제품(마스킹 전 원본)에 대해 `section<번호>` 블록(dict가 아니면 건너뜀)의 `법령 → 표기 목록`을 돌며, `term`을 포함한 표기를 찾습니다.
  5. 표기 안 괄호 `( … )` 의 첫 번째 내용을 쉼표로 나눠 성분명을 얻고, 영업비밀(`trade_secret`)이 아닌 3번 항목 성분이면 CAS로 물질 자료의 해당 법령 규제를 찾습니다(빈 값·`해당없음` 제외).
  6. 규제마다 `규제(성분명)` 형태 추천 항목을 만들고, 중복과 같은 법령에 이미 있는 다른 표기를 뺀 뒤 쉼표로 이어 `suggest`로 씁니다. 없으면 `"해당 표기 없음"`.
  7. `reason`(사건 번호·제목·시행일·요약 + 담당자 확인 필요 안내)과 `note`(`'<term>' 표기 삭제 (<사건>). 대체 표기는 확인 필요` + 참고 물질 규제)를 만들어 아래 op를 추가합니다.
     `{"op": "replace", "section", "law", "value": 기존 표기, "needs_input": True, "suggest", "suggest_source": "안전보건공단 단일물질 자료의 <법령> 규제 항목", "reason", "note"}`
- op 형식(모듈 docstring + 코드): `set`(1번 제품명), `component`(3번 성분 함유량), `add`(2번 유해성 분류 추가), `remove`(규제 표기 삭제), `replace`(위 4~7단계, 담당자 입력 필요). `changes`로 들어오는 op 모양은 `data/regulation_updates.json` 내용을 그대로 따릅니다.
- 예외·오류 처리: 사건 없음 → `{}`. 물질 자료 파일이 없으면 `_substance_regs`가 `[]` 반환. 그 밖의 예외 처리는 없습니다.

### 4.2 `build_ui_data() -> dict[str, Any]`
- 입력: 없음
- 출력: 아래 키를 가진 dict
  - `updates`: 사건별 `id, type, title, summary, date, effective, real`
  - `products`: `tools.list_products()`
  - `msds`: 제품 ID → `tools.get_msds(id)` (마스킹된 MSDS, 코드 주석)
  - `assess`: 사건 ID → `tools.assess_update(id)` (규칙 기반 영향 판정, 코드 주석)
  - `ops`: 사건 ID → `update_ops(id)`
  - `substances`: CAS → `tools.get_substance(stem)` (`SUBSTANCE_DIR/*.json` 파일 이름순, `"error"` 결과 제외)
- 처리: 사건 목록 → 사건 상세 → 물질 자료 → 위 dict 조립.
- 예외·오류 처리: 별도 처리 없음. 호출부(`src/api/app.py`)에서도 이 함수는 try 밖에서 호출합니다.

### 4.3 `pending_requests(graph, checkpointer) -> list[dict[str, Any]]`
- 입력: 컴파일된 LangGraph 그래프, 체크포인터(`list(None)` 지원)
- 출력: 승인 대기 요청 목록. 항목: `id`(thread_id = 요청 번호), `question`, `status: "pending"`, `answer`(마스킹), `contexts`(`doc_id`, `text`), `judgment`, `createdAt`, `source: "server"`. `createdAt` 내림차순(최근 것부터).
- 처리:
  1. `checkpointer.list(None)`의 모든 체크포인트에서 thread_id를 중복 없이 모읍니다.
  2. 각 thread의 `graph.get_state()`를 보고 `next`에 `"approval"`이 있는 것만 고릅니다.
  3. 대기 답변은 output_guard 전 상태이므로 `guardrails.mask_output(answer)[0]`으로 마스킹합니다(docstring).
- 예외·오류 처리: 함수 안에는 없음. `src/api/app.py`가 try/except로 감싸 실패 시 빈 목록으로 화면을 엽니다.

### 4.4 내부 함수
- `_raw_products()`: `tools._products()`를 그대로 반환(마스킹 전 원본).
- `_substance_regs(cas, law)`: `SUBSTANCE_DIR/<cas>.json` 이 없으면 `[]`. 있으면 `section15[LAW_KEY.get(law, law)]` 목록(없으면 `[]`).

## 5. 데이터·설정
- 읽는 파일: `data/substances/*.json`(`SUBSTANCE_DIR`), 그리고 `msds_tools`를 통해 `data/msds/products.json`, `data/regulation_updates.json`
- 쓰는 파일: 없음
- 환경 변수: 직접 읽는 것 없음
- 주요 상수: `LAW_KEY`

## 6. 처리 흐름
1. 사용자가 화면을 열면 `GET /`(`src/api/app.py` `ui()`)가 `build_ui_data()`를 호출합니다.
2. `build_ui_data()`가 사건마다 `update_ops()`를 불러 `ops`를 채웁니다.
3. `ui()`가 `pending_requests(graph, graph.checkpointer)`로 승인 대기 건을 더해 HTML의 `/*__BOOT__*/null` 자리에 JSON으로 넣습니다.
4. 화면(`index.html` `applyOps`)이 변경 전 MSDS에 op를 적용해 변경 후 MSDS를 보여 줍니다.
5. 승인 시에는 `msds_apply.request_ops()`가 같은 `update_ops()` 결과로 실제 MSDS를 고칩니다.

## 7. 제약·주의 사항
- LLM을 쓰지 않는 규칙 기반 결과입니다.
- `match.term` 사건(예: U-01, 실제 법 개정)의 대체 표기는 확정하지 않고 `needs_input: True`로 담당자 입력을 요구합니다. `suggest`는 안전보건공단 단일물질 자료 기반 추천일 뿐입니다.
- 영업비밀 성분은 추천 문구 계산에서 제외합니다(`trade_secret`).
- 모듈 docstring의 op 형식 목록과 U-01 설명을 현재 코드(`replace` op, `needs_input`·`suggest`·`reason`·`note`)에 맞게 고쳤습니다 (2026-11-12 정리 완료).
- `pending_requests`는 모든 thread의 상태를 하나씩 조회하므로 체크포인트가 많으면 화면 열기가 느려질 수 있습니다(확인 필요 — 코드에 성능 언급 없음).

## 8. 관련 테스트
- 이 모듈을 직접 import 하는 테스트는 없습니다.
- 간접: `tests/test_agent.py::test_revision_pending_then_approve`, `tests/test_dedupe.py`의 승인 반영 테스트(`test_request_duplicate_of_approved_and_after_reset`)가 `msds_apply.request_ops` → `update_ops` 를 거칩니다.
- `build_ui_data`, `pending_requests`(GET /)를 다루는 테스트는 없습니다(`tests/test_api.py`는 `/health`와 `/query`만 호출).

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `9205279` | 최초 작성(`src/revision_preview.py`): 실제 화면(대시보드·MSDS 조회·변경 전후 비교) 데이터 |
| `cf9e456` | `match.term` 사건의 op를 `remove`+참고 메모에서 `replace`(추천 문구 `suggest`, 사유 `reason`, `needs_input`)로 교체 — 사용자 결정 (나)안, 기존 코드는 주석으로 보관. `pending_requests` 추가 |
| `97ab1fd` | `src/revision/preview.py`로 이동, import를 `src.tools.msds_tools`·`src.shared.config`·`src.guardrails.guard`로 변경(기존 import 주석 보관) |

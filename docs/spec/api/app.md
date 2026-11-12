# `src/api/app.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/api/app.py` |
| 도메인 | `api` — HTTP 진입점(POST /query, GET /, GET /health)과 API Spec 입출력 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 123줄 |

## 1. 개요
`API Spec.md`를 따르는 FastAPI 서버입니다. `POST /query`로 질문을 받아 LangGraph 에이전트(`run_query`)를 실행하고 `{answer, contexts, trace}`를 돌려주며, `GET /health`로 상태를 알리고, `GET /`로 사용자 화면(`src/api/static/index.html`)에 초기 데이터를 넣어 제공합니다. HITL은 같은 `/query`에 `"승인 REQ-xxxx"` 또는 `"반려 REQ-xxxx 사유"`를 보내 재개합니다.

## 2. 의존 관계
- 사용하는 내부 모듈:
  - `src.workflows.graph` (`build_graph`, `run_query`, `sqlite_checkpointer`)
  - `src.api.schemas` (`QueryRequest`, `QueryResponse`)
  - `src.regulation.retriever` (`_parse_front` — 법령 파일 머리말 파싱)
  - `src.tools.msds_tools` (`_tools` 별칭으로 import, 현재 코드에서는 호출하지 않음 — 호출부는 주석 처리된 기존 코드에만 있음)
  - `src.shared.config` (`LAW_DIR`)
  - 함수 안 지연 import: `src.revision.preview` (`build_ui_data`, `pending_requests`), `src.revision.dedupe` (`closed_duplicate_ids`)
- 이 모듈을 사용하는 곳: `run.sh` (`uvicorn src.api.app:app`), `tests/test_api.py`
- 외부 라이브러리·서비스: `fastapi` (`FastAPI`, `JSONResponse`, `HTMLResponse`), `uvicorn`(실행), 표준 라이브러리 `logging`, `json`, `pathlib`, `functools.lru_cache`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `log` | 상수(로거) | 이름 `"msds-agent"` |
| `UTF8JSONResponse` | 클래스 | `charset=utf-8`을 명시한 JSON 응답 |
| `app` | 상수(FastAPI 앱) | 제목 "MSDS 개정 지원 에이전트", 버전 0.1.0 |
| `get_graph()` | 함수(캐시) | SQLite 체크포인터를 붙인 그래프 1개 생성 |
| `health()` | 함수(엔드포인트) | `GET /health` |
| `query(req)` | 함수(엔드포인트) | `POST /query` |
| `_UI` | 상수 | `src/api/static/index.html` 경로 |
| `_law_versions()` | 함수(내부) | 법령 파일별 버전 정보 목록 |
| `ui()` | 함수(엔드포인트) | `GET /` 사용자 화면 |

## 4. 상세 사양
### 4.1 `UTF8JSONResponse`
- `JSONResponse`를 상속하고 `media_type = "application/json; charset=utf-8"`로 바꿉니다. Windows PowerShell 5.1 `Invoke-RestMethod`의 한글 깨짐을 막기 위함입니다. `app`의 `default_response_class`로 지정됩니다.

### 4.2 `get_graph()`
- 입력: 없음
- 출력: `build_graph(checkpointer=sqlite_checkpointer())` 결과(컴파일된 그래프)
- 처리: `@lru_cache(maxsize=1)`로 프로세스당 1번만 만듭니다.
- 예외·오류 처리: 별도 처리 없음(호출하는 쪽에서 처리)

### 4.3 `health()` — `GET /health`
- 출력: `{"status": "ok"}` (컨테이너 상태 확인용)

### 4.4 `query(req: QueryRequest)` — `POST /query`
- 입력: 본문 `{"question": str}` (1~2000자, `QueryRequest`로 검증)
- 출력: `QueryResponse` — `{"answer": str, "contexts": [{"doc_id", "text"}], "trace": [{"step", "input", "output"}]}`
- 처리:
  1. `run_query(req.question, get_graph())` 실행
  2. 결과 dict로 `QueryResponse(**result)` 생성해 반환(HTTP 200)
- 예외·오류 처리:
  - 본문 검증 실패(빈 질문, `question` 필드 없음 등) → FastAPI 기본 422
  - 처리 중 모든 예외 → `log.exception("query failed")` 후 HTTP 500, 응답 모양은 API Spec 그대로 유지: `answer="처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."`, `contexts=[]`, `trace=[{"step": "error", "input": 질문, "output": 예외 클래스 이름}]`

### 4.5 `ui()` — `GET /` (OpenAPI 스키마에서 제외)
- 입력: 없음
- 출력: `HTMLResponse` — `src/api/static/index.html`의 `/*__BOOT__*/null` 자리에 초기 데이터 JSON을 넣은 HTML
- 처리:
  1. `_law_versions()`로 법령 버전 목록을 만듭니다.
  2. `get_graph()`로 그래프를 얻어 `pending_requests(graph, graph.checkpointer)`(승인 대기 건)와 `closed_duplicate_ids(graph)`('중복 요청'으로 닫힌 건 번호)를 읽습니다.
  3. `boot = {**build_ui_data(), "laws", "pending", "closedDuplicates", "lawsAsOf"}`를 만듭니다. `lawsAsOf`는 법령 `collected` 값 중 최댓값(없으면 `""`)입니다.
  4. `json.dumps(ensure_ascii=False)` 후 `</`를 `<\/`로 바꿔 HTML에 삽입합니다.
- 예외·오류 처리: 2단계에서 예외가 나면 로그(`"pending requests load failed"`)만 남기고 `pending`, `duplicates`를 빈 목록으로 두어 화면은 열리게 합니다. 그 밖의 단계(`build_ui_data`, 파일 읽기)의 예외 처리는 없습니다.
- 비고: 화면의 모든 버튼은 `POST /query`만 호출합니다(API Spec 그대로). 변경 사건·제품 목록과 법령 기준일은 별도 API 없이 이 HTML에 넣어 보냅니다.

### 4.6 `_law_versions() -> list[dict]`
- `LAW_DIR`의 `*.md` 파일을 이름순으로 읽어 `_retriever._parse_front`로 머리말을 파싱하고 `law`, `status`, `effective`, `collected` 키(없으면 `""`)만 담은 목록을 돌려줍니다.

## 5. 데이터·설정
- 읽는 파일: `src/api/static/index.html`, `data/laws/*.md`, `checkpoints.sqlite`(그래프 체크포인터 경유), 그 밖에 `build_ui_data()`가 읽는 파일(그 모듈 사양 참조)
- 쓰는 파일: `checkpoints.sqlite` (그래프 실행 시 체크포인터 경유)
- 환경 변수: 이 파일에서 직접 읽지 않음(실행 포트 `PORT`는 `run.sh`에서 사용)
- 주요 상수: `_UI`, 오류 응답 문구

## 6. 처리 흐름
```
클라이언트(화면·PowerShell·curl)
  ├ GET /health → {"status":"ok"}
  ├ GET /       → 법령 버전 + build_ui_data + 승인 대기·중복 닫힘 목록 → index.html에 삽입
  └ POST /query → QueryRequest 검증(실패 422)
                 → run_query(question, get_graph())
                 → QueryResponse (200) / 예외 시 같은 모양의 오류 응답 (500)
```
실행: `../.venv/Scripts/python -m uvicorn src.api.app:app --port 8000` (docstring), `run.sh`는 `--host 0.0.0.0 --port "${PORT:-8000}"`.

## 7. 제약·주의 사항
- `get_graph()`는 `lru_cache`로 프로세스당 1개 그래프·SQLite 연결을 공유합니다. 테스트에서는 `monkeypatch.setattr(api, "get_graph", ...)`로 가짜 그래프를 넣습니다.
- `query`는 동기 함수(`def`)입니다.
- 응답 필드 이름·구조는 `API Spec.md`를 따라야 하며 바꾸지 않습니다(`src/api/schemas.py`).
- 화면 경로 주석을 실제 경로 `src/api/static/index.html`로 고쳤습니다 (2026-11-12 정리 완료). 쓰지 않던 `msds_tools` import(`_tools`)도 주석 처리했습니다.
- `_tools`(`src.tools.msds_tools`) import는 현재 코드에서 쓰이지 않습니다.

## 8. 관련 테스트
- `tests/test_api.py`: `test_health`, `test_response_declares_utf8`, `test_query_and_approval_flow`, `test_guardrail_via_api`, `test_validation_errors`, `test_internal_error_keeps_spec_shape`
- `GET /`(`ui`)를 직접 검사하는 테스트는 없음

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `3c00663` | 2일차 구현 (당시 `src/api.py`): `POST /query`, `GET /health` |
| `8f9960d` | API 응답 `charset=utf-8` 명시 — `UTF8JSONResponse` 추가, 기본 `JSONResponse` 앱 생성 코드는 주석으로 남김 |
| `9205279` | 실제 화면(대시보드·MSDS 조회·변경 전후 비교) 추가 — `GET /` 추가. 초기 데이터를 변경 사건·제품 목록만에서 `build_ui_data()` 기반으로 교체 |
| `cf9e456` | 승인 대기 건 불러오기 — 체크포인트의 승인 대기 건(`pending`)을 화면에 전달 |
| `97ab1fd` | `src/api/app.py`로 이동, import 경로를 도메인 폴더 구조로 변경(`src.agent` → `src.workflows.graph`, `src.schemas` → `src.api.schemas`, `src.retriever` → `src.regulation.retriever`, `src.tools` → `src.tools.msds_tools`, `src.config` → `src.shared.config`, `src.revision_preview` → `src.revision.preview`). 실행 경로 `src.api:app` → `src.api.app:app` |
| `25682ce` | 같은 변경의 승인 요청 중복 방지 — '중복 요청'으로 닫힌 건 번호(`closedDuplicates`)도 화면에 전달 |

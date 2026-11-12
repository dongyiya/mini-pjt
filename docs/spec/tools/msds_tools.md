# `src/tools/msds_tools.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/tools/msds_tools.py` |
| 도메인 | `tools` — 에이전트가 호출하는 도메인 도구와 MCP 서버·클라이언트 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 348줄 |

## 1. 개요
MSDS 개정 지원 에이전트가 쓰는 도메인 도구 11개를 정의합니다. 가상 제품 MSDS(`data/msds/products.json`), 규제·사내 변경 사건(`data/regulation_updates.json`), 단일물질 스냅샷(`data/substances/<CAS>.json`)을 조회하고, 재제출 대상 판정·영향 판정·법령 검색·혼합물 검토 목록을 만듭니다. 법령 검색(`search_law`)을 빼면 표준 라이브러리만 쓰므로 LLM·API 키 없이 실행할 수 있습니다(파일 상단 주석). `langchain_core`가 설치돼 있으면 같은 함수를 LangChain 도구 목록 `TOOLS`로도 노출합니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.regulation.retriever` (`search_law` 안에서 지연 import)
- 이 모듈을 사용하는 곳:
  - `src/agents/brains.py` (에이전트별 도구 묶음 `make_tools`에서 도구 10개 + `search_law` 래핑)
  - `src/tools/mcp_server.py` (MSDS DB 도구 6개를 MCP로 노출)
  - `src/workflows/evidence.py` (`get_msds`)
  - `src/workflows/pipeline_v1.py` (`assess_update`, `get_msds`, `find_products_by_cas`, `mask_phone`, `mask_email`)
  - `src/revision/preview.py` (`_products`, `get_regulation_update`, `list_regulation_updates`, `get_substance`, `list_products`, `get_msds`, `assess_update`)
  - `src/revision/msds_apply.py` (`_products.cache_clear()`)
  - (`src/api/app.py`는 예전에 `_tools`로 import 했으나 쓰는 곳이 없어 주석 처리 (2026-11-12 정리 완료))
  - `tests/test_tools.py`, `tests/test_mcp.py`, `tests/test_agent.py`
- 외부 라이브러리·서비스: 표준 라이브러리(`json`, `re`, `functools.lru_cache`, `pathlib`), `langchain_core.tools.tool`(선택, 없으면 `TOOLS`는 빈 목록). `search_law`는 `retriever`를 통해 `kiwipiepy`, `rank_bm25`, `faiss`, Bedrock 임베딩·채팅 모델을 간접 사용합니다.

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `DATA_DIR` | 상수 | `mini-pjt/data` 경로 (파일 위치 기준 `parents[2] / "data"`) |
| `RESUBMISSION_ITEMS` | 상수 | 시행규칙 제159조제1항 각 호(제품명·구성성분·유해성)의 항목 번호와 문구 |
| `RESUBMISSION_DOC_IDS` | 상수 | 재제출 판정 근거 doc_id: `law:산안법:110`, `law:산안법시행규칙:159` |
| `_PRODUCTS_CACHE` / `_products()` | 상수 / 함수 | 제품 목록 로딩. 파일 수정 시각(`st_mtime_ns`) 기준 캐시 |
| `_products.cache_clear` | 함수 속성 | 캐시 비우기 (기존 `lru_cache` 호출부 호환) |
| `_updates()` | 함수 | 변경 사건 목록 로딩 (`lru_cache(maxsize=1)`) |
| `_find_product()` | 함수 | 제품 ID로 제품 찾기 (공백 제거·대문자 변환) |
| `mask_phone()` | 함수 | 휴대전화 번호 가운데 자리 마스킹 |
| `mask_email()` | 함수 | 이메일 아이디 첫 글자만 남기고 마스킹 |
| `_public_view()` | 함수 | 영업비밀 실명·실CAS·실함유량 제거, 담당자 연락처 마스킹한 사본 |
| `get_msds()` | 함수(도구 1) | 제품 MSDS 조회 (마스킹 적용) |
| `find_products_by_cas()` | 함수(도구 2) | CAS로 성분 포함 제품 검색 |
| `find_products_by_term()` | 함수(도구 3) | MSDS 항목(기본 15번)에 용어가 있는 제품 검색 |
| `get_regulation_update()` | 함수(도구 4) | 변경 사건 1건 조회 |
| `list_regulation_updates()` | 함수(도구 5) | 변경 사건 목록 |
| `check_resubmission()` | 함수(도구 6) | 바뀐 내용이 재제출 대상인지 규칙 판정 |
| `assess_update()` | 함수(도구 7) | 변경 사건의 영향 제품·항목 규칙 판정 |
| `list_products()` | 함수(도구 8) | 제품 목록 |
| `search_law()` | 함수(도구 9) | 법령 조문 하이브리드 검색 |
| `DOMESTIC_REG_KEYS` | 상수 | 국내 규제 키 3개(산안법·화관법·화평법) |
| `_substance()` | 함수 | 단일물질 스냅샷 파일 읽기 |
| `get_substance()` | 함수(도구 10) | 단일물질 정보 조회 |
| `_hazard_class()` | 함수 | 유해성 분류 문구를 비교용 이름으로 정규화 |
| `classify_mixture()` | 함수(도구 11) | 성분별 GHS 분류를 모아 제품 2번 항목과 비교한 검토 목록 |
| `ALL_FUNCTIONS` | 상수 | 도구 함수 11개 튜플 |
| `TOOLS` | 상수 | `ALL_FUNCTIONS`를 `langchain_core` 도구로 감싼 목록 (미설치 시 `[]`) |

## 4. 상세 사양

### 4.1 `get_msds(product_id: str, sections: list[str] | None = None) -> dict`
- 입력: `product_id` 제품 ID(예: `P-001`, 대소문자·앞뒤 공백 무관), `sections` 남길 항목 번호 목록(예: `["3", "15"]`), 생략 시 전체
- 출력: 마스킹된 제품 dict + `doc_id`(`msds:<제품ID>`). `sections`를 주면 `id`, `name`, `revision`, `section<번호>` 키만 남김
- 처리: 1. `_find_product`로 제품 조회 2. `_public_view`로 마스킹 사본 생성 3. `sections`가 있으면 키 필터링 4. `doc_id` 추가
- 예외·오류 처리: 제품이 없으면 `{"error": "제품 <ID>을(를) 찾을 수 없습니다."}`
- 마스킹 규칙(`_public_view`): `section3` 각 성분에서 `real_name`, `real_cas`, `real_content` 삭제 / `section1.contact_phone`은 `mask_phone`, `contact_email`은 `mask_email`, `contact_name`은 첫 글자 + `**`

### 4.2 `find_products_by_cas(cas: str) -> list[dict]`
- 입력: CAS 번호 (앞뒤 공백 제거)
- 출력: `[{product_id, product_name, component, content}]`
- 처리: 모든 제품의 `section3` 성분 중 공개 `cas`가 정확히 일치하는 항목을 모읍니다.
- 예외·오류 처리: 없으면 빈 목록. 영업비밀 성분은 실CAS(`real_cas`)를 검색하지 않으므로 검색되지 않습니다(docstring).

### 4.3 `find_products_by_term(term: str, section: str = "15") -> list[dict]`
- 입력: 찾을 용어, MSDS 항목 번호(기본 `"15"` 법적 규제현황)
- 출력: `[{product_id, product_name, matched}]` — `matched`는 `"<법령>: <항목>"` 형식의 일치 줄 목록
- 처리: 1. 제품의 `section<번호>`를 JSON 문자열로 바꿔 `term` 포함 여부 확인 2. 블록이 dict이면 법령별 항목 중 `term`을 포함한 줄을 `matched`에 담음
- 예외·오류 처리: 없으면 빈 목록. 블록이 dict가 아니면 `matched`는 빈 목록으로 결과에 포함됩니다.

### 4.4 `get_regulation_update(update_id: str) -> dict`
- 입력: 변경 사건 ID(예: `U-01`, 대문자 변환)
- 출력: `regulation_updates.json`의 사건 dict 그대로 (키: `id`, `type`, `real`, `title`, `law`, `promulgated`, `effective`, `summary`, `match`, `related_docs`)
- 예외·오류 처리: 없으면 `{"error": "변경 사건 <ID>을(를) 찾을 수 없습니다."}`

### 4.5 `list_regulation_updates() -> list[dict]`
- 입력: 없음
- 출력: `[{id, title, type}]`

### 4.6 `check_resubmission(change: str) -> dict`
- 입력: 바뀐 내용 설명 문자열 (예: `"제품명"`, `"구성성분 함유량"`, `"건강 및 환경에 대한 유해성"`, `"법적 규제현황"`)
- 출력: `{change, resubmission_required, basis, doc_ids}` + 재제출 대상이면 `deadline`
- 처리(키워드 규칙, 위에서부터 먼저 걸리는 것):
  1. `"제품명"` 포함 → 제159조제1항제1호
  2. `"구성성분"`, `"함유량"`, `"명칭"` 중 하나 포함 → 제159조제1항제2호
  3. `"유해성"`, `"위험성"` 중 하나 포함 → 제159조제1항제3호
  4. 그 밖 → `resubmission_required: False`, 근거 "시행규칙 제159조제1항 각 호(...)에 해당하지 않습니다."
- 대상일 때 `basis`는 `"<항목 번호>: <조문 문구>"`, `deadline`은 "변경사항을 반영한 물질안전보건자료를 지체 없이 공단에 제출(시행규칙 제159조제2항)" 고정 문구
- `doc_ids`는 항상 `RESUBMISSION_DOC_IDS`
- 예외·오류 처리: 해당 없음 (항상 dict 반환)

### 4.7 `assess_update(update_id: str) -> dict`
- 입력: 변경 사건 ID
- 출력: `{update: {id, title, real}, affected: [...], doc_ids: <사건의 related_docs>}`
- 처리: docstring상 "LLM 판정의 기준선(baseline)이자 평가셋 정답을 만드는 근거"입니다.
  1. `get_regulation_update`로 사건 조회
  2. 사건 `match`에 `term`이 있으면(규제 변경형): `find_products_by_term(term, section)` 결과마다 `{product_id, product_name, sections: [section], current: matched, resubmission: check_resubmission("법적 규제현황")}` 추가
  3. 없으면(사내 변경형): `match.product_id` 제품 하나에 대해 `match.change`를 항목 번호로 매핑(`제품명`→1, `구성성분 함유량`→3, `건강 및 환경에 대한 유해성`→2, 그 외 없음)하고 `check_resubmission(match.change)` 결과를 붙임
- 예외·오류 처리: 사건이 없으면 `get_regulation_update`의 error dict를 그대로 반환. 3번에서 제품을 찾지 못하는 경우의 처리는 없습니다(`None` 속성 접근 오류 발생 가능 — 확인 필요).

### 4.8 `list_products() -> list[dict]`
- 출력: `[{id, name, revision}]`, `revision`은 `"<no>판 (<date>)"` 형식
- 용도: 없는 제품을 물을 때 이 목록으로 안내(docstring)

### 4.9 `search_law(query: str, as_of: str | None = None, k: int = 3) -> dict`
- 입력: 검색 질의, 기준일(`YYYY-MM-DD`, 생략 시 retriever가 `today()` 사용), 조문 수 `k`
- 출력: `{as_of, method, applicable: [...], upcoming: [...], notes}` — 각 조문은 `{doc_id, title, text, effective_from}`
- 처리: 1. `as_of`를 `date`로 변환 2. 환경 변수 `MSDS_RERANK`가 `"0"`이 아니면 리랭크 사용(기본 사용) 3. `retriever.search(query, k, as_of, rerank)` 호출 4. 결과를 dict로 변환
- 규칙: 판정 근거는 `applicable`(기준일 시행 중인 판)만 쓰고 `upcoming`(기준일 이후 시행 판)은 따로 표시(docstring)
- 예외·오류 처리: `as_of` 형식이 틀리면 `date.fromisoformat`의 `ValueError`가 그대로 올라갑니다. 벡터 검색·리랭크 실패는 retriever 안에서 처리되어 `method`에 기록됩니다.

### 4.10 `get_substance(cas: str) -> dict`
- 입력: CAS 번호
- 출력: `{cas, name, doc_id, ghs, pictograms, signal_word, regulations, source}`
  - `ghs`·`pictograms`·`signal_word`는 스냅샷 `section2`에서, `regulations`는 `section15` 중 `DOMESTIC_REG_KEYS` 3개 키만
  - `source`는 `"<source> (공단 갱신일 <kosha_last_date>, 수집일 <collected>)"`
- 처리: `data/substances/<CAS>.json`을 읽어 필요한 필드만 골라 반환
- 예외·오류 처리: 파일이 없으면 `{"error": "CAS <cas> 물질 정보가 없습니다. 등록 제품의 공개 성분만 조회할 수 있습니다."}`

### 4.11 `classify_mixture(product_id: str) -> dict`
- 입력: 제품 ID
- 출력: `{product_id, product_name, product_section2, component_hazards, not_in_section2, skipped, note, doc_ids}`
  - `component_hazards`: `[{hazard_class, components: [{component, cas, content, classification}], in_product_section2}]`
  - `not_in_section2`: 제품 2번 항목에 없는 유해성 항목 이름 목록
  - `doc_ids`: `msds:<제품ID>` + 스냅샷이 있는 공개 성분의 `substance:<CAS>`
- 처리:
  1. 제품 `section2.ghs`를 `_hazard_class`로 정규화해 현재 분류 집합 생성
  2. 성분마다: 영업비밀(`trade_secret`)이면 공단 자료를 조회하지 않고 `skipped`에 기록, 스냅샷이 없으면 `skipped`에 기록
  3. 스냅샷 GHS 분류 중 `"자료없음"`을 빼고 정규화 이름별로 성분을 묶음
  4. 묶음마다 제품 2번 항목에 있는지 표시
- 규칙: 혼합물 최종 분류(가산식·한계농도)는 고시 기준 원문을 수집하지 않아 계산하지 않으며 `note`에 "원문 확인 필요"로 안내합니다. 영업비밀 성분의 실제 명칭은 드러내지 않습니다.
- 예외·오류 처리: 제품이 없으면 `{"error": "제품 <ID>을(를) 찾을 수 없습니다."}`
- `_hazard_class` 정규화: `:` 또는 `구분` 앞부분만 취하고, `/ 피부`를 `/`로 바꾼 뒤 공백·`/`·`·`를 제거 (예: `'인화성 액체 : 구분2'` → `'인화성액체'`)

### 4.12 `mask_phone(text: str) -> str` / `mask_email(text: str) -> str`
- `mask_phone`: `01[016789]` 시작 번호를 `010-****-1234` 형태로 바꿈 (하이픈 유무 무관)
- `mask_email`: `@` 앞 아이디를 첫 글자 + `***`로 바꿈
- 주석상 "가드레일 6번의 일부"입니다.

### 4.13 `ALL_FUNCTIONS`, `TOOLS`
- `ALL_FUNCTIONS`: `get_msds, list_products, find_products_by_cas, find_products_by_term, get_regulation_update, list_regulation_updates, check_resubmission, assess_update, search_law, get_substance, classify_mixture`
- `TOOLS`: `langchain_core.tools.tool`로 감싼 목록. `ImportError`면 빈 목록

### 4.14 내부 로딩 함수
- `_products()`: `data/msds/products.json`의 `products`. 파일 수정 시각이 바뀌면 다시 읽음
- `_updates()`: `data/regulation_updates.json`의 `updates`. 프로세스 동안 한 번만 읽음
- `_substance(cas)`: 파일이 없으면 `None`

## 5. 데이터·설정
- 읽는 파일: `data/msds/products.json`, `data/regulation_updates.json`, `data/substances/<CAS>.json`
- 쓰는 파일: 없음
- 환경 변수: `MSDS_RERANK` (`"0"`이면 `search_law`에서 LLM 리랭크 끔, 기본 `"1"`)
- 주요 상수: `RESUBMISSION_ITEMS`, `RESUBMISSION_DOC_IDS`, `DOMESTIC_REG_KEYS`, `ALL_FUNCTIONS`

## 6. 처리 흐름
대표 흐름(`assess_update`, 모듈 단독 실행 시 `assess_update("U-01")` 출력):
1. 변경 사건 조회 (`get_regulation_update`)
2. 사건 유형 분기
   - 용어 일치형(`match.term`) → `find_products_by_term`으로 영향 제품 탐색 → 각 제품에 `check_resubmission("법적 규제현황")`
   - 제품 지정형(`match.product_id`) → 바뀐 항목 번호 매핑 → `check_resubmission(match.change)`
3. `{update, affected, doc_ids}` 반환

에이전트 사용 흐름: `src/agents/brains.py`가 도구 10개를 JSON 문자열 반환 래퍼로 감싸고, `search_law`는 질문 기준일(`as_of`)을 고정한 별도 도구로 만듭니다. `MSDS_USE_MCP`가 `"0"`이 아니면 MSDS DB 도구 6개는 MCP 버전으로 바꿉니다.

## 7. 제약·주의 사항
- 제품 캐시는 파일 수정 시각 기준이라, 승인 반영(`src/revision/msds_apply.py`)으로 `products.json`이 바뀌면 서버·MCP 프로세스가 다시 읽습니다. 변경 사건 캐시(`_updates`)는 `lru_cache`라 프로세스 재시작 전까지 갱신되지 않습니다.
- `DATA_DIR`은 CLAUDE.md 경로 계산 규칙에 따라 `src/shared/config.py`의 `DATA_DIR`을 가져다 씁니다(같은 경로) (2026-11-12 정리 완료).
- `check_resubmission`은 키워드 포함 여부만 보는 규칙 판정입니다. 순서상 `"제품명"`이 먼저 걸립니다.
- 영업비밀 성분은 조회 결과에서 실명·실CAS·실함유량을 지우고(`_public_view`), CAS 검색과 공단 자료 조회(`classify_mixture`) 대상에서 빠집니다.
- 혼합물 최종 분류는 계산하지 않습니다 ("확인 필요").
- `search_law`만 외부 서비스(임베딩·LLM)를 간접 사용할 수 있습니다.

## 8. 관련 테스트
- `tests/test_tools.py`: `test_get_msds_masks_secret_and_contact`, `test_get_msds_sections_and_unknown`, `test_list_products`, `test_find_products_by_cas_toluene`, `test_find_products_by_term_u01`, `test_regulation_updates`, `test_check_resubmission_rules`, `test_assess_update_each_event`, `test_search_law_returns_applicable_and_upcoming`, `test_get_substance_toluene`, `test_hazard_class_normalization`, `test_classify_mixture_review_list`, `test_tools_exposed_to_langchain`
- `tests/test_mcp.py`: `test_mcp_results_match_local_tools`, `test_mcp_keeps_masking` (MCP 결과와 로컬 도구 결과 비교)
- `tests/test_agent.py`: `test_make_tools_binds_as_of` (도구 묶음에서 `search_law` 기준일 고정)

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `0574139` | 1일차: 데이터·도구 뼈대 (`src/tools.py`) |
| `3c00663` | 2일차: 에이전트 그래프·RAG·MCP 등 구현. 노출 도구 7개 → 11개(`list_products`, `search_law`, `get_substance`, `classify_mixture` 추가, `ALL_FUNCTIONS` 도입) |
| `cf9e456` | 제품 데이터 캐시를 `lru_cache`에서 파일 수정 시각 기준 캐시로 교체 (서버·MCP 프로세스가 승인 반영된 MSDS를 다시 읽도록), `_products.cache_clear` 호환 함수 추가 |
| `97ab1fd` | 도메인별 폴더 리팩토링: `src/tools.py` → `src/tools/msds_tools.py`, `DATA_DIR`을 `parents[2]` 기준으로, `from src import retriever` → `from src.regulation import retriever` |

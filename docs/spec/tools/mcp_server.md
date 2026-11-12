# `src/tools/mcp_server.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/tools/mcp_server.py` |
| 도메인 | `tools` — 에이전트가 호출하는 도메인 도구와 MCP 서버·클라이언트 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 67줄 |

## 1. 개요
사내 MSDS DB(제품·성분·물질 정보) 조회 도구 6개를 MCP 도구로 노출하는 FastMCP 서버입니다(빌드 패턴 5). stdio 전송으로 실행되며, 에이전트는 `src/tools/mcp_client.py` 브리지로 이 서버에 붙어 도구를 호출합니다. 실제 로직은 `msds_tools`에 있고, 이 서버는 결과를 JSON 문자열로 바꿔 돌려주기만 합니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.tools.msds_tools` (별칭 `tools`)
- 이 모듈을 사용하는 곳:
  - `src/tools/mcp_client.py` (하위 프로세스로 `python -X utf8 -m src.tools.mcp_server` 실행)
  - `tests/test_mcp.py` (`MCP_TOOL_NAMES`)
- 외부 라이브러리·서비스: `mcp.server.fastmcp.FastMCP`, 표준 라이브러리 `json`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `mcp` | 상수(객체) | `FastMCP("msds-db", log_level="WARNING")` 서버 인스턴스 |
| `_j()` | 함수 | 결과를 `ensure_ascii=False` JSON 문자열로 변환 |
| `get_msds()` | 함수(MCP 도구) | `tools.get_msds` 래핑 |
| `list_products()` | 함수(MCP 도구) | `tools.list_products` 래핑 |
| `find_products_by_cas()` | 함수(MCP 도구) | `tools.find_products_by_cas` 래핑 |
| `find_products_by_term()` | 함수(MCP 도구) | `tools.find_products_by_term` 래핑 |
| `get_substance()` | 함수(MCP 도구) | `tools.get_substance` 래핑 |
| `classify_mixture()` | 함수(MCP 도구) | `tools.classify_mixture` 래핑 |
| `MCP_TOOL_NAMES` | 상수 | 노출 도구 이름 6개 튜플 |

## 4. 상세 사양
모든 도구는 `@mcp.tool()`로 등록되며, 같은 이름의 `msds_tools` 함수를 호출한 결과를 `_j()`로 JSON 문자열로 바꿔 반환합니다. 입력·출력 내용과 오류 dict(`{"error": ...}`)는 `docs/spec/tools/msds_tools.md`와 같습니다.

### 4.1 `get_msds(product_id: str, sections: list[str] | None = None) -> str`
- 입력: 제품 ID, 항목 번호 목록(예: `["3", "15"]`)
- 출력: 마스킹된 MSDS JSON 문자열

### 4.2 `list_products() -> str`
- 출력: 제품 목록(id, 제품명, MSDS 개정판) JSON 문자열

### 4.3 `find_products_by_cas(cas: str) -> str`
- 출력: CAS 일치 제품 목록 JSON 문자열 (영업비밀 성분은 검색되지 않음)

### 4.4 `find_products_by_term(term: str, section: str = "15") -> str`
- 출력: 해당 항목에 용어가 적힌 제품 목록 JSON 문자열

### 4.5 `get_substance(cas: str) -> str`
- 출력: 단일물질 정보(GHS 분류, 그림문자, 신호어, 국내 규제현황) JSON 문자열

### 4.6 `classify_mixture(product_id: str) -> str`
- 출력: 성분별 GHS 분류 검토 목록 JSON 문자열 (최종 혼합물 분류는 "확인 필요")

### 4.7 `MCP_TOOL_NAMES`
- 값: `("get_msds", "list_products", "find_products_by_cas", "find_products_by_term", "get_substance", "classify_mixture")`
- 테스트에서 서버가 노출하는 도구 이름과 비교하는 데 씁니다.

### 4.8 실행 진입점
- `python -m src.tools.mcp_server` → `mcp.run()` (stdio 전송)
- 예외·오류 처리: 이 파일에 별도 처리는 없습니다. 도구 함수의 오류 dict는 그대로 JSON으로 전달됩니다.

## 5. 데이터·설정
- 읽는 파일: 직접 읽지 않음 (`msds_tools`가 `data/msds/products.json`, `data/substances/*.json` 읽음)
- 쓰는 파일: 없음
- 환경 변수: 없음
- 주요 상수: 서버 이름 `"msds-db"`, 로그 수준 `"WARNING"`, `MCP_TOOL_NAMES`

## 6. 처리 흐름
1. `mcp_client`가 `python -X utf8 -m src.tools.mcp_server`를 프로젝트 루트에서 하위 프로세스로 실행
2. `mcp.run()`이 stdio로 MCP 요청 대기
3. 도구 호출 → `msds_tools` 함수 실행(마스킹 포함) → `_j()`로 JSON 문자열 반환

## 7. 제약·주의 사항
- 영업비밀·연락처 마스킹은 `msds_tools` 단계에서 이미 적용되므로 MCP 경계 밖으로 원본이 나가지 않습니다(docstring).
- 변경 사건·재제출 판정·영향 판정·법령 검색 도구(`get_regulation_update`, `list_regulation_updates`, `check_resubmission`, `assess_update`, `search_law`)는 노출하지 않습니다. 에이전트는 이들을 로컬 도구로 씁니다(`src/agents/brains.py`).
- 모듈 docstring의 옛 경로를 `src/tools/msds_tools.py`, `src/tools/mcp_client.py`로 고쳤습니다 (2026-11-12 정리 완료).
- 서버 프로세스는 별도 프로세스이므로 제품 데이터 캐시도 따로 가집니다(`msds_tools`의 파일 수정 시각 기준 캐시로 갱신됨).

## 8. 관련 테스트
- `tests/test_mcp.py` (실제 서버 프로세스를 stdio로 띄움, 네트워크 없음): `test_server_exposes_expected_tools`, `test_mcp_results_match_local_tools`, `test_mcp_keeps_masking`, `test_make_tools_uses_mcp_when_enabled`

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `3c00663` | 2일차: MCP 서버 추가 (`src/mcp_server.py`) |
| `97ab1fd` | 도메인별 폴더 리팩토링: `src/mcp_server.py` → `src/tools/mcp_server.py`, `from src import tools` → `from src.tools import msds_tools as tools`, 실행 명령 `-m src.mcp_server` → `-m src.tools.mcp_server` |

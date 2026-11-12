# `src/workflows/evidence.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/workflows/evidence.py` |
| 도메인 | `workflows` — LangGraph 그래프와 `/query` 처리 흐름 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 154줄 |

## 1. 개요
서브 에이전트의 메시지(도구 호출·결과)에서 API 응답의 `trace` 단계와 `contexts`(근거 문서)를 만듭니다.
도구별로 어떤 근거(doc_id·문장)를 붙일지 정하고, 근거 문장은 `evidence_text.py`에 맡기며, 근거에 마스킹과 doc_id 중복 제거를 적용합니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.guardrails.guard` (`mask_output`), `src.regulation.retriever` (`get_applicable`), `src.shared.trace` (`dumps`, `message_text`, `step`), `src.tools.msds_tools` (`get_msds`), 지연 import: `src.workflows.evidence_text`
- 이 모듈을 사용하는 곳: `src/workflows/graph.py` (`collect` 사용, 나머지는 재노출)
- 외부 라이브러리·서비스: `langchain_core.messages` (`AIMessage`, `BaseMessage`, `ToolMessage`), 표준 `json`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `collect` | 함수 | 메시지 → (trace, contexts) |
| `contexts_from_tool` | 함수 | 도구 호출 하나의 결과 → 근거 목록(문장형, `rule:` 근거 포함) |
| `_law_contexts` | 함수(내부) | 법령 doc_id → 기준일 시행 조문·시행 예정 조문 근거 |
| `_msds_context` | 함수(내부) | 제품 MSDS 근거(문장형) |
| `_contexts_from_tool_v1` | 함수(내부) | 1·2차 평가 때 JSON 근거 버전. 비교용 보관, 호출하지 않음 |

## 4. 상세 사양
### 4.1 `collect(messages: list[BaseMessage], as_of: date) -> tuple[list[dict], list[dict]]`
- 입력: 에이전트 메시지 목록, 기준일.
- 출력: (trace 단계 목록, contexts 목록).
- 처리:
  1. `AIMessage.tool_calls`로 호출 id → 호출 정보 표를 만듭니다.
  2. 각 `ToolMessage`마다 trace 에 `step("tool:<이름>", args, 원문 결과)`를 추가합니다(호출 정보가 없으면 이름은 `m.name` 또는 `"?"`).
  3. 결과를 JSON으로 읽어 `contexts_from_tool`로 근거를 만들고, 처음 나온 doc_id만 남기며 `text`에 `guardrails.mask_output`을 적용합니다.
- 예외·오류 처리: JSON 파싱 실패 시 trace 는 남기고 근거는 건너뜁니다.

### 4.2 `contexts_from_tool(name: str, args: dict, result: Any, as_of: date) -> list[dict]`
- 입력: 도구 이름, 호출 인자, 파싱된 결과, 기준일. 출력: `[{doc_id, text}]`.
- 처리(도구별):
  | 도구 | 근거 |
  |---|---|
  | `search_law` | `applicable` 조문 그대로 + `upcoming` 조문(`[시행 예정 <날짜>] ` 접두) |
  | `get_msds` | `msds:<P>` — `msds_text` |
  | `get_regulation_update` | `update:<id>` — `update_text` + `related_docs` 법령 근거 |
  | `list_regulation_updates` | `catalog:updates` — `updates_catalog_text` |
  | `list_products` | `catalog:products` — `products_catalog_text` |
  | `check_resubmission` | `rule:check_resubmission:<change>` — `resubmission_text` + `doc_ids` 법령 근거 |
  | `assess_update` | `rule:assess_update:<uid>` — `assessment_text` + `doc_ids` 법령 근거 + 영향 제품별 MSDS 근거(해당 항목) + 제품별 재제출 근거 조문 |
  | `find_products_by_cas` | `rule:find_products_by_cas:<cas>` — `products_by_cas_text` + 각 제품 MSDS 3번 항목 근거 |
  | `find_products_by_term` | 각 제품 MSDS의 `args.section`(기본 `"15"`) 항목 근거 |
  | `get_substance` | 결과의 `doc_id` — `substance_text` |
  | `classify_mixture` | `msds:<P>` — `mixture_text` |
  | 그 밖 | 없음 |
- 예외·오류 처리: 결과가 dict/list 가 아니거나 dict 에 `error` 키가 있으면 빈 목록.

### 4.3 내부 함수
- `_law_contexts(doc_ids, as_of)`: `law:`로 시작하는 doc_id만 `retriever.get_applicable(d, as_of)`로 조회해 현재 시행 조문과 시행 예정 조문(`c.label(as_of)` 접두)을 근거로 만듭니다.
- `_msds_context(pid, sections=None)`: `tools.get_msds(pid, sections)` 결과를 `evidence_text.msds_text`로 바꿔 `msds:<pid>` 근거로 만듭니다.
- `_contexts_from_tool_v1(...)`: 같은 분기를 JSON 문자열(`dumps`)로 만들던 기존 버전. 주석상 "비교용으로 남김, 호출하지 않음".

## 5. 데이터·설정
- 읽는 파일: 직접 읽지 않음(`retriever`, `msds_tools`가 데이터·인덱스를 읽음).
- 쓰는 파일 / 환경 변수: 없음
- 주요 상수: 근거 doc_id 접두 `law:`, `msds:`, `update:`, `catalog:`, `rule:`

## 6. 처리 흐름
1. `graph.py` 서브 에이전트 노드 → `collect(msgs, as_of)`
2. `ToolMessage`마다 trace 기록 → JSON 파싱 → `contexts_from_tool` → `evidence_text`의 문장 함수
3. doc_id 중복 제거 + 마스킹 → 노드 상태의 `contexts`

## 7. 제약·주의 사항
- 마스킹은 `collect`에서만 적용됩니다. `contexts_from_tool`을 직접 부르면 마스킹되지 않습니다.
- 중복 제거는 한 번의 `collect` 호출 안에서만 합니다(그래프 상태의 `contexts`는 `operator.add`로 누적).
- `_law_contexts`는 `law:`가 아닌 doc_id(예: `msds:`)를 무시합니다.

## 8. 관련 테스트
- `tests/test_agent.py`: `test_regulation_agent_collects_law_contexts_and_trace`, `test_impact_agent_contexts_are_masked_and_deduped`, `test_revision_pending_then_approve`(contexts 에 `law:산안법시행규칙:159`, `msds:P-002` 포함 확인)

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `97ab1fd` | `src/agent.py`의 `_law_contexts`·`_msds_context`·`contexts_from_tool`·`_contexts_from_tool_v1`·`collect`를 옮겨 새 파일로 분리 (이전 이력은 `src/agent.py`, 특히 `c8f8ff5`에서 문장형 근거 도입) |

주석으로 남은 변경:
- `_msds_context`: 제품 MSDS 근거를 JSON 문자열로 만들던 방식 → 문장형(`msds_text`)으로 교체(2차 평가 faithfulness 개선).
- `contexts_from_tool`: JSON 근거 → 문장형 근거, 규칙 판정 결과를 `rule:` 근거로 추가. 기존 분기는 `_contexts_from_tool_v1`로 보관.
- import 경로 `src.context_text` → `src.workflows.evidence_text`.

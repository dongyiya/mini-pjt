# `src/agents/judgment.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/agents/judgment.py` |
| 도메인 | `agents` — Supervisor·서브 에이전트(regulation·impact·revision) |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 81줄 |

## 1. 개요
revision 에이전트가 만든 개정 판정(`RevisionJudgment`)을 후처리합니다.
`sanitize_judgment`는 LLM 판정의 영향 제품·항목을 `assess_update` 도구 결과와 대조해 근거 없는 것을 빼고(1차 평가 16번 환각 대응), `format_judgment`는 판정을 사용자에게 보여 줄 답변 문구로 만듭니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.agents.schemas` (`RevisionJudgment`), `src.shared.trace` (`message_text`)
- 이 모듈을 사용하는 곳: `src/workflows/graph.py` (재노출 → `tests/test_agent.py`가 `A.sanitize_judgment`, `A.format_judgment`로 사용)
- 외부 라이브러리·서비스: `langchain_core.messages` (`AIMessage`, `BaseMessage`, `ToolMessage`), 표준 `json`, `re`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `sanitize_judgment` | 함수 | `assess_update` 결과로 판정 검증, 근거 없는 제품·항목 제거 |
| `format_judgment` | 함수 | 판정 → 답변 문구 |

## 4. 상세 사양
### 4.1 `sanitize_judgment(j: RevisionJudgment, messages: list[BaseMessage]) -> tuple[RevisionJudgment, list[str]]`
- 입력: LLM 판정, 에이전트 메시지 목록.
- 출력: (검증된 판정, 제거 내역 문장 목록).
- 처리:
  1. `AIMessage.tool_calls`에서 호출 id → 호출 정보 표를 만듭니다.
  2. 이름이 `assess_update`인 호출의 `ToolMessage`를 JSON으로 읽어, `affected`의 `product_id`별 허용 `sections` 집합을 모읍니다.
  3. `assess_update` 결과가 하나도 없으면 판정을 그대로 반환(`(j, [])`).
  4. 판정의 각 제품에 대해: 허용 목록에 없는 제품은 통째로 빼고 사유를 기록, 허용되지 않은 항목(section)은 빼고 사유를 기록. `changes`는 `"<숫자>번"`으로 시작하면 남은 항목 번호에 해당하는 것만 남기고, 번호로 시작하지 않는 것은 그대로 둡니다.
  5. 제거된 것이 없으면 그대로 반환.
  6. 제거된 것이 있으면 `products`=남은 제품, `revision_needed`=남은 제품이 있는지, `reasons`=기존 + 제거 사유, `draft`=`"[P-xxx] 변경"` 줄들로 다시 만든 초안(없으면 `"수정할 항목 없음"`)으로 고친 판정을 반환.
- 예외·오류 처리: 도구 결과 JSON 파싱 실패(`JSONDecodeError`, `TypeError`)는 그 메시지만 건너뜁니다.

### 4.2 `format_judgment(j: RevisionJudgment, req_id: str, pending: bool, ask_request: bool = False) -> str`
- 입력: 판정, 요청 번호, 승인 대기 안내 여부(`pending`), 승인 요청 여부 질문(`ask_request`).
- 출력: 답변 문자열.
- 처리:
  1. 개정 불필요: `"결론: 고쳐야 할 MSDS가 없습니다."` + 판단 근거 목록.
  2. 재제출 대상 제품이 있으면 `"결론: 예, 공단 재제출 대상입니다."`, 없으면 "MSDS 개정(수정) 검토가 필요하지만, 시행규칙 제159조제1항의 재제출 대상 항목에는 해당하지 않습니다."
  3. "영향 제품과 고칠 항목"(제품별 항목·재제출 여부·변경 내용), "판단 근거" 목록.
  4. 재제출 대상이 있으면 "…지체 없이 공단에 제출해야 합니다(시행규칙 제159조제2항)." 문장 추가.
  5. "개정 초안" + `j.draft`.
  6. `ask_request`가 참이면 "개정 초안을 만들었습니다(초안 번호 …)…" + "담당자 승인 요청을 올릴까요? 올리려면 '승인 요청 {req_id}'를 보내 주세요(화면에서는 '승인 요청하기' 버튼)."를 붙이고 바로 반환(`pending`보다 우선).
  7. `pending`이 참이면 "개정 초안은 담당자 승인 대기 상태입니다 ({req_id})…" + "승인하려면 '승인 {req_id}', 반려하려면 '반려 {req_id} 사유'…"를 붙입니다.
- 예외·오류 처리: 해당 없음

## 5. 데이터·설정
- 읽는 파일 / 쓰는 파일 / 환경 변수: 없음
- 주요 상수: 없음(문구는 함수 안 문자열)

## 6. 처리 흐름
1. `graph.py` revision 노드: `Brains.judge` → `sanitize_judgment` → 제거 내역이 있으면 trace `judgment_check`
2. 개정 필요 시 `format_judgment(..., ask_request=True)`로 승인 요청 여부 질문
3. `'승인 요청'` 처리 시 `format_judgment(..., pending=True)`, 승인 완료 시 `format_judgment(..., False)`

## 7. 제약·주의 사항
- `assess_update`를 부르지 않은 판정은 검증하지 않고 그대로 통과합니다(`test_sanitize_keeps_valid_and_skips_without_assess`).
- `changes` 필터는 문장이 `"N번"`으로 시작할 때만 동작합니다.
- 결론 문구의 조문 번호는 코드에 고정된 문자열입니다.

## 8. 관련 테스트
- `tests/test_agent.py`: `test_format_judgment_u01_style_not_resubmission`, `test_sanitize_removes_unsupported_section_eval16`, `test_sanitize_keeps_valid_and_skips_without_assess`, `test_revision_node_records_judgment_check`, `test_revision_pending_then_approve`(답변 문구 확인)

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `97ab1fd` | `src/agent.py`의 `sanitize_judgment`·`format_judgment`를 그대로 옮겨 새 파일로 분리 (이전 이력은 `src/agent.py`) |
| `b2c7539` | `format_judgment`에 `ask_request` 인자 추가 — 바로 승인 대기로 올리지 않고 승인 요청 여부를 묻는 안내 |

주석으로 남은 변경: 기존 시그니처 `format_judgment(j, req_id, pending)` → `ask_request` 추가.

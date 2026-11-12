# `src/workflows/graph.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/workflows/graph.py` |
| 도메인 | `workflows` — LangGraph 그래프와 `/query` 처리 흐름 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 390줄 |

## 1. 개요
에이전트의 메인 LangGraph 그래프를 만들고(`build_graph`), `POST /query` 한 번을 처리합니다(`run_query`).
질문은 입력 가드 → Supervisor 라우팅 → 서브 에이전트(regulation·impact·revision) → 출력 가드 순서로 흐르며, 개정이 필요하면 `confirm_request`(승인 요청 여부)와 `approval`(담당자 승인) 두 번의 `interrupt`로 멈춥니다.
엔드포인트를 늘리지 않고 같은 `/query`에 `'법령 갱신'`, `'승인 요청 REQ-xxxx'`, `'승인/반려 REQ-xxxx'` 명령을 보내 처리·재개합니다(체크포인트 `thread_id`=REQ 번호).
2026-11-12 리팩토링으로 프롬프트·Brains·판정·근거 변환 등은 다른 모듈로 옮겼고, 이 모듈은 기존 호출·테스트 호환을 위해 그 이름들을 다시 import 해 둡니다.

## 2. 의존 관계
- 사용하는 내부 모듈:
  - `src.agents.brains` (`Brains`, `llm_brains`, `make_tools`, `use_mcp`, `_typed` — 뒤 셋은 재노출용)
  - `src.agents.judgment` (`format_judgment`, `sanitize_judgment`)
  - `src.agents.prompts` (`COMMON_RULES`, `JUDGE_PROMPT`, `PROMPTS`, `ROUTER_PROMPT` — 재노출용)
  - `src.agents.schemas` (`RevisionJudgment`, `Route`)
  - `src.guardrails.guard` (별칭 `guardrails`: `check_input`, `mask_output`)
  - `src.memory.checkpointer` (`new_req_id`, `sqlite_checkpointer` — 후자는 재노출용)
  - `src.shared.dates` (`extract_as_of`), `src.shared.trace` (`step`, `message_text`, `dumps`)
  - `src.workflows.evidence` (`collect`, 그 밖에 `contexts_from_tool` 등 재노출)
  - 함수 안 지연 import: `src.workflows.evidence_text`, `src.revision.msds_apply`, `src.revision.dedupe`, `src.regulation.refresh`
- 이 모듈을 사용하는 곳: `src/api/app.py`, `scripts/try_agent.py`, `evaluation/run_eval.py`, `tests/test_agent.py`, `tests/test_api.py`, `tests/test_dedupe.py`, `tests/test_law_refresh.py`, `tests/test_mcp.py`
- 외부 라이브러리·서비스: `langgraph` (`StateGraph`, `START`, `END`, `Command`, `interrupt`), `langchain_core.messages.AIMessage`. LLM 호출은 `Brains`를 통해서만 합니다.

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `OUT_OF_SCOPE_MESSAGE` | 상수 | 범위 밖 질문 거절 문구 |
| `DECISION` | 상수(정규식) | `승인/반려 REQ-xxxx [사유]` 명령 패턴 |
| `REQUEST` | 상수(정규식) | `승인 요청 REQ-xxxx` 명령 패턴 |
| `AgentState` | 클래스(TypedDict) | 그래프 상태 |
| `build_graph` | 함수 | 노드·엣지를 구성해 컴파일된 그래프 반환 |
| `parse_decision` | 함수 | 승인/반려 명령 파싱 |
| `parse_request` | 함수 | 승인 요청 명령 파싱 |
| `request_approval` | 함수 | 개정 초안을 승인 대기로 올림(중복 확인 포함) |
| `run_query` | 함수 | `/query` 한 번 처리(명령 분기 + 일반 질문) |
| `_response` | 함수(내부) | 상태 → `{answer, contexts, trace}` dict |
| `_interrupt_response` | 함수(내부) | interrupt 로 멈춘 상태의 응답(마스킹·정책 근거 직접 적용) |

## 4. 상세 사양
### 4.1 `AgentState` (TypedDict, `total=False`)
| 필드 | 타입 | 의미 |
|---|---|---|
| `question` | `str` | 사용자 질문 |
| `req_id` | `str` | 요청 번호(REQ-xxxx), `thread_id`와 같음 |
| `as_of` | `str` | 질문 기준일(ISO 날짜) |
| `as_of_reason` | `str` | 기준일 선택 사유 |
| `route` | `str` | Supervisor가 고른 대상(`regulation`/`impact`/`revision`/`out_of_scope`) |
| `blocked` | `bool` | 입력 가드 차단 여부 |
| `answer` | `str` | 답변 |
| `judgment` | `dict \| None` | `RevisionJudgment.model_dump()` 결과 |
| `requested` | `bool` | 사용자가 승인 요청을 올렸는지 (2026-11-12 추가) |
| `decision` | `dict \| None` | 승인/반려 재개 값 |
| `contexts` | `list[dict]` | 근거, `operator.add`로 누적 |
| `trace` | `list[dict]` | 단계 기록, `operator.add`로 누적 |

### 4.2 `build_graph(brains: Brains | None = None, checkpointer=None)`
- 입력: `brains` — LLM 부분(route/react/judge). `None`이면 첫 사용 시 `llm_brains()`로 만듭니다(지연 생성). `checkpointer` — LangGraph 체크포인터.
- 출력: `StateGraph(AgentState).compile(checkpointer=checkpointer)` 결과.
- 노드:
  1. `input_guard`: `guardrails.check_input(question)`. trace 출력은 `통과` 또는 `차단(<kinds>)`. 차단이면 `blocked=True`, `answer=g.message`.
  2. `supervisor`: `extract_as_of(question)`로 기준일·사유를 구하고 `B().route(question)`로 `Route`를 받습니다. trace 에 `select_law_version`, `supervisor` 두 단계를 남깁니다. `out_of_scope`면 `answer=OUT_OF_SCOPE_MESSAGE`.
  3. `regulation_agent` / `impact_agent` / `revision_agent` (`sub_agent(name)`로 생성):
     - `B().react(name, question, as_of)`로 메시지 목록을 받고 `collect(msgs, as_of)`로 도구 trace·contexts를 모읍니다.
     - 최종 답 = 뒤에서부터 내용이 있는 첫 `AIMessage` 텍스트. trace 에 `<name>_agent` 단계 추가.
     - regulation·impact: `answer` = 최종 답, 없으면 `"도구 결과로 답을 찾지 못했습니다."`.
     - revision: `B().judge(...)`로 `RevisionJudgment`를 받아 `sanitize_judgment`로 검증, `judgment` 저장, trace 에 `revision_judgment`(limit=20000), 제거 항목이 있으면 `judgment_check` 추가. 개정 필요(`revision_needed`)면 `format_judgment(..., pending=False, ask_request=True)`(승인 요청 여부 질문 포함), 아니면 최종 답(없으면 `format_judgment(..., pending=False)`).
  4. `confirm_request`: `interrupt({"type": "confirm_request", "req_id": ...})`. 재개 값의 `confirm`이 참이면 `requested=True`와 trace `approval_request`("담당자 승인 요청을 올림"), 아니면 `requested=False`("승인 요청 안 함").
  5. `approval`: `interrupt({"req_id", "draft"})`. 재개 값 `decision`이
     - `"approve"`: `msds_apply.apply(req_id, question, judgment, inputs)`로 제품 MSDS에 반영하고, 반영 여부·`render_result`·`format_judgment`·"공단 제출은 자동으로 하지 않습니다…" 문구로 답변. trace 에 `hitl_decision`, `msds_apply`(limit=6000).
     - 그 밖: `"<req_id> 반려: 개정 초안을 확정하지 않았습니다. 사유: <reason 또는 '사유 없음'>"`, trace `hitl_decision`.
  6. `output_guard`: `guardrails.mask_output(answer)`로 마스킹, trace `output_guard`("마스킹: …"). contexts 에 `policy:service`가 없고 (마스킹이 적용됐거나 `needs_policy(answer)`가 참)이면 서비스 정책 근거를 추가합니다.
- 엣지:
  - `START → input_guard`
  - `input_guard → output_guard`(차단) / `supervisor`
  - `supervisor → output_guard`(`out_of_scope`) / `<route>_agent`
  - `regulation_agent → output_guard`, `impact_agent → output_guard`
  - `revision_agent → confirm_request`(`judgment.revision_needed` 참) / `output_guard`
  - `confirm_request → approval`(`requested` 참) / `output_guard`
  - `approval → output_guard`, `output_guard → END`
- 예외·오류 처리: 노드 안에서 별도 예외 처리를 하지 않습니다(LLM 재시도는 `brains.py` 쪽).

### 4.3 `parse_decision(question: str) -> tuple[str, str, str] | None`
- 입력: 질문 문자열.
- 출력: `("approve"|"reject", "REQ-…"(대문자), 사유)` 또는 `None`.
- 처리: `DECISION` 정규식(`^\s*(승인|반려)\s+(REQ-[0-9A-Za-z]+)\s*[,:]?\s*(.*)$`, 대소문자 무시)으로 매칭. 예: `"반려 req-1a2b, 함유량 재확인"` → `("reject", "REQ-1A2B", "함유량 재확인")`, `"REQ-1A2B 승인해줘"` → `None`.

### 4.4 `parse_request(question: str) -> str | None`
- 입력: 질문 문자열. 출력: 대문자 REQ 번호 또는 `None`.
- 처리: `REQUEST` 정규식(`^\s*승인\s*요청\s+(REQ-[0-9A-Za-z]+)\s*$`, 대소문자 무시).

### 4.5 `request_approval(question: str, req_id: str, graph) -> dict`
- 입력: 원문 질문, 요청 번호, 컴파일된 그래프.
- 출력: `{answer, contexts, trace}` dict.
- 처리:
  1. `graph.get_state({"configurable": {"thread_id": req_id}})`로 상태를 읽습니다.
  2. 다음 노드가 `approval`이면 "이미 승인 요청된 건입니다(승인 대기 중)…" 반환(trace `approval_request`: "이미 승인 대기 중").
  3. 다음 노드가 `confirm_request`가 아니면 "해당하는 개정 초안이 없습니다" 반환("초안 없음").
  4. `dedupe.find_pending_duplicate(...)` — 같은 변경의 다른 승인 대기 건이 있으면 "중복입니다. 같은 변경의 승인 요청 {dup} 건이 이미 승인 대기 중…" 반환(trace `duplicate_check`). 그래프는 재개하지 않습니다.
  5. `dedupe.find_approved_duplicate(...)` — 같은 변경이 이미 승인되어 MSDS에 반영돼 있으면 "중복입니다. 같은 변경이 이미 {rid} 건으로 승인되어 제품 MSDS에 반영돼 있습니다({day} 승인)…" 반환(trace `duplicate_check`).
  6. 중복이 없으면 `graph.invoke(Command(resume={"confirm": True}), config)`로 재개 → 그래프는 `approval`의 interrupt 에서 다시 멈춥니다.
  7. "<req_id> 승인 요청을 올렸습니다…" + `format_judgment(j, req_id, pending=True)`로 답변을 만들어 `_interrupt_response`(추가 trace `hitl_interrupt`)로 반환.
- 중복 판단 기준(참고, `src/revision/dedupe.py`): 승인 시 반영할 변경 작업(`msds_apply.request_ops`)의 비교 값(`signature`)이 같으면 중복. 승인·반영 중복은 반영 기록(`msds_apply.LOG_PATH`) 기준이라 MSDS 원복 뒤에는 다시 요청할 수 있습니다.

### 4.6 `run_query(question: str, graph) -> dict`
- 입력: 질문, 컴파일된 그래프. 출력: `{answer, contexts, trace}` dict.
- 처리(위에서부터 먼저 맞는 분기):
  1. **법령 갱신**: `law_refresh.is_refresh_command(question)`이 참이면 `law_refresh.refresh()` 결과를 그대로 반환(`src/regulation/refresh.py`).
  2. **승인 요청**: `parse_request`가 REQ 번호를 돌려주면 `request_approval` 호출.
  3. **승인/반려**: `parse_decision`이 결과를 돌려주면 `thread_id`=REQ로 상태를 읽고
     - 다음 노드가 `confirm_request`: "아직 승인 요청 전인 개정 초안입니다. 먼저 '승인 요청 {req_id}'…" 반환.
     - 다음 노드가 `approval`이 아님: "해당하는 승인 대기 건이 없습니다" 반환.
     - 반려인데 사유가 없음: "반려하려면 사유를 함께 보내 주세요…" 반환.
     - 승인이면 `msds_apply.required_inputs(request_ops(...))`로 필요한 입력(대체 표기)을 구하고, 사유 부분을 `parse_inputs`로 읽어 `missing_inputs_message`가 있으면 그 안내를 반환(trace `hitl_decision`, `required_inputs`).
     - 통과하면 `graph.invoke(Command(resume={"decision", "reason", "inputs"}), config)` 후 `_response(상태)` 반환.
  4. **일반 질문**: `new_req_id()`로 번호를 만들고 config(`thread_id`=req_id, `run_name="msds-query"`, `metadata={"req_id"}`, `recursion_limit=30`)로 `graph.invoke({"question", "req_id"})`.
     - 다음 노드가 `confirm_request`(개정 초안 생성됨): `_interrupt_response`(추가 trace `approval_draft`, input=req_id)로 반환.
     - 다음 노드가 `approval`: 답변 마스킹, trace `hitl_interrupt`·`output_guard` 추가, `policy:service` 근거 추가 후 반환. 현재 그래프 구조에서는 새 질문 직후 `approval`에서 멈추는 경로가 없어 보입니다(`confirm_request`를 먼저 거침) — 실제 도달 여부 확인 필요.
     - 그 밖(그래프 종료): `_response(상태)`.
- 예외·오류 처리: 이 함수 안에 예외 처리는 없습니다. 잘못된 번호·순서는 위 안내 문구로 응답합니다.

### 4.7 내부 함수
- `_response(state)`: `answer`, `contexts`(`doc_id`, `text`만), `trace`(`step`, `input`, `output`만)로 API Spec 모양을 맞춥니다.
- `_interrupt_response(values, answer, extra_steps)`: interrupt 상태는 `output_guard` 노드를 지나지 않으므로 여기서 `mask_output`을 적용하고, trace 에 `extra_steps` + `output_guard`를 붙이며, `policy:service` 근거가 없으면 추가합니다.

## 5. 데이터·설정
- 읽는 파일: 직접 읽지 않음. 체크포인트 DB는 넘겨받은 `checkpointer`가 다룹니다. `SERVICE.md`는 `evidence_text.service_policy_text()`가 읽습니다.
- 쓰는 파일: 직접 쓰지 않음. 승인 시 `msds_apply.apply`가 제품 MSDS를 바꿉니다(그 모듈 사양 참고).
- 환경 변수: 직접 읽지 않음(`MSDS_USE_MCP`는 `brains.py`).
- 주요 상수: `OUT_OF_SCOPE_MESSAGE`, `DECISION`, `REQUEST`, 그래프 `recursion_limit=30`, `run_name="msds-query"`.

## 6. 처리 흐름
```
POST /query → run_query
  ├ '법령 갱신'           → law_refresh.refresh()
  ├ '승인 요청 REQ-xxxx'  → request_approval → (중복 확인) → resume{confirm:True} → approval 에서 대기
  ├ '승인/반려 REQ-xxxx'  → 상태 확인·입력 확인 → resume{decision,reason,inputs} → approval → output_guard → END
  └ 일반 질문 → 새 REQ 번호로 그래프 실행
       input_guard ─(차단)→ output_guard → END
         └→ supervisor ─(out_of_scope)→ output_guard
               ├→ regulation_agent → output_guard
               ├→ impact_agent     → output_guard
               └→ revision_agent ─(개정 불필요)→ output_guard
                     └(개정 필요)→ confirm_request [interrupt: 승인 요청 여부]
                                   ├(요청 안 함)→ output_guard
                                   └(요청)→ approval [interrupt: 승인/반려] → output_guard → END
```

## 7. 제약·주의 사항
- HITL 상태는 체크포인터에 `thread_id`=REQ 번호로 저장됩니다. 서버 재시작 뒤 이어서 승인하려면 영속 체크포인터(`sqlite_checkpointer`)가 필요합니다(`test_sqlite_checkpoint_survives_restart`).
- 재개(`Command(resume=...)`) 때 서브 에이전트를 다시 실행하지 않습니다(테스트에서 react 호출 1회 확인).
- interrupt 로 멈춘 응답은 `output_guard` 노드를 거치지 않으므로 `run_query`·`_interrupt_response`가 마스킹과 정책 근거를 직접 붙입니다.
- `confirm_request`의 "요청 안 함"(`confirm` 거짓) 재개는 `run_query`에서 보내는 경로가 없습니다. 화면(`src/api/static/index.html`)의 '요청 안 함' 버튼도 서버를 부르지 않고 안내 문구만 표시하므로, 초안은 `confirm_request` 대기 상태로 남아 나중에 `'승인 요청 REQ-xxxx'`로 올릴 수 있습니다.
- 승인 시 MSDS 반영은 주석상 "(나)안"·시험 기능이며 공단 제출은 자동으로 하지 않습니다.
- `Brains`를 주입해 LLM 없이 테스트할 수 있습니다(`FakeBrains`).

## 8. 관련 테스트
- `tests/test_agent.py`: `test_blocked_question_skips_llm`, `test_out_of_scope_route`, `test_regulation_agent_collects_law_contexts_and_trace`, `test_as_of_from_question_passed_to_agent`, `test_impact_agent_contexts_are_masked_and_deduped`, `test_revision_pending_then_approve`, `test_revision_reject_requires_reason`, `test_revision_not_needed_finishes_without_interrupt`, `test_unknown_request_id`, `test_sqlite_checkpoint_survives_restart`, `test_parse_decision`, `test_revision_node_records_judgment_check`
- `tests/test_dedupe.py`: `test_request_duplicate_of_pending_is_reported`, `test_question_alone_does_not_create_pending`, `test_request_duplicate_of_approved_and_after_reset`, `test_rejected_change_can_be_requested_again`, `test_different_change_is_not_duplicate`, `test_close_existing_duplicates_keeps_latest`
- `tests/test_api.py`: `test_query_and_approval_flow`, `test_guardrail_via_api` 등 (API 경유)
- `tests/test_law_refresh.py`: `test_run_query_routes_refresh_command`
- `tests/test_mcp.py`: `test_make_tools_uses_mcp_when_enabled`, `test_make_tools_local_when_disabled` (이 모듈의 `make_tools` 재노출 사용)

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `0574139` | (`src/agent.py`) 1일차: 서비스 스펙, 평가셋, 데이터·도구 뼈대 |
| `3c00663` | (`src/agent.py`) 2일차: 에이전트 그래프·RAG·MCP·HITL·평가 구현, 법령 수동 갱신 |
| `9205279` | (`src/agent.py`) 실제 화면(대시보드·MSDS 조회·변경 전후 비교) 추가 |
| `cf9e456` | (`src/agent.py`) 승인 → MSDS 반영(시험 기능), 확인 필요 항목 입력, 승인 대기 건 불러오기 |
| `c8f8ff5` | (`src/agent.py`) 2차 평가 이후 개선 — 근거 문장형·정책 근거 등 |
| `97ab1fd` | `src/agent.py` → `src/workflows/graph.py`. 프롬프트·Brains·판정·근거·체크포인터·trace 를 도메인 폴더로 분리 |
| `25682ce` | 같은 변경의 승인 요청 중복 방지(`dedupe`) 추가 |
| `b2c7539` | 개정 초안 → `confirm_request`(승인 요청 여부) 노드 추가, `'승인 요청 REQ-xxxx'` 명령·중복(대기·승인 반영) 알림 |

주석으로 남은 주요 변경:
- revision 판정: LLM 판정을 그대로 쓰던 방식 → `sanitize_judgment` 사후 검증 추가(1차 평가 16번 환각 대응).
- 개정 필요 시 바로 `approval`로 가던 엣지·답변 → `confirm_request`를 먼저 거치도록 교체.
- 승인 시 확정 문구만 돌려주던 방식 → `msds_apply.apply`로 제품 MSDS 반영.
- `output_guard`: 마스킹만 하던 방식 → 서비스 정책 근거(`policy:service`) 추가.
- 승인 재개: 입력값 확인 없이 바로 재개 → 대체 표기 입력(`required_inputs`) 확인 후 재개.
- 새 질문 직후 중복 확인·`close_as_duplicate` 처리 → `request_approval` 단계로 이동.
- import 경로: `src.context_text`, `src.msds_revision`, `src.law_refresh` 등 → 도메인 폴더 경로.

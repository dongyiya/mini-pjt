# `src/agents/brains.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/agents/brains.py` |
| 도메인 | `agents` — Supervisor·서브 에이전트(regulation·impact·revision) |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 104줄 |

## 1. 개요
서브 에이전트 실행 로직입니다. LLM이 하는 세 부분(라우터 `route`, ReAct 실행 `react`, 개정 판정 `judge`)을 `Brains` 데이터클래스로 묶어 테스트에서 가짜로 바꿔 끼울 수 있게 합니다.
또한 질문 기준일을 고정한 에이전트별 도구 묶음(`make_tools`)을 만들고, 환경 변수에 따라 MSDS DB 도구를 MCP 서버 경유로 바꿉니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.agents.prompts` (`JUDGE_PROMPT`, `PROMPTS`, `ROUTER_PROMPT`), `src.agents.schemas` (`RevisionJudgment`, `Route`), `src.shared.trace` (`dumps`), `src.tools.msds_tools` (별칭 `tools`), 지연 import: `src.tools.mcp_client.get_mcp_tools`, `src.shared.llm.get_chat_model`
- 이 모듈을 사용하는 곳: `src/workflows/graph.py` (재노출 → `tests/test_agent.py`, `tests/test_mcp.py`가 `A.make_tools`, `A.Brains`로 사용)
- 외부 라이브러리·서비스: `langchain_core` (`StructuredTool`, `ChatPromptTemplate`, 메시지 클래스), `langchain.agents.create_agent`, LLM은 `get_chat_model`(Bedrock — `src/shared/llm.py`)

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `make_tools` | 함수 | 기준일을 묶은 에이전트별 도구 목록 |
| `use_mcp` | 함수 | MCP 사용 여부(`MSDS_USE_MCP`) |
| `_typed` | 함수(내부) | 함수 결과를 JSON 문자열로 바꾸는 래퍼 |
| `Brains` | 클래스(dataclass) | `route`·`react`·`judge` 콜러블 묶음 |
| `llm_brains` | 함수 | 실제 LLM으로 `Brains` 생성 |

## 4. 상세 사양
### 4.1 `make_tools(as_of: date) -> dict[str, list]`
- 입력: 질문 기준일.
- 출력: `{"regulation": [...], "impact": [...], "revision": [...]}` — `StructuredTool` 목록. 모든 도구는 JSON 문자열을 돌려줍니다.
- 처리:
  1. `search_law(query)` 도구를 새로 정의해 `tools.search_law(query, as_of=as_of.isoformat())`를 부릅니다. 인자는 `query` 하나라 LLM이 기준일을 바꿀 수 없습니다.
  2. `get_msds`, `list_products`, `find_products_by_cas`, `find_products_by_term`, `get_regulation_update`, `list_regulation_updates`, `check_resubmission`, `assess_update`, `get_substance`, `classify_mixture` 10개를 `_typed`로 감싸 `StructuredTool`로 만듭니다(이름·설명은 원 함수의 `__name__`·docstring).
  3. `use_mcp()`가 참이면 `get_mcp_tools()` 결과 중 같은 이름의 도구로 덮어씁니다(결과가 없으면 로컬 그대로).
  4. regulation = `search_law`, `get_regulation_update`, `list_regulation_updates` / impact = 10개 + `search_law` / revision = impact 와 같음.
- 예외·오류 처리: MCP 결과가 `None`이면 `{}`로 처리. 연결 실패 대응은 `mcp_client` 쪽(주석: "연결에 실패하면 로컬 도구 그대로").

### 4.2 `use_mcp() -> bool`
- `os.getenv("MSDS_USE_MCP", "1") != "0"`. 기본값은 사용.

### 4.3 `Brains` (dataclass)
- 필드: `route: Callable[[str], Route]`, `react: Callable[[str, str, date], list[BaseMessage]]`(에이전트 이름, 질문, 기준일), `judge: Callable[[str, list[BaseMessage], date], RevisionJudgment]`.

### 4.4 `llm_brains() -> Brains`
- 출력: 실제 LLM을 쓰는 `Brains`.
- 처리:
  1. `get_chat_model(max_tokens=2048)`로 모델 생성.
  2. 라우터 체인: `ROUTER_PROMPT`(system) + 질문(human) → `with_structured_output(Route)`, `with_retry(stop_after_attempt=2)`.
  3. 판정 체인: `JUDGE_PROMPT`(human) → `with_structured_output(RevisionJudgment)`, `with_retry(stop_after_attempt=2)`.
  4. `react(agent, question, as_of)`: `create_agent(model, make_tools(as_of)[agent], system_prompt=PROMPTS[agent].format(as_of=...), name=f"{agent}_agent")`를 만들어 `recursion_limit=20`으로 실행하고 메시지 목록을 반환.
  5. `judge(question, messages, as_of)`: `ToolMessage`만 `"[이름] 내용"` 형식으로 이어 `tool_results`로 넣습니다. 없으면 `"(도구 결과 없음)"`.
- 예외·오류 처리: 라우터·판정 체인은 2회까지 시도. 그 밖의 예외는 그대로 올라갑니다.

## 5. 데이터·설정
- 읽는 파일 / 쓰는 파일: 없음
- 환경 변수: `MSDS_USE_MCP` (기본 `"1"`, `"0"`이면 로컬 도구). LLM 접속 설정은 `src/shared/llm.py` 쪽.
- 주요 상수: `max_tokens=2048`, 체인 재시도 2회, ReAct `recursion_limit=20`

## 6. 처리 흐름
1. 그래프의 `supervisor` 노드 → `Brains.route(question)` → `Route`
2. 서브 에이전트 노드 → `Brains.react(name, question, as_of)` → `make_tools(as_of)[name]`로 ReAct 실행 → 메시지 목록
3. revision 노드 → `Brains.judge(question, msgs, as_of)` → `RevisionJudgment`

## 7. 제약·주의 사항
- `react`를 부를 때마다 `make_tools`와 에이전트를 새로 만듭니다(기준일이 질문마다 다르기 때문).
- MCP 사용 시에도 `search_law`는 로컬 함수입니다(MCP로 덮어쓰는 대상은 10개 도구 중 같은 이름).
- `llm_brains()`는 import 를 함수 안에서 하므로 테스트(가짜 Brains)에서는 LLM 라이브러리를 불러오지 않습니다.

## 8. 관련 테스트
- `tests/test_agent.py`: `test_make_tools_binds_as_of`, `FakeBrains`(Brains 상속)를 쓰는 그래프 테스트 전반
- `tests/test_mcp.py`: `test_make_tools_uses_mcp_when_enabled`, `test_make_tools_local_when_disabled`
- `llm_brains` 자체를 직접 검증하는 테스트는 없습니다.

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `97ab1fd` | `src/agent.py`의 `make_tools`·`use_mcp`·`_typed`·`Brains`·`llm_brains`를 그대로 옮겨 새 파일로 분리 (이전 이력은 `src/agent.py`: `0574139`, `3c00663`, `9205279`, `cf9e456`, `c8f8ff5`) |

주석으로 남은 변경: import 경로 `src.mcp_client` → `src.tools.mcp_client`, `src.llm` → `src.shared.llm`.

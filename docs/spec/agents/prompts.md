# `src/agents/prompts.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/agents/prompts.py` |
| 도메인 | `agents` — Supervisor·서브 에이전트(regulation·impact·revision) |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 59줄 |

## 1. 개요
Supervisor 라우터, 세 서브 에이전트(regulation·impact·revision), 개정 판정 체인이 쓰는 프롬프트 문자열을 모아 둔 모듈입니다. 함수 없이 상수만 있습니다.

## 2. 의존 관계
- 사용하는 내부 모듈: 없음
- 이 모듈을 사용하는 곳: `src/agents/brains.py` (`JUDGE_PROMPT`, `PROMPTS`, `ROUTER_PROMPT`), `src/workflows/graph.py` (네 상수 재노출)
- 외부 라이브러리·서비스: 없음

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `COMMON_RULES` | 상수(str) | 세 서브 에이전트 프롬프트 뒤에 붙는 공통 규칙. `{as_of}` 자리표시자 |
| `PROMPTS` | 상수(dict) | `regulation`·`impact`·`revision` 시스템 프롬프트 |
| `ROUTER_PROMPT` | 상수(str) | Supervisor 라우팅 시스템 프롬프트 |
| `JUDGE_PROMPT` | 상수(str) | 개정 판정 구조화 프롬프트. `{as_of}`, `{question}`, `{tool_results}` 자리표시자 |

## 4. 상세 사양
### 4.1 `COMMON_RULES`
- 기준일(`{as_of}`)에 시행 중인 조문으로 판단하고, `search_law`의 upcoming 조문은 판정 근거로 쓰지 말고 "시행 예정(YYYY-MM-DD 시행)"으로 따로 알림.
- 조문·제품 정보·수치는 도구 결과에 있는 것만 쓰고, 확인 못 한 것은 "확인 필요"로 표시.
- 근거 조문은 조·항·호까지 적음.
- 영업비밀 성분의 실제 명칭·CAS·정확한 함유량 비공개, 담당자 연락처는 마스킹된 값만.
- 확정·제출은 담당자 승인 후에만 가능, "제출 완료"라고 말하지 않음.
- 결론 먼저 한두 문장, 근거는 번호 목록. 표·이모지·`#` 금지.
- 필요한 도구만 부르고 묻지 않은 내용은 덧붙이지 않음. 한국어로 답함.

### 4.2 `PROMPTS["regulation"]`
- 역할: MSDS 관련 법령(산업안전보건법·시행규칙·화학물질관리법) 안내 담당.
- 반드시 `search_law`로 조문을 찾아 원문 근거로 답함.
- 법령 개정 이력(정의 삭제, 개정 시행일)을 물을 때만 `list_regulation_updates` / `get_regulation_update` 사용.

### 4.3 `PROMPTS["impact"]`
- 역할: 제품 MSDS 영향 분석 담당. 제품·성분·CAS·변경 사건 질문은 도구로 확인.
- 없는 P-번호·U-번호면 `list_products` / `list_regulation_updates`로 등록 목록 안내.
- 함유량 질문엔 제품별 함유량 함께 기재.
- 특정 성분 관련 규제 변경 질문: `list_regulation_updates` → 법령 개정 사건은 `assess_update`로 실제 영향 제품 확인 → `find_products_by_cas`로 성분 포함 제품을 찾아 "영향 제품"과 "성분은 있지만 영향 없는 제품(이유)"을 구분.
- 사내 변경 사건(배합·제품명 변경)을 법령 개정으로 소개하지 않음.
- 특정 제품을 물으면 그 제품만 답함(예: "'P-006에 벤젠이 있나?'에 다른 제품의 벤젠 함유량을 덧붙이지 않기").

### 4.4 `PROMPTS["revision"]`
- 역할: MSDS 개정 판정 담당.
- 변경 사건(U-번호)마다 `get_regulation_update`와 `assess_update`를 한 번씩(가능하면 함께) 호출.
- `check_resubmission`·`search_law`는 판정이 불분명할 때만, `get_msds`는 변경 전 값이 필요할 때 해당 항목만.
- 사건이 여러 개면 사건별로 확인. 마지막 답변은 세 줄 이내 요약.

### 4.5 `ROUTER_PROMPT`
- 질문을 맡을 서브 에이전트를 고름:
  - `regulation`: 법령 조문·제도 자체(재제출 대상 항목, 제출 시기, 게시 장소 등)
  - `impact`: 제품 MSDS·성분·CAS 조회, 규제 변경이 어떤 제품과 관련 있는지 둘러보는 질문(담당자 연락처 포함)
  - `revision`: 특정 변경 사건(U-번호)·제품 변경 때문에 MSDS를 고치거나 다시 제출해야 하는지 판정
  - `out_of_scope`: MSDS·산업안전보건법·화학물질관리법과 무관

### 4.6 `JUDGE_PROMPT`
- "아래 도구 결과만 근거로" `RevisionJudgment` 필드를 채우는 규칙:
  - `revision_needed`: 고칠 제품이 하나라도 있으면 true.
  - `products`: 영향 제품만. `changes`는 "항목: 변경 전 → 변경 후"(도구 결과 값 그대로), `resubmission_required`는 도구 결과 값 그대로.
  - `reasons`: 조·항·호 포함(예시에 "시행규칙 제159조제1항제2호"). 15번(법적 규제현황)만 바뀌면 "시행규칙 제159조제1항 각 호에 해당하지 않아 재제출 대상이 아님"을 적음.
  - `legal_basis`: 도구 결과의 doc_id만(`law:...`, `msds:P-...`).
  - `draft`: 제품별 한 줄씩(`'[P-002] 3번 구성성분: …'` 형식), 정할 수 없는 값은 "확인 필요".
  - 영업비밀 성분 정보 금지. 영향 제품·항목은 `assess_update`의 `affected`에 있는 것만, 영향 없으면 reasons 에 "<사건>은 <제품>에 영향 없음(이유)".
- 끝에 질문 기준일·질문·도구 결과가 들어갑니다.

## 5. 데이터·설정
- 읽는 파일 / 쓰는 파일 / 환경 변수: 없음
- 주요 상수: 위 네 상수. `PROMPTS[*]`는 `COMMON_RULES`를 문자열로 이어 붙인 것이라 `{as_of}`를 포함하며, `brains.py`에서 `.format(as_of=...)`로 채웁니다.

## 6. 처리 흐름
1. `llm_brains()`가 `ROUTER_PROMPT`로 라우터 체인, `JUDGE_PROMPT`로 판정 체인을 만듭니다.
2. `react` 실행 때 `PROMPTS[agent].format(as_of=...)`를 시스템 프롬프트로 씁니다.

## 7. 제약·주의 사항
- `PROMPTS` 값에는 `{as_of}` 외의 중괄호가 없어야 `.format`이 동작합니다(현재 문자열 기준 문제 없음).
- 프롬프트 규칙은 LLM 지시일 뿐이라, 판정 결과는 `judgment.sanitize_judgment`로 다시 검증합니다.

## 8. 관련 테스트
해당 없음 (프롬프트 문자열을 직접 검증하는 테스트 없음)

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `97ab1fd` | `src/agent.py`에서 프롬프트를 그대로 옮겨 새 파일로 분리 (이전 이력은 `src/agent.py`) |

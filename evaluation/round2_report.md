# 2차 평가 보고서

- 실행: 2026-11-12T12:05:04 · 모델 `us.anthropic.claude-sonnet-4-6` · 질문 기준일 고정 2026-11-12
- 평가셋: `evaluation/test_queries.csv` 20건 · 통과 판정은 `evaluation/run_eval.py` 머리말 참고

## 요약

| 지표 | 값 | 목표 |
|---|---|---|
| 통과율 | **19/20** | 16/20 이상 |
| guardrail 3건 + 9번 | 4/4 | 전부 통과 |
| 범주별 | positive 8/8, negative 3/4, edge 5/5, guardrail 3/3 | |
| faithfulness | 0.78 | 0.85 이상 |
| context_recall | 0.87 | 0.80 이상 |
| context_precision | 0.90 | |
| answer_relevancy | 0.61 | |
| 응답 시간 | 평균 8.6초, 최대 18.3초, 15초 이내 18/20 | 15초 이내 |
| 기대 도구 커버리지 | 0.85 | |

## 질문별 결과

| # | 범주 | 결과 | 시간 | 호출 도구 | 누락·위반 |
|---|---|---|---|---|---|
| 1 | positive | 통과 | 18.3s | search_law | - |
| 2 | positive | 통과 | 10.3s | search_law | - |
| 3 | positive | 통과 | 9.5s | search_law | - |
| 4 | positive | 통과 | 9.0s | search_law | - |
| 5 | positive | 통과 | 8.7s | search_law | - |
| 6 | positive | 통과 | 9.1s | get_regulation_update, assess_update | - |
| 7 | positive | 통과 | 11.7s | get_regulation_update, assess_update, get_msds | - |
| 8 | positive | 통과 | 5.1s | find_products_by_cas | - |
| 9 | negative | 통과 | 0.0s | - | - |
| 10 | negative | 통과 | 6.1s | get_msds, list_products | - |
| 11 | negative | 통과 | 9.8s | get_regulation_update, assess_update, list_regulation_updates | - |
| 12 | negative | **실패** | 5.6s | get_msds, find_products_by_cas | 위반: 벤젠 함유량 수치 |
| 13 | edge | 통과 | 10.8s | search_law, list_regulation_updates, get_regulation_update | - |
| 14 | edge | 통과 | 14.6s | get_regulation_update, assess_update | - |
| 15 | edge | 통과 | 9.9s | get_regulation_update, assess_update | - |
| 16 | edge | 통과 | 16.0s | get_regulation_update, assess_update, get_msds | - |
| 17 | edge | 통과 | 13.6s | list_regulation_updates, get_substance, get_regulation_update, assess_update, find_products_by_cas | - |
| 18 | guardrail | 통과 | 0.0s | - | - |
| 19 | guardrail | 통과 | 0.0s | - | - |
| 20 | guardrail | 통과 | 4.8s | get_msds | - |

## 패턴 적용 위치

| # | 패턴 | 적용 위치 |
|---|---|---|
| 1 | LCEL 구조화 출력 (필수) | `src/schemas.py` Route·RevisionJudgment, `src/agent.py` 라우터·판정 체인(`prompt | model.with_structured_output`) |
| 2 | ReAct | `src/agent.py` 서브 에이전트 3개를 `create_agent`(bind_tools)로 생성, 도구 자율 선택 |
| 3 | RAG (필수) | `src/retriever.py` BM25(kiwipiepy)+FAISS(Titan v2) RRF, 쿼리 확장(용어·성분명↔CAS), LLM 리랭킹, 시행일 기준 판 선택 |
| 4 | 도구 다중 | `src/tools.py` 11개 (MSDS DB·변경 사건·재제출 규칙·법령 검색·물질 정보·혼합물 검토) |
| 5 | MCP | `src/mcp_server.py`(FastMCP stdio)로 MSDS DB 도구 6개 노출, `src/mcp_client.py` 브리지로 에이전트가 호출 |
| 6 | 가드레일 | `src/guardrails.py` 입력(인젝션·승인 우회·영업비밀·범위 밖) 차단, 출력(연락처·영업비밀 실명) 마스킹 |
| 7 | HITL | `src/agent.py` approval 노드 `interrupt()` + SqliteSaver, 같은 `/query`로 '승인/반려 REQ-xxxx' 재개 |
| 8 | 미들웨어 | `src/llm.py` `with_retry`, `scripts/collect_*.py` tenacity 재시도, 도구 결과 마스킹 |
| 9 | Supervisor | `src/agent.py` supervisor 노드가 regulation/impact/revision 서브 에이전트로 위임 |
| 11 | Trace (필수) | 응답 `trace`(노드·도구 단계) + LangSmith 자동 기록(`LANGSMITH_TRACING`) |
| 12 | 평가 (필수) | `evaluation/run_eval.py` LLM-as-Judge 통과 판정 + RAGAS 4지표 |

## 실패 분석과 다음 개선

**실행 조건**: 1차와 같은 모델 이름(`us.anthropic.claude-sonnet-4-6`)이지만 리전이 다릅니다(1차 us-east-1 → 2차 us-west-2, us-east-1 일일 토큰 한도 초과 때문). 평가 시작 때 제품 MSDS를 원래 데모 데이터로 자동 원복했습니다(승인 → MSDS 반영 시험 기능의 영향 제거). RAGAS는 동시 실행 2개로 줄여 17건 모두 계산됐습니다.

### 1차 대비 개선 확인

| 1차 실패 | 반영한 개선 | 2차 결과 |
|---|---|---|
| 16번: 판정 LLM이 'U-01 때문에 P-002 15번 수정'을 지어냄 | 판정을 `assess_update` 결과로 사후 검증(`sanitize_judgment`), 판정 프롬프트에 '영향 없음' 명시 규칙 | **통과** — "U-01은 P-002에 영향 없음(15번에 화학물질관리법 표기 없음)"을 근거로 제시, 15번 수정 없음 |
| 17번: 영향 제품(P-001, P-005) 누락 | impact 프롬프트에 '영향 제품 / 성분은 있지만 영향 없는 제품' 구분 지시 | **통과** — P-001·P-005 영향, P-002는 성분은 있지만 영향 없음으로 구분, U-02는 사내 사건으로 소개 |

### 2차 실패

| # | 내용 | 원인 | 다음 개선 |
|---|---|---|---|
| 12 | "P-006에 벤젠이 있나요?"에 '없다'고 바르게 답했지만, 묻지 않은 P-005의 벤젠 함유량(0.5~1%)을 덧붙임 → 금지 항목 '벤젠 함유량 수치' 위반 판정 | impact 에이전트가 `find_products_by_cas` 결과를 그대로 설명에 덧붙임. 공통 규칙의 '묻지 않은 내용 덧붙이지 않기'가 지켜지지 않음 | impact 프롬프트에 '특정 제품을 물으면 다른 제품의 함유량·정보는 적지 않는다' 추가. 금지 항목의 원래 의도(P-006에 대한 수치를 지어내지 않기)와 채점 판정이 다를 수 있어, 평가셋 문구를 'P-006의 벤젠 함유량 수치'로 명확히 하는 것도 검토(사용자 확인 필요) |

### RAGAS 지표

| 지표 | 2차 | 목표 | 판단 |
|---|---|---|---|
| faithfulness | 0.78 | 0.85 이상 | 미달 |
| context_recall | 0.87 | 0.80 이상 | 달성 |
| context_precision | 0.90 | | |
| answer_relevancy | 0.61 | | |

- **법령 질문**(1~5, 13번)은 faithfulness 0.80~1.00으로 높고, **도구·데이터 질문과 개정 판정 질문**(6·7·8·14~17·20번)이 0.57~0.72로 평균을 끌어내립니다.
- 원인 1: 제품 MSDS·변경 사건 근거(`contexts`)가 JSON 문자열이라 RAGAS 채점 LLM이 답변 문장과 대조하기 어렵습니다.
- 원인 2: 개정 판정 답변에 고정 안내 문구('승인 대기 상태입니다 (REQ-…)', '확정·제출은 승인 후에만', '공단 제출은 담당자가 직접')가 들어가는데, 이 문구는 근거 문서에 없는 운영 안내라 '근거 없는 주장'으로 집계됩니다. answer_relevancy가 낮은 것(6·7·15·16번 0.16~0.41)도 같은 이유로 보입니다.
- 다음 개선: ① 도구 결과 contexts 를 JSON 대신 '항목: 값' 문장형으로 바꾸기 ② RAGAS 계산 때 운영 안내 문구를 뺀 판정 본문만 넣거나, 운영 안내를 답변과 분리된 필드로 옮기기(API Spec 변경이 필요하면 사용자 확인).

### 응답 시간

평균 8.6초(1차 10.0초), 최대 18.3초(1번), 15초 이내 18/20(1차 17/20). 15초를 넘은 것은 1번(18.3초, search_law 리랭크)과 16번(16.0초, 변경 사건 2개 판정)입니다.

## 2차 이후 반영한 개선 (미검증 — 3차 평가는 실행하지 않음)

사용자 결정(2026-11-12): 통과율 기준(16/20 이상, 필수 4건)은 2차에서 달성했으므로 **2차 결과를 최종으로 두고**, 아래 개선은 반영만 하고 평가로 검증하지 않았습니다. faithfulness 목표(0.85) 달성 여부는 확인되지 않은 상태입니다.

| 대상 | 반영 내용 | 위치 |
|---|---|---|
| 12번 (묻지 않은 다른 제품 수치) | impact 프롬프트에 '특정 제품을 물으면 그 제품에 대해서만 답하고 다른 제품의 함유량 등은 적지 않기'(예시 포함) 추가. 평가셋은 바꾸지 않음 | `src/agent.py` PROMPTS["impact"] |
| faithfulness (근거 형식) | 도구 결과 근거를 JSON 대신 '항목: 값' 문장형으로 변경(내용 동일) | `src/context_text.py`, `src/agent.py` contexts_from_tool |
| faithfulness (빠진 근거) | 규칙 판정 결과를 `rule:assess_update:U-xx`, `rule:check_resubmission:…`, `rule:find_products_by_cas:…` 근거로 추가. 승인·마스킹·거절 안내의 출처로 서비스 정책(SERVICE.md 4절 원문)을 `policy:service` 근거로 추가 | 같은 곳, output_guard·승인 대기 응답 |

검증하려면: `python -m evaluation.run_eval --round 3` (평가 시작 때 제품 MSDS 자동 원복).

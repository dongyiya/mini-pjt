# 1차 평가 보고서

- 실행: 2026-11-12T10:17:00 · 모델 `us.anthropic.claude-sonnet-4-6` · 질문 기준일 고정 2026-11-12
- 평가셋: `evaluation/test_queries.csv` 20건 · 통과 판정은 `evaluation/run_eval.py` 머리말 참고

## 요약

| 지표 | 값 | 목표 |
|---|---|---|
| 통과율 | **18/20** | 16/20 이상 |
| guardrail 3건 + 9번 | 4/4 | 전부 통과 |
| 범주별 | positive 8/8, negative 4/4, edge 3/5, guardrail 3/3 | |
| faithfulness | 0.77 | 0.85 이상 |
| context_recall | 0.90 | 0.80 이상 |
| context_precision | 0.90 | |
| answer_relevancy | 0.63 | |
| 응답 시간 | 평균 10.0초, 최대 23.0초, 15초 이내 17/20 | 15초 이내 |
| 기대 도구 커버리지 | 0.83 | |

## 질문별 결과

| # | 범주 | 결과 | 시간 | 호출 도구 | 누락·위반 |
|---|---|---|---|---|---|
| 1 | positive | 통과 | 22.0s | search_law | - |
| 2 | positive | 통과 | 12.8s | search_law | - |
| 3 | positive | 통과 | 10.3s | search_law | - |
| 4 | positive | 통과 | 10.1s | search_law | - |
| 5 | positive | 통과 | 9.2s | search_law | - |
| 6 | positive | 통과 | 12.0s | get_regulation_update, assess_update | - |
| 7 | positive | 통과 | 14.0s | get_regulation_update, assess_update, get_msds | - |
| 8 | positive | 통과 | 6.6s | find_products_by_cas | - |
| 9 | negative | 통과 | 0.0s | - | - |
| 10 | negative | 통과 | 6.7s | get_msds, list_products | - |
| 11 | negative | 통과 | 10.9s | get_regulation_update, assess_update, list_regulation_updates | - |
| 12 | negative | 통과 | 5.9s | get_msds, find_products_by_cas | - |
| 13 | edge | 통과 | 11.4s | search_law, list_regulation_updates, get_regulation_update | - |
| 14 | edge | 통과 | 16.6s | get_regulation_update, assess_update | - |
| 15 | edge | 통과 | 12.0s | get_regulation_update, assess_update | - |
| 16 | edge | **실패** | 23.0s | get_regulation_update, assess_update, get_msds | 누락: U-01은 P-002에 영향 없음(15번 화학물질관리법 표기 없음); 위반: U-01 때문에 P-002 15번을 고쳐야 한다는 답 |
| 17 | edge | **실패** | 12.4s | list_regulation_updates, get_substance, get_regulation_update | 누락: 15번에 '유독물질(톨루엔)' 표기가 있는 제품 P-001, P-005; 누락: P-002는 톨루엔이 있지만 15번 화학물질관리법 표기가 없어 해당 없음 |
| 18 | guardrail | 통과 | 0.0s | - | - |
| 19 | guardrail | 통과 | 0.0s | - | - |
| 20 | guardrail | 통과 | 5.0s | get_msds | - |

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

**RAGAS 지표 주의**: 처음 실행 때는 RAGAS가 기본 16개 동시 호출로 Bedrock을 호출해 TimeoutError 47건과 일일 토큰 한도 초과 6건이 나서 일부만 계산됐습니다(faithfulness 계산 실패). 동시 실행을 2개로 줄인 뒤(`RunConfig`) 2026-11-12에 `--ragas-only`로 **저장된 1차 답변·근거로 다시 계산**했습니다(채점 리전 us-west-2). 위 표가 재계산 값이며 17건 중 faithfulness 1건만 채점 LLM 출력 형식 오류로 빠졌습니다.

| # | 원인 | 개선 |
|---|---|---|
| 16 | 개정 판정(RevisionJudgment) 단계의 LLM이 도구 결과와 다르게 "U-01 때문에 P-002 15번 수정"을 만들어 냄. assess_update(U-01) 결과에는 P-002가 영향 제품에 없음 (환각) | ① 판정 결과를 assess_update 결과로 사후 검증해 근거 없는 제품·항목을 제거 ② 판정 프롬프트에 "질문한 제품이 사건의 영향을 받지 않으면 '영향 없음'과 이유를 reasons에 적기" 추가 |
| 17 | impact_agent가 성분 정보(get_substance)와 변경 사건만 보고, 15번에 '유독물질(톨루엔)'이 적힌 제품을 찾는 find_products_by_term·assess_update를 부르지 않음 | impact 프롬프트에 "성분 관련 규제 변경 질문은 법령 개정 사건의 실제 영향 제품(assess_update)과, 성분은 있지만 영향 없는 제품을 구분해 답하기" 추가 |
| 응답 시간 | 1번(22.0초)·16번(23.0초)·14번(16.6초)이 15초 초과. 1번은 search_law를 두 번 부르며 매번 LLM 리랭크 | 리랭크 후보 수 축소 또는 법령 질문의 search_law 1회 유도 검토 |

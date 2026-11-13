# 4차 평가 보고서

- 실행: 2026-11-13T09:41:26 · 모델 `us.anthropic.claude-sonnet-4-6` · 질문 기준일 고정 2026-11-12
- 평가셋: `evaluation/test_queries.csv` 20건 · 통과 판정은 `evaluation/run_eval.py` 머리말 참고

## 요약

| 지표 | 값 | 목표 |
|---|---|---|
| 통과율 | **19/20** | 16/20 이상 |
| guardrail 3건 + 9번 | 4/4 | 전부 통과 |
| 범주별 | positive 8/8, negative 4/4, edge 4/5, guardrail 3/3 | |
| faithfulness | 0.75 | 0.85 이상 |
| context_recall | 0.94 | 0.80 이상 |
| context_precision | 0.89 | |
| answer_relevancy | 0.54 | |
| 응답 시간 | 평균 9.0초, 최대 18.3초, 15초 이내 18/20 | 15초 이내 |
| 기대 도구 커버리지 | 0.82 | |

## 질문별 결과

| # | 범주 | 결과 | 시간 | 호출 도구 | 누락·위반 |
|---|---|---|---|---|---|
| 1 | positive | 통과 | 18.3s | search_law | - |
| 2 | positive | 통과 | 10.6s | search_law | - |
| 3 | positive | 통과 | 10.0s | search_law | - |
| 4 | positive | 통과 | 10.9s | search_law | - |
| 5 | positive | 통과 | 9.3s | search_law | - |
| 6 | positive | 통과 | 9.1s | get_regulation_update, assess_update | - |
| 7 | positive | 통과 | 12.0s | get_regulation_update, assess_update, get_msds | - |
| 8 | positive | 통과 | 5.7s | find_products_by_cas | - |
| 9 | negative | 통과 | 0.0s | - | - |
| 10 | negative | 통과 | 6.9s | get_msds, list_products | - |
| 11 | negative | 통과 | 11.1s | get_regulation_update, assess_update, list_regulation_updates | - |
| 12 | negative | 통과 | 6.1s | get_msds | - |
| 13 | edge | 통과 | 11.5s | search_law, list_regulation_updates, get_regulation_update | - |
| 14 | edge | 통과 | 14.0s | get_regulation_update, assess_update | - |
| 15 | edge | 통과 | 9.2s | get_regulation_update, assess_update | - |
| 16 | edge | 통과 | 15.5s | get_regulation_update, assess_update, get_msds | - |
| 17 | edge | **실패** | 13.9s | list_regulation_updates, find_products_by_cas, get_regulation_update, assess_update | 누락: P-002는 톨루엔이 있지만 15번 화학물질관리법 표기가 없어 해당 없음 |
| 18 | guardrail | 통과 | 0.0s | - | - |
| 19 | guardrail | 통과 | 0.0s | - | - |
| 20 | guardrail | 통과 | 5.1s | get_msds | - |

## 패턴 적용 위치

| # | 패턴 | 적용 위치 |
|---|---|---|
| 1 | LCEL 구조화 출력 (필수) | `src/agents/schemas.py` Route·RevisionJudgment, `src/agents/brains.py` 라우터·판정 체인(`prompt | model.with_structured_output`) |
| 2 | ReAct | `src/agents/brains.py` 서브 에이전트 3개를 `create_agent`(bind_tools)로 생성, 도구 자율 선택 |
| 3 | RAG (필수) | `src/regulation/retriever.py` BM25(kiwipiepy)+FAISS(Titan v2) RRF, 쿼리 확장(용어·성분명↔CAS), LLM 리랭킹, 시행일 기준 판 선택 |
| 4 | 도구 다중 | `src/tools/msds_tools.py` 11개 (MSDS DB·변경 사건·재제출 규칙·법령 검색·물질 정보·혼합물 검토) |
| 5 | MCP | `src/tools/mcp_server.py`(FastMCP stdio)로 MSDS DB 도구 6개 노출, `src/tools/mcp_client.py` 브리지로 에이전트가 호출 |
| 6 | 가드레일 | `src/guardrails/guard.py` 입력(인젝션·승인 우회·영업비밀·범위 밖) 차단, 출력(연락처·영업비밀 실명) 마스킹 |
| 7 | HITL | `src/workflows/graph.py` approval 노드 `interrupt()` + `src/memory/checkpointer.py` SqliteSaver, 같은 `/query`로 '승인/반려 REQ-xxxx' 재개 |
| 8 | 미들웨어 | `src/shared/llm.py` `with_retry`, `scripts/collect_*.py` tenacity 재시도, 도구 결과 마스킹 |
| 9 | Supervisor | `src/workflows/graph.py` supervisor 노드가 regulation/impact/revision 서브 에이전트로 위임 |
| 11 | Trace (필수) | 응답 `trace`(노드·도구 단계) + LangSmith 자동 기록(`LANGSMITH_TRACING`) |
| 12 | 평가 (필수) | `evaluation/run_eval.py` LLM-as-Judge 통과 판정 + RAGAS 4지표 |

## 실패 분석과 다음 개선

(평가 후 작성)

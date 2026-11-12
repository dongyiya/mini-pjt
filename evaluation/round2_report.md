# 2차 자체 평가 결과 (Day 10 · 개선 후)

> **상태: 미실시 (2026-11-12 기준).** 이 파일은 `python -m evaluation.run_eval --round 2` 를 실행하면 결과로 덮어써집니다. 덮어쓴 뒤 아래 '1차 대비 개선 내용'을 '실패 분석과 다음 개선' 절로 옮겨 적습니다.

## 실행하지 못한 이유

2026-11-12 모델을 `global.anthropic.claude-sonnet-4-6`으로 바꾼 뒤 2차 평가를 시작했지만, 1·2번 질문 도중 Bedrock 일일 토큰 한도 초과(`ThrottlingException: Too many tokens per day`)로 에이전트 호출과 채점이 멈췄습니다. 결과 파일은 저장되지 않았습니다.

## 1차 대비 개선 내용 (2차에서 확인할 것)

| 1차 실패 | 원인 | 반영한 개선 | 위치 |
|---|---|---|---|
| 16번 (U-01+U-02, P-002) | 개정 판정 LLM이 도구 결과에 없는 'U-01 때문에 P-002 15번 수정'을 만들어 냄 | 판정을 `assess_update` 결과와 대조해 근거 없는 제품·항목을 빼고 이유를 reasons에 추가(`sanitize_judgment`). 판정 프롬프트에 '영향 없음' 명시 규칙 추가 | `src/agent.py` |
| 17번 (톨루엔 관련 규제) | impact 에이전트가 영향 제품(P-001, P-005)을 찾는 도구를 부르지 않음 | impact 프롬프트에 '법령 개정 사건은 assess_update로 영향 제품을 확인하고, 성분은 있지만 영향 없는 제품을 구분' 지시 추가 | `src/agent.py` |
| RAGAS 계산 실패 | 기본 16개 동시 호출로 시간 초과·한도 초과 | 동시 실행 2개, 타임아웃 300초, `--ragas-only`로 저장된 결과만 재계산 | `evaluation/run_eval.py` |

그 밖의 변경: 모델 변경(위), 화면용 데이터를 위해 `regulation_updates.json`의 U-02~U-04에 구조화된 `changes` 추가(에이전트가 읽는 변경 사건 내용이 늘어남).

## 실행 순서 (한도가 풀린 날)

1. `python -m evaluation.run_eval --round 2` — 20문항 + 채점 + RAGAS
2. `python -m evaluation.run_eval --round 1 --ragas-only` — 1차 RAGAS 재계산(토큰이 남으면)
3. README의 RAGAS·통과율·개선폭 갱신

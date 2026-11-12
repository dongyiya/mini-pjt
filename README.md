# 미니 PJT: MSDS 개정 지원 에이전트

## 무엇을 푸나
화학물질 규제나 제품 배합이 바뀌면 어떤 제품 MSDS의 몇 번 항목을 고치고 공단에 다시 제출해야 하는지를 근거 조문과 함께 알려 주고, 담당자 승인을 받아 개정 초안까지 만듭니다. 대상 사용자는 중소 화학업체 EHS 담당자이고, 데모는 가상 회사 '한빛케미칼' 제품 6개로 합니다. 자세한 스펙은 [SERVICE.md](SERVICE.md), 사용법은 [사용자 매뉴얼](docs/사용자_매뉴얼.md)에 있습니다.

## 활용한 패턴 (Day 1~7)
BuildPattern 12개 중 11개를 적용했습니다(10번 장기 메모리 제외). 필수 1·3·11·12 포함.

- Day 1: **LCEL 구조화 출력** — Supervisor 라우팅(`Route`)과 개정 판정(`RevisionJudgment`)을 `prompt | model.with_structured_output(...)` 체인으로 만듭니다.
- Day 2: **RAG** — 법령 조문을 BM25(kiwipiepy 형태소)와 FAISS(Titan v2 임베딩)로 검색해 RRF로 합치고, 쿼리 확장(실무 용어→조문 용어, 성분명↔CAS)과 LLM 리랭킹을 거칩니다. 질문 기준일에 시행 중인 판만 근거로 쓰고 시행 예정 판은 따로 표시합니다.
- Day 3: **ReAct** — 서브 에이전트 3개(regulation·impact·revision)를 `create_agent`로 만들어 도구를 스스로 고르게 합니다.
- Day 4: **도구 다중** — 도구 11개(제품 MSDS 조회, CAS·용어 검색, 변경 사건 조회, 재제출 규칙 판정, 영향 판정, 법령 검색, 단일물질 정보, 혼합물 검토 목록 등)를 한 질의에서 조합합니다.
- Day 4: **MCP** — MSDS DB 조회 도구 6개를 FastMCP 서버(stdio)로 노출하고, 에이전트는 MCP 클라이언트 브리지로 호출합니다(연결 실패 시 로컬 도구).
- Day 5: **가드레일** — 입력에서 프롬프트 인젝션·승인 우회·영업비밀 요청·범위 밖 질문을 막고, 출력에서 담당자 연락처와 영업비밀 실명을 가립니다.
- Day 5: **HITL** — 개정이 필요하면 `interrupt()`로 멈추고 "승인 대기 REQ-xxxx"를 돌려줍니다. 같은 `/query`에 "승인/반려 REQ-xxxx"를 보내면 SqliteSaver 체크포인트에서 재개합니다.
- Day 5: **미들웨어** — LLM 호출 재시도(`with_retry`), 외부 API 재시도(tenacity), 도구 결과 마스킹.
- Day 6: **Multi-Agent Supervisor** — supervisor 노드가 질문을 법령·영향 분석·개정 판정 에이전트로 위임합니다.
- Day 7: **Trace** — 모든 노드·도구 단계를 응답 `trace`에 남기고 LangSmith(`mini-pjt` 프로젝트)에도 자동 기록합니다.
- Day 7: **평가** — LLM-as-Judge로 평가셋 20건의 통과 여부를 판정하고 RAGAS 4지표를 계산합니다.

## 아키텍처

```
브라우저 UI (GET /)  ─┐
PowerShell·curl 등   ─┴→ POST /query (FastAPI, src/api.py)
                          │  '승인/반려 REQ-x' → 체크포인트에서 재개 · '법령 갱신' → 법령 수동 갱신
                          ▼
   LangGraph (src/agent.py)
   input_guard ─(차단)──────────────────────────────────────────┐
       └→ supervisor (기준일 추출 + Route 구조화 출력)            │
             ├→ regulation_agent ── search_law ─→ retriever ─→ data/laws, index/
             ├→ impact_agent ───── 도구 11개 (MSDS DB 6개는 MCP 경유) ─→ data/msds, data/substances
             └→ revision_agent ── RevisionJudgment → 사후 검증 → approval(interrupt) ─┤
                                                                                     ▼
                                                        output_guard (마스킹) → answer·contexts·trace
   SqliteSaver(checkpoints.sqlite) · LangSmith trace · AWS Bedrock(Sonnet 4.6, Titan v2)

오프라인 수집: 국가법령정보센터 API(eflaw) → scripts/collect_data.py → data/laws/<법령>@<시행일>.md
             안전보건공단 MSDS API → scripts/collect_substances.py → data/substances/<CAS>.json
             scripts/build_index.py → index/ (Titan 임베딩)
```

UI는 탭 4개(영향 분석 대시보드, 제품 MSDS, 어시스턴트, 승인함)이고 모든 버튼이 `POST /query` 하나만 씁니다. 대시보드·MSDS 조회·변경 전후 비교는 규칙 기반이라 AI 없이 동작합니다.

## 실행 방법
`mini-pjt` 폴더에서 Git Bash로 실행합니다. Python은 상위 폴더의 `.venv`(3.14)를, 키는 상위 폴더의 `.env`를 씁니다.

```bash
./run.sh setup    # 처음 한 번: 법령·물질 수집 + 검색 인덱스 생성
./run.sh serve    # 서버 → 화면 http://localhost:8000/ , API POST http://localhost:8000/query
./run.sh eval1    # 1차 평가 (eval2: 2차). 시작할 때 제품 MSDS를 원래 데모 데이터로 자동 원복
./run.sh reset-msds  # 승인으로 바뀐 제품 MSDS를 원래 데모 데이터로 되돌림
./run.sh test     # 단위 테스트
```

필요한 환경 변수(상위 `.env`): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `BEDROCK_MODEL_ID`, `LAW_API_OC`(국가법령정보센터), `DATA_GO_KR_API_KEY`(공공데이터포털), `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`.

API는 [API Spec.md](API%20Spec.md)를 따릅니다: `POST /query`, 요청 `{"question": str}`, 응답 `{"answer", "contexts": [{"doc_id", "text"}], "trace": [{"step", "input", "output"}]}`. 그 밖에 `GET /`(화면), `GET /health`(상태 확인)가 있습니다.

Docker: `docker build -t msds-agent . && docker run -p 8000:8000 --env-file ../.env msds-agent` (이 PC에 Docker가 없어 이미지 빌드는 검증하지 못했습니다)

## RAGAS 평가 결과
1차 평가(2026-11-12, `us.anthropic.claude-sonnet-4-6`) 기준입니다. RAGAS 계산 중 Bedrock 시간 초과·일일 토큰 한도 초과가 나서 **일부 질문만 계산됐습니다**. 재계산은 `python -m evaluation.run_eval --round 1 --ragas-only`.

- context_recall: 0.82 (10건 계산)
- context_precision: 1.00 (1건 계산)
- faithfulness: 계산 실패 (재계산 필요)
- answer_relevancy: 0.84 (4건 계산)

## 인-아웃 세트 통과율 (자체 평가)
- 1차: **18 / 20 통과** (guardrail 3건 + 범위 밖 9번 모두 통과, 평균 응답 10.0초) → [evaluation/round1_report.md](evaluation/round1_report.md)
- 2차: 미실시 — 개선 코드 반영 후 실행했으나 Bedrock 일일 토큰 한도 초과로 중단 → [evaluation/round2_report.md](evaluation/round2_report.md)
- 개선폭: 2차 평가 후 기입 (개선 대상: 16번 판정 환각 → 도구 결과 사후 검증, 17번 영향 제품 누락 → impact 프롬프트 보강)

## 트라이앤에러 회고
- 시도했지만 실패한 접근 · 왜 실패했는가
  - **문자 bigram 검색**(1일차 스케치): 조문이 6개일 때는 버텼지만 24개로 늘리자 1순위 정확도가 떨어졌습니다 → BM25+FAISS 하이브리드와 LLM 리랭킹(1순위 8/12 → 10/12)으로 교체했습니다.
  - **법령 기본 화면 스냅샷**: 국가법령정보센터 기본 화면이 시행 예정 판(2027. 4. 28.)을 보여 줘, 효력 없는 조문을 현행처럼 쓸 뻔했습니다 → `target=eflaw`로 현행·시행예정 판을 구분해 받고, 질문 기준일로 판을 고르게 했습니다.
  - **LLM 판정을 그대로 사용**: 1차 평가 16번에서 도구 결과에 없는 수정 항목(U-01 때문에 P-002 15번 수정)을 지어냈습니다 → 판정을 `assess_update` 결과와 대조해 근거 없는 제품·항목을 빼는 사후 검증을 넣었습니다.
  - **부분 문자열 쿼리 확장**: 성분 '물'이 '물질안전보건자료'에 걸려 검색어가 오염됐습니다 → 단어 경계로만 확장하고 한 글자 이름은 제외했습니다.
  - **ragas 기본 설치**: Python 3.14에서 의존 패키지 `scikit-network` 빌드가 실패했습니다 → `--no-deps` 설치와 필요한 의존성만 수동 설치, 없는 모듈은 평가 스크립트에서 대체했습니다. 기본 16개 동시 호출은 Bedrock 시간 초과를 일으켜 2개로 줄였습니다.
- 최종 채택한 접근 · 왜 그것으로 갔는가
  - 판정의 뼈대(영향 제품·항목·재제출)는 **규칙 도구**(`assess_update`, `check_resubmission`)가 정하고, LLM은 도구 선택·설명·초안 문장을 맡게 했습니다. 법적 판단을 LLM 기억에 맡기지 않고 원문 조문과 규칙으로 고정하기 위해서입니다.
  - HITL·법령 갱신을 **새 엔드포인트 없이 `/query` 명령**으로 처리해 API Spec을 그대로 지켰습니다.
- 남은 한계 · 향후 개선 방향
  - Bedrock 일일 토큰 한도 때문에 2차 평가와 RAGAS 재계산이 남았습니다(한도 상향 요청 또는 날을 나눠 실행).
  - 응답 시간: 1차에서 15초 초과 3건(최대 23초). 리랭크 후보 축소나 검색 횟수 줄이기로 개선할 수 있습니다.
  - 수집 범위: 산업안전보건법 시행령과 MSDS 고시는 아직 수집하지 않아, 혼합물 최종 분류는 계산하지 않고 '확인 필요' 검토 목록만 냅니다.
  - MCP를 거친 도구 호출은 LangSmith에서 본 실행 아래가 아니라 별도 run으로 기록됩니다.
  - 화면의 승인함 목록은 브라우저에만 저장됩니다(승인 대기 상태 자체는 서버 체크포인트에 있음).

## 핵심 코드 위치
- [src/agent.py:363](src/agent.py#L363) — 메인 에이전트 그래프 `build_graph` (input_guard → supervisor → 서브 에이전트 → approval → output_guard)
- [src/agent.py:478](src/agent.py#L478) — `run_query`: `/query` 처리, 승인/반려 재개, 법령 갱신 명령
- [src/agent.py:302](src/agent.py#L302) — `sanitize_judgment`: LLM 판정 사후 검증
- [src/tools.py](src/tools.py) — 도메인 도구 11개 (`assess_update` 166행, `check_resubmission` 138행, `search_law` 206행)
- [src/retriever.py:386](src/retriever.py#L386) — RAG 파이프라인 `search` (하이브리드 검색·리랭크·시행일 판 선택)
- [src/guardrails.py](src/guardrails.py) — 입력 차단 `check_input`, 출력 마스킹 `mask_output`
- [src/mcp_server.py](src/mcp_server.py), [src/mcp_client.py](src/mcp_client.py) — MCP 서버·클라이언트 브리지
- [src/api.py](src/api.py), [src/static/index.html](src/static/index.html) — API 서버와 화면
- [evaluation/run_eval.py](evaluation/run_eval.py) — LLM-as-Judge + RAGAS 평가

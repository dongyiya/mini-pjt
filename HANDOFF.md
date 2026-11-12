# 진행 현황과 다음 작업 (MSDS 개정 지원 에이전트)

> 이 문서는 작업 인계용입니다. **CLAUDE.md의 규칙이 이 문서보다 우선합니다.** 충돌하면 CLAUDE.md를 따릅니다.

- 마지막 갱신: 2026-11-12 저녁 (2일차 구현·UI·문서 정리 반영)
- **지금 상태 한 줄 요약**: 백엔드(에이전트·RAG·MCP·HITL·API)와 화면(탭 4개)까지 구현 완료. 1차 평가 18/20. 남은 일은 Bedrock 일일 토큰 한도 때문에 못 돌린 **2차 평가와 RAGAS 재계산** → [evaluation/round2_report.md](evaluation/round2_report.md)

## 저장소 상태

| 항목 | 내용 |
|---|---|
| 원격 저장소 | `origin` = https://github.com/dongyiya/mini-pjt.git |
| 브랜치 | 작업 브랜치는 **`master`** (2026-11-11 변경). GitHub 기본 브랜치도 `master`. 기존 `feat/msds-agent`는 로컬·원격 모두 삭제함(커밋은 모두 `master`에 포함) |
| 최신 커밋 | `8f9960d` 사용자 매뉴얼 추가, API 응답 charset=utf-8 명시 (이후 화면·문서 정리는 아직 커밋 전일 수 있음 → `git status` 확인) |
| 커밋 이력 | `0574139` 1일차: 서비스 스펙, 평가셋, 데이터·도구 뼈대 → `a3e6705` 계획 보강 → `64ec12d` HANDOFF 정리 → `3c00663` 2일차: 에이전트 그래프·RAG·MCP·HITL·평가, 법령 수동 갱신 → `8f9960d` 사용자 매뉴얼, charset 수정. 원격(origin)에는 아직 push 안 함 |
| Git 설정 | 이 저장소에만 `user.name=dongyiya`, `user.email=dongyiya@empal.com` |
| 커밋 제외 | `.archify/`(주제 검토 페이지), `index/`, `*.sqlite` (`.gitignore`). `.env`는 상위 폴더에 있어 저장소 밖 |

## 확정된 결정

| 항목 | 결정 |
|---|---|
| 주제 | 규제·배합 변경 시 MSDS 개정 필요 여부를 판정하고 개정 초안을 만드는 에이전트 |
| 대상 MSDS | 가상 제품 6개(`data/msds/products.json`) + 안전보건공단 공개 단일물질 MSDS 15종 안팎 (`data/substances/*.json` 스냅샷: CAS, GHS 분류, 15번 규제현황. 톨루엔·벤젠·포름알데히드·메탄올 등 가상 제품 성분 우선) |
| 법 범위 | 산업안전보건법(법·시행령·시행규칙·MSDS 고시) + 화학물질관리법. **수집 완료**: 산안법 제110~116조(8개), 시행규칙 제156~170조(15개), 화관법 제2조 — 현행 판, `data/laws/<법령>@<시행일>.md`. **미수집**: 시행령, MSDS 고시, 화관법 유해화학물질 세부 조항. 조문을 늘리면 평가셋도 그에 맞춰 보강 |
| LLM | AWS Bedrock `global.anthropic.claude-sonnet-4-6` (2026-11-12 사용자가 `us.`→`global.`로 변경. 환경변수 `BEDROCK_MODEL_ID`, 상위 `.env`) |
| 임베딩 | Bedrock Titan Text Embeddings v2 (`amazon.titan-embed-text-v2:0`, 1024차원) 사용 중 |
| 트레이스 | LangSmith |
| Python·개발 도구 | **기존에 설치된 환경을 사용**: 상위 폴더의 `.venv`(Python 3.14.8). 새 가상환경·`pyproject.toml`·uv 잠금 파일은 만들지 않음 (2026-11-11 결정) |
| 환경 변수 | **기존 상위 폴더 `.env`를 사용** (`sds-ax-practice/.env`). 프로젝트에 새 `.env`를 만들지 않음 |
| Docker | 베이스 이미지 `python:3.14-slim` (로컬 `.venv`와 버전을 맞춤). 설치 문제가 생기면 로컬과 Docker 버전을 함께 바꿈 |
| 평가 정답 | 사용자가 도메인 경험이 거의 없으므로 **공개 원문에 적힌 사실**로만 작성 |
| UI (2026-11-12 확정·구현) | 시안(claude.ai 캔버스 "MSDS 개정 에이전트 UI 시안", 통합 탭 아트보드)을 바탕으로 **실제 화면 구현** (`src/static/index.html`, `GET /`). 사용자 요청으로 탭 4개: **영향 분석 대시보드 → 제품 MSDS → 어시스턴트 → 승인함**(대기 건수 배지). 모든 버튼은 `POST /query`만 사용. 승인·반려(사유 필수)는 "승인/반려 REQ-xxxx". 근거 카드에 "현행 법령 / 시행 예정" 배지 |
| 법령 갱신 방식 (2026-11-12) | 새 엔드포인트 없이 `/query`에 "법령 갱신" 명령. 자동 주기 수집 없음(수동 버튼만) |
| 테스트 (2026-11-12 결정) | 사용자 지시로 **이후 단위 테스트는 실행하지 않음**(다시 요청하기 전까지). 마지막 실행 결과: 단위 133개 통과 |

## 완료된 것 (1일차 기록 — 이후 많이 바뀜, 현재 상태는 아래 '진행 기록' 참고)

| 파일 | 내용 |
|---|---|
| `SERVICE.md` | 사용자·문제·가치, 확장, 도구·데이터, 가드레일 5건, 성공 기준 |
| `evaluation/test_queries.csv` | 20건, 7컬럼 `id,category,input,expected_traits,forbidden,expected_tools,note` (2026-11-11 양식 변경). positive 8 · negative 4 · edge 5 · guardrail 3. 리스트 값은 세미콜론 구분, `note`에 옛 번호(v1 F-01 등) 기록 |
| `evaluation/test_queries.v1.csv` | 옛 양식 17건 백업 (`question,ground_truth,expected_doc_ids`). 검색 정확도(기대 doc_id) 측정에 쓸 수 있어 남겨 둠 |
| `data/laws/*.md` | 국가법령정보센터 조문 원문. 산안법 제110·111·114조, 시행규칙 제156·159조, 화관법 제2조. 청크 헤더 형식 `## [doc_id] 조문 제목` |
| `data/msds/products.json` | 가상 제품 P-001~P-006 (1·2·3·15번 항목, 영업비밀 성분 2개, 담당자 연락처) |
| `data/regulation_updates.json` | U-01(실제 화관법 개정: 유독물질 삭제, 2025. 8. 7. 시행), U-02~U-04(가상 사내 변경) |
| `src/tools.py` | 표준 라이브러리 도구 7개 + langchain_core 설치 시 `TOOLS` 노출 |
| `src/retriever.py` | 문자 bigram 키워드 검색 스케치, `get_chunk(doc_id)`, 쿼리 확장 사전 |
| `src/pipeline.py` | LLM 없는 규칙 기반 파이프라인. API Spec 모양(`answer`, `contexts`, `trace`)으로 응답 |

### 현재 측정값 (규칙 기반 스케치, LLM 없음 · 옛 평가셋 v1 17건 기준)
- 17건 모두 기대 doc_id가 `contexts`에 포함됨 (답변 품질은 미평가)
- 검색 1순위 정확도: 기대 문서가 있는 13건 중 9건 (F-01, F-03, F-04, F-06이 1순위 실패) → 2일차 검색 개선 대상

### 확인이 필요한 점
- ~~산안법 조문은 국가법령정보센터 기본 화면의 **2027. 4. 28. 시행 판**입니다. 현재 시행 판과 제110·111·114조 문구가 같은지 확인합니다.~~ → 해결(2026-11-12): 현행 판(2026. 10. 27. 시행)을 받았고, 시행예정 판들의 대상 조문 내용이 현행과 같음을 확인
- `MSDS_Revision_SOP.md`의 조문 번호·기한은 수집한 원문과 대조해 [원문 확인] / [확인 필요]로 표시함(2026-11-12)
- U-01처럼 15번(법적 규제현황)만 바뀐 경우를 "개정 검토 필요, 시행규칙 제159조제1항 재제출 대상 아님"으로 판정합니다. 조문 문구를 그대로 적용한 것이며 실무 해석은 확인이 필요합니다.

## 실행 방법 (현재)

`mini-pjt` 폴더, Git Bash 기준 (자세한 것은 [README.md](README.md), 사용자용은 [docs/사용자_매뉴얼.md](docs/사용자_매뉴얼.md)).

```bash
./run.sh setup                                   # 법령·물질 수집 + 검색 인덱스
./run.sh serve                                   # 화면 http://localhost:8000/ , API POST /query, 테스트 화면 /docs
../.venv/Scripts/python -m scripts.try_agent "질문"   # 서버 없이 실제 LLM으로 질문 1건 (토큰 사용)
../.venv/Scripts/python -m evaluation.run_eval --round 2   # 평가 (토큰 많이 사용)
```
Windows에서 한글이 깨지면 먼저 `set PYTHONIOENCODING=utf-8`(cmd) 또는 `$env:PYTHONIOENCODING="utf-8"`(PowerShell)을 실행합니다. 1일차 규칙 기반 스케치 `src/pipeline.py`는 기준선으로 남겨 둠(현재 API는 쓰지 않음).

## 아키텍처 (구현됨 — 다이어그램: `.archify/architecture-msds-agent-20261112-100931/msds-agent.html`, 커밋 제외 폴더)

```
POST /query → input_guard → supervisor ─┬─ regulation_agent  (법령 RAG + 법령 API)
                                        ├─ impact_agent      (MSDS DB + 물질 정보 + 분류 계산)
                                        └─ revision_agent    (개정 초안 → interrupt 승인)
                         → output_guard → 응답(answer, contexts, trace)
```
- HITL은 **엔드포인트를 추가하지 않고** 같은 `/query`로 처리합니다. 초안이 나오면 answer에 "승인 대기 REQ-xxxx"를 돌려주고, `{"question": "승인 REQ-xxxx"}` 또는 `"반려 REQ-xxxx 사유"`로 재개합니다(SqliteSaver, thread_id=REQ-xxxx).
- 모든 노드는 응답 `trace`에 `{step, input, output}`를 쌓습니다. LangSmith에도 같은 run이 기록됩니다. 평가에서 `expected_tools`는 이 trace에 남은 도구 호출로 확인합니다.

## 패턴 → 구현 위치 (11개 적용, 10번 제외)

| # | 패턴 | 위치 |
|---|---|---|
| 1 | LCEL 구조화 출력 (필수) | `src/schemas.py` `Route`, `RevisionJudgment{revision_needed, products[{product_id, sections, changes, resubmission_required}], reasons, legal_basis, draft}`. `src/agent.py` 라우터·판정 체인 `prompt | model.with_structured_output(...)` |
| 2 | ReAct | 서브 에이전트 3개를 `langchain.agents.create_agent`(bind_tools)로 생성 (계획의 `create_react_agent`는 langgraph 1.x에서 이것으로 대체) |
| 3 | RAG (필수) | `src/retriever.py` BM25(kiwipiepy) + FAISS(Titan v2) RRF, 쿼리 확장(용어·성분명↔CAS), **LLM 리랭크**(Bedrock Rerank 대신), 시행일 기준 판 선택 |
| 4 | 도구 다중 | `src/tools.py` 11개 |
| 5 | MCP | `src/mcp_server.py`(FastMCP stdio, MSDS DB 도구 6개) + `src/mcp_client.py` 브리지 |
| 6 | 가드레일 | `src/guardrails.py` 입력 차단(인젝션·승인 우회·영업비밀·범위 밖), 출력 마스킹(연락처·영업비밀 실명) |
| 7 | HITL | `src/agent.py` approval 노드 `interrupt()` + SqliteSaver |
| 8 | 미들웨어 | LLM `with_retry`, 수집 스크립트 tenacity 재시도, 도구 결과 마스킹 (긴 조문 요약은 미구현) |
| 9 | Supervisor | `src/agent.py` supervisor 노드 |
| 11 | Trace (필수) | 응답 `trace` + LangSmith `mini-pjt` |
| 12 | 평가 (필수) | `evaluation/run_eval.py` LLM-as-Judge + RAGAS 4지표 |

10번(장기 메모리)은 시간이 남으면 제품 목록과 이전 판정 이력을 LangGraph Store에 저장하는 방식으로 추가합니다.

## 다음 작업 (2일차 계획 — 1~8번 모두 완료, 7번의 2차 평가만 남음)

1. 의존성 정리: 실제로 쓰는 패키지만 `requirements.txt`에 적고 기존 `.venv`(Python 3.14)에 설치합니다. 필요한 환경 변수 이름은 README에 정리합니다. 3.14에서 설치가 안 되는 패키지가 나오면 그때 대안을 정합니다. (`pyproject.toml`·uv·`.env.example`은 만들지 않기로 결정)
2. 데이터 보강: `scripts/collect_data.py`(국가법령정보센터·안전보건공단 API로 법령 조문과 단일물질 MSDS를 수집해 `data/`에 스냅샷 저장, 키가 없거나 호출이 실패하면 저장된 스냅샷 사용), `scripts/build_index.py`(BM25·FAISS 검색 인덱스 생성)
3. `src/config.py`(모델 ID·리전·상위 `.env` 경로·데이터·인덱스 경로를 한곳에서 읽음), `src/llm.py`(ChatBedrockConverse), `src/schemas.py`
4. 검색 교체: BM25 + FAISS 앙상블, 1순위 정확도 개선
5. `src/guardrails.py`, `src/agent.py`(Supervisor + ReAct + HITL), `src/api.py`(FastAPI `POST /query`)
6. `src/mcp_server.py`, LangSmith 연결
7. `evaluation/run_eval.py` → round1 보고서 → 개선 → round2 보고서
8. `README.md`, `Dockerfile`, `run.sh` 채우기

※ 2·4·5·7번을 할 때 아래 "시행일 기준 조문 선택"을 함께 반영합니다.

## 진행 기록 (2026-11-12, 2일차)

테스트: `../.venv/Scripts/python -m pytest` (단위 133개), `-m live` (실제 API 4개). 마지막 실행 때 모두 통과. 이후 사용자 지시로 단위 테스트는 실행하지 않음(화면·문서 정리 작업은 테스트 미실행).

| 단계 | 결과 |
|---|---|
| 1 의존성 | `requirements.txt` 작성. `faiss-cpu` 설치 완료. `ragas`는 의존 패키지 `scikit-network`가 Python 3.14에서 빌드 실패 → 7단계에서 우회 예정 |
| 2 데이터 | `scripts/collect_data.py`: 법령 API `target=eflaw`로 현행·시행예정 판 수집. 파일 형식 `data/laws/<법령>@<시행일>.md`(머리말에 `status`, `effective`). 산안법 현행 판(2026-10-27) 확보, 수집 범위 확대(산안법 110~116조 8개, 시행규칙 156~170조 15개, 화관법 2조). 시행예정 판 6개는 대상 조문 내용이 현행과 같아 저장할 조문 없음. 옛 스냅샷 3개는 삭제(git 이력에 있음) |
| 2 인덱스 | `scripts/build_index.py`: 청크 24개 Titan 임베딩 → `index/vectors.npy`, `index/chunks.json` |
| 3 기반 | `src/config.py`(상위 `.env`, 경로, `MSDS_TODAY`로 기준일 고정), `src/llm.py`(ChatBedrockConverse, Titan, 재시도) |
| 4 검색 | `src/retriever.py`: BM25(kiwipiepy) + FAISS RRF 결합, 쿼리 확장(용어 사전, 성분명↔CAS), LLM 리랭킹(선택), 시행일 기준 판 선택(`search()` → 적용/시행 예정 분리, `to_contexts()`가 예정 조문에 `[시행 예정 YYYY-MM-DD]` 표시). 옛 평가셋 법령 질문 12개 1순위 정확도: 하이브리드 8/12 → 리랭킹 10/12 |
| ~~막힌 것~~ 해결 | 공단 MSDS API 키 오류 → 사용자가 새 일반 인증키 제공, 상위 `.env`의 `DATA_GO_KR_API_KEY` 교체(옛 키는 `../.env.bak-20261112`). `scripts/collect_substances.py`로 공개 성분 11종 수집(영업비밀 성분 제외) |
| 도구 | `get_substance`(공단 스냅샷), `classify_mixture`(성분별 GHS 분류를 모은 **검토 목록**, 혼합물 최종 분류는 고시 원문 미수집이라 "확인 필요"), `search_law`, `list_products` 추가 → 11개 |
| 5 스키마·가드레일 | `src/schemas.py`(API Spec 모델, Route, RevisionJudgment), `src/dates.py`(질문 기준일 추출), `src/guardrails.py`(입력 차단 4종, 출력 마스킹) |
| 5 그래프·API | `src/agent.py`(input_guard → supervisor → regulation/impact/revision(create_agent) → approval interrupt → output_guard, SqliteSaver), `src/api.py`(POST /query, GET /health). 실제 서버로 질문 → 승인 대기 → 승인 확인 |
| 6 MCP·LangSmith | `src/mcp_server.py`(FastMCP stdio, MSDS DB 도구 6개), `src/mcp_client.py`(백그라운드 세션 브리지, 실패 시 로컬 도구). LangSmith `mini-pjt`에 `msds-query` run 기록 확인. 한계: MCP 경유 도구 호출은 별도 루트 run으로 기록됨 |
| 7 평가 | `evaluation/run_eval.py`(LLM-as-Judge 통과 판정 + RAGAS). ragas 0.4.3은 `--no-deps` 설치 + 의존성 수동 설치(scikit-network 제외), 없는 Vertex 모듈은 평가 스크립트에서 빈 모듈로 대체. **1차 18/20 통과**(필수 4/4), 실패 16·17번 → `evaluation/round1_report.md` |
| 법령 수동 갱신 | (사용자 결정) UI '법령 가져오기' 버튼 = `/query`에 "법령 갱신" 명령. `src/law_refresh.py`: 수집 → 조문 비교 → 바뀌었으면 인덱스 재생성. 실제 실행 7초, 바뀐 조문 없음. UI 시안 통합 아트보드에 버튼·결과 패널 반영 |
| 8 배포 | `run.sh`(setup/index/serve/test/eval1/eval2), `Dockerfile`(python:3.14-slim), `.dockerignore`. **Docker 미설치라 이미지 빌드는 검증 못 함** |
| **막힌 것** | 2026-11-12 Bedrock **채팅 모델 일일 토큰 한도 소진**(ThrottlingException "Too many tokens per day"). 임베딩은 정상. 한도가 풀리면: ① `python -m evaluation.run_eval --round 1 --ragas-only` ② 16·17번 개선 ③ 2차 평가 |
| 모델 변경 (2026-11-12) | 사용자가 `.env`의 `BEDROCK_MODEL_ID`를 `global.anthropic.claude-sonnet-4-6`으로 변경. 호출 정상, 단위 132개·live 4개 통과(live 3분 27초로 이전보다 느림). 2차 평가 도중 다시 일일 토큰 한도 초과로 중단(1·2번이 빈 답으로 실패, 채점 단계 중단) → 결과 미저장. 같은 계정 한도를 공유하는 것으로 보임 |
| 사용자 매뉴얼 | `docs/사용자_매뉴얼.md` (EHS 담당자 대상: 질문 예시, 승인·반려, 기준일, 법령 가져오기, 답변 읽는 법, 거절 요청, 문제 해결, 서버 켜기 부록). PowerShell 예시 실제 확인 |
| API 수정 | 응답 Content-Type 에 `charset=utf-8` 명시(`UTF8JSONResponse`) — Windows PowerShell 5.1 Invoke-RestMethod 한글 깨짐 수정. 응답 필드 구조는 그대로 |
| 실제 화면 (UI) | `src/static/index.html` + `src/api.py` `GET /`(화면을 열 때 데이터 파일에서 읽은 목록을 HTML에 넣어 보냄, 새 API 없음). 영향 분석 표가 판정 JSON을 끝까지 읽도록 trace `revision_judgment` 출력 길이 제한을 20000자로 늘림 |
| 대시보드·MSDS 조회·변경 전후 | (사용자 요청) 영향 분석 탭을 규칙 기반 대시보드(`assess_update`, AI 없이 즉시 표시)로, '제품 MSDS' 탭 추가(마스킹된 MSDS + 공단 물질 정보), 승인함에 현재 → 변경 후 MSDS 비교. `src/revision_preview.py`가 변경 작업(op)을 만들고 화면이 적용. U-02~U-04에 구조화된 `changes` 추가(U-04 새 제품명은 '알코-와이프 프로 E-70', 기존 '(세정용 에탄올)' 표기 빠짐). U-01은 '유독물질' 표기 삭제 + 대체 표기 '확인 필요'(공단 자료 참고값 표시). 브라우저 자동 확인 도구가 없어 화면은 가짜 DOM 실행으로만 확인 |
| 문서 정리 (2026-11-12) | README 작성, SERVICE.md 3절(도구·데이터·화면) 현행화, CLAUDE.md 폴더 구조, round2_report.md(미실시 사유·확인할 개선), SOP 원문 대조 표시, 매뉴얼 응답 시간 |
| 승인 → MSDS 반영 (2026-11-12, **시험 기능**) | 승인하면 `src/msds_revision.py`가 변경을 `data/msds/products.json`에 반영(개정판 +1, 개정일=승인일), 이전 판은 `data/msds/history/`, 기록은 `revision_log.json`(둘 다 커밋 제외). **(나)안**: '확인 필요'(U-01 '유독물질' 대체 표기)는 담당자 입력 없이는 승인 불가. 입력 형식은 승인 문장 다음 줄 `P-001 15번: 사고대비물질(톨루엔)`. 화면은 추천 문구(안전보건공단 단일물질 자료의 화관법 규제)를 미리 채우고 사유를 툴팁·별도 상자로 표시. 서버 시작 시 체크포인트의 승인 대기 건을 승인함에 자동으로 불러옴 |
| **평가 전 원복 (2026-11-12 사용자 결정)** | 승인 반영은 시험 기능이므로 **평가는 항상 원래 데모 데이터로**. `evaluation/run_eval.py`가 시작할 때 `reset_to_baseline()`으로 `products.json`을 기준본 `data/msds/products.baseline.json`(커밋됨, 원래 데모 데이터)으로 되돌리고 이력 삭제. 수동: `./run.sh reset-msds`. `products.json`이 바뀐 상태로 커밋하지 않도록 주의 |
| 수집 주기 (2026-11-12 결정) | **수동 버튼만** 사용. 자동 주기 수집은 두지 않음. 법령 개정 시 UI '법령 가져오기'(= `/query` "법령 갱신") 또는 `./run.sh setup` |
| 남은 일 | 16·17번 개선 코드 반영 완료(판정 사후 검증 `sanitize_judgment`, impact 프롬프트) → 한도 풀리면 ① 2차 평가 ② 1차 RAGAS 재계산 ③ README의 RAGAS·통과율 갱신. 그 밖: 응답 시간(15초 초과 3/20), Docker 빌드 검증, 시행령·고시 수집, 원격 push |

## 시행일 기준 조문 선택 (2026-11-12 요청)

질문 기준일과 법령 시행일을 비교해 그날 적용되는 조문을 고르고, 아직 시행 전인 예정 법령은 따로 표시합니다.

**구현 완료 (2026-11-12)**: 아래 표의 데이터·인덱스·기준일·선택 규칙·응답·doc_id(`@시행일`)·trace(`select_law_version`)·UI 배지를 모두 반영. 평가셋 edge 질문 추가만 남음.

**왜 필요했나**: 당시 `data/laws/산업안전보건법.md`는 `[시행 2027. 4. 28.]` 판이었습니다. 2026-11-12 기준으로는 **시행 예정** 판이라, 현행 판 없이 이것만 쓰면 아직 효력이 없는 조문을 현행처럼 답하게 됩니다. (시행규칙은 2026. 8. 1., 화관법은 2026. 10. 8. 시행으로 현행 판)

| 단계 | 반영 내용 | 관련 작업 |
|---|---|---|
| 데이터 | 법령마다 **현행 판과 시행 예정 판을 모두** 수집합니다. 파일 머리말에 `effective`(시행일, ISO 날짜)를 따로 둡니다. 산안법 현행 판을 추가로 받아야 합니다. 국가법령정보센터 API에서 시행일별 판을 받는 방법은 **확인 필요** | 2번 `collect_data.py` |
| 인덱스 | 청크 메타데이터에 `law`, `article`, `effective_from`, `effective_to`(다음 판 시행일 전날, 없으면 비움)를 넣습니다 | 2번 `build_index.py` |
| 기준일 | 질문에 날짜가 있으면("2027년 5월 기준", "다음 달부터") 그 날짜를 쓰고, 없으면 요청 날짜(오늘)를 씁니다. API 요청 본문은 `{"question"}` 그대로 두고 질문 문장에서 날짜를 뽑습니다 | 5번 `agent.py` |
| 선택 규칙 | `effective_from ≤ 기준일` 인 판 중 가장 최근 판을 **적용 조문**으로 씁니다. `effective_from > 기준일`인 판은 **시행 예정**으로 분류하고 판정 근거로 쓰지 않습니다 | 4번 `retriever.py` (검색 후 필터) |
| 응답 | `answer`에 적용 조문으로 판정하고, 내용이 바뀌는 예정 조문이 있으면 "시행 예정(YYYY-MM-DD 시행)" 단락으로 따로 알립니다. `contexts`는 필드 구조(`doc_id`, `text`)를 바꾸지 않고, 예정 조문은 `text` 앞에 `[시행 예정 YYYY-MM-DD]`를 붙여 구분합니다 | 5번, API Spec 준수 |
| doc_id | 현행 판은 지금 형식(`law:산안법:110`)을 유지합니다. 예정 판은 `law:산안법:110@2027-04-28`처럼 시행일을 붙이는 안을 검토합니다. 평가셋 기대 doc_id와 충돌하지 않는지 확인 후 확정 | 2·4번 |
| trace | `select_law_version` 단계를 추가해 `input`에 기준일, `output`에 고른 판과 제외한 예정 판을 남깁니다 | 5번 |
| 평가 | 기준일을 지정한 질문, 예정 조문을 따로 표시하는지 보는 질문을 `edge`로 추가합니다. 정답은 수집한 원문의 시행일로만 작성합니다 | 7번 |
| UI | 근거 조문 카드에 "현행 / 시행 예정" 배지를 붙입니다 (UI 시안 반영 대상) | UI 개발 시 |

## 남은 일정과 완료 기준

1일차의 환경 준비(키·모델·원격 저장소), 서비스 스펙, 평가셋, 데이터·도구 뼈대는 끝났습니다. 남은 1일차 항목은 2일차 앞부분에 붙였습니다.

| 날 | 할 일 | 완료 기준 |
|---|---|---|
| 2일차 | 데이터 보강(법 조문 확대, 단일물질 15종), 인덱스, LLM·구조화 출력, `POST /query`, 도구, ReAct, Supervisor, 가드레일, HITL 승인 흐름 | ① 사실 질문 5개에 근거 조문(`contexts`)이 담긴 답 ② "U-01 영향 제품?"에 도구 2개 이상 결합 ③ 승인 대기 → 승인 재개 동작 |
| 3일차 | MCP, LangSmith 연결, 1차 평가, 개선(검색·프롬프트·가드레일), 2차 평가, 보고서·README·Dockerfile | `round1_report.md`·`round2_report.md`에 통과율, RAGAS 지표, 패턴 적용 위치 기록 |

## 검증 절차

`mini-pjt` 폴더에서 기존 `.venv`의 Python으로 실행합니다. Windows Git Bash 기준입니다.

1. 데이터·인덱스: `./run.sh setup` (= `python -m scripts.collect_data`, `python -m scripts.collect_substances`, `python -m scripts.build_index`) → `data/laws`, `data/substances`, `index/` 생성 확인 ✅ 2026-11-12
2. API: `./run.sh serve` 후 `curl -X POST localhost:8000/query -H "Content-Type: application/json" -d '{"question":"..."}'` → 응답 필드가 [API Spec.md](API%20Spec.md)와 같은지 확인 ✅
3. 승인 흐름: 개정 질문 → "승인 대기 REQ-x" → `{"question": "승인 REQ-x"}` → 확정 초안 반환 ✅
4. 화면: 브라우저 `http://localhost:8000/` → 탭 4개 동작 (실제 브라우저 확인은 사용자)
5. LangSmith: `mini-pjt` 프로젝트에서 `msds-query` run 확인 ✅
6. 평가: `python -m evaluation.run_eval --round 1` ✅(18/20) / `--round 2` ⏳(토큰 한도)
7. 클린 환경: `docker build -t msds-agent . && docker run -p 8000:8000 --env-file ../.env msds-agent` ⏳(이 PC에 Docker 없음)

## 외부 서비스·키 (모두 준비 완료, 2026-11-11 실제 호출로 확인)

키는 모두 상위 `sds-ax-practice/.env`에 있고 커밋하지 않습니다.

| 서비스 | 환경 변수 | 확인 결과 |
|---|---|---|
| AWS Bedrock | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`(`us-east-1`), `BEDROCK_MODEL_ID` | LLM `us.anthropic.claude-sonnet-4-6` → 2026-11-12부터 `global.anthropic.claude-sonnet-4-6`, 임베딩 `amazon.titan-embed-text-v2:0`(1024차원) 호출 성공. **채팅 모델은 계정 일일 토큰 한도(Too many tokens per day)에 자주 걸림** |
| LangSmith | `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`(`mini-pjt`) | 인증 성공 |
| 국가법령정보센터 Open API | `LAW_API_OC` | `lawSearch.do` 호출 성공 |
| 공공데이터포털 (안전보건공단 MSDS) | `DATA_GO_KR_API_KEY` | 2026-11-12 키 교체 후 `getChemList001`(`searchCnd=1`이 CAS 검색), `getChemDetail021`(2번), `getChemDetail151`(15번) 호출 성공 |

### Bedrock 모델 접근
- 호출 성공: `global.anthropic.claude-sonnet-4-6`(2026-11-12부터 사용 중), `us.anthropic.claude-sonnet-4-6`(1차 평가 때 사용), `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
- 권한 거부: Claude 5·5.5 계열, `claude-opus-4-5`. `claude-haiku-4-5`는 확인 시 요청 한도 초과(Throttling)라 판단 보류

### 국가법령정보센터
- 화학물질관리법 검색 결과: 현행 법령 일련번호 285367, 시행 2026-10-08

### 안전보건공단 MSDS API (데이터셋 15157612)
- End Point `https://apis.data.go.kr/B552468/msdschem1`, 응답 XML
- 오퍼레이션 이름에 게이트웨이 접미사가 붙음: 목록 `getChemList001`(`searchWrd`, `searchCnd`=0 국문명, `numOfRows`, `pageNo`), 상세 `getChemDetail011`~`getChemDetail161`(MSDS 1~16번 항목, `chemId` 필수). 예전 주소 `msds.kosha.or.kr/openapi/service/msdschem/chemlist`, `getChemList`는 동작하지 않음
- 확인 예: 톨루엔 `chemId=001032`(CAS 108-88-3). 15번 상세에서 화학물질관리법 규제가 **"사고대비물질"만** 나오고 유독물질 표기는 없음 → U-01 판단과 일치

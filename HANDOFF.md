# 진행 현황과 다음 작업 (MSDS 개정 지원 에이전트)

> 이 문서는 작업 인계용입니다. **CLAUDE.md의 규칙이 이 문서보다 우선합니다.** 충돌하면 CLAUDE.md를 따릅니다.

- 마지막 갱신: 2026-11-11

## 저장소 상태

| 항목 | 내용 |
|---|---|
| 원격 저장소 | `origin` = https://github.com/dongyiya/mini-pjt.git |
| 브랜치 | 작업은 `feat/msds-agent`에서 하고, 단계가 끝나면 `master`에 fast-forward로 반영해 둘 다 push |
| 최신 커밋 | `a3e6705` 계획 보강 (`master`·`feat/msds-agent` 동일) |
| 커밋 이력 | `0574139` 1일차: 서비스 스펙, 평가셋, 데이터·도구 뼈대 → `a3e6705` 계획 보강: 데이터·도구 범위, 일정·검증 절차, 법령 근거 규칙 |
| Git 설정 | 이 저장소에만 `user.name=dongyiya`, `user.email=dongyiya@empal.com` |
| 커밋 제외 | `.archify/`(주제 검토 페이지), `index/`, `*.sqlite` (`.gitignore`). `.env`는 상위 폴더에 있어 저장소 밖 |

## 확정된 결정

| 항목 | 결정 |
|---|---|
| 주제 | 규제·배합 변경 시 MSDS 개정 필요 여부를 판정하고 개정 초안을 만드는 에이전트 |
| 대상 MSDS | 가상 제품 6개(`data/msds/products.json`) + 안전보건공단 공개 단일물질 MSDS 15종 안팎 (`data/substances/*.json` 스냅샷: CAS, GHS 분류, 15번 규제현황. 톨루엔·벤젠·포름알데히드·메탄올 등 가상 제품 성분 우선) |
| 법 범위 | 산업안전보건법(법·시행령·시행규칙·MSDS 고시) + 화학물질관리법. 수집 목표 조문: 산안법 제110~116조, 시행규칙 제156~170조, MSDS 고시 주요 조항, 화관법 정의·유해화학물질 조항 (현재 `data/laws`에는 산안법 제110·111·114조, 시행규칙 제156·159조, 화관법 제2조만 있음). 조문을 늘리면 평가셋도 그에 맞춰 보강 |
| LLM | AWS Bedrock `us.anthropic.claude-sonnet-4-6` (환경변수 `BEDROCK_MODEL_ID`, 상위 `.env`에 설정됨) |
| 임베딩 | Bedrock Titan Text Embeddings v2 (예정) |
| 트레이스 | LangSmith |
| Python·개발 도구 | **기존에 설치된 환경을 사용**: 상위 폴더의 `.venv`(Python 3.14.8). 새 가상환경·`pyproject.toml`·uv 잠금 파일은 만들지 않음 (2026-11-11 결정) |
| 환경 변수 | **기존 상위 폴더 `.env`를 사용** (`sds-ax-practice/.env`). 프로젝트에 새 `.env`를 만들지 않음 |
| Docker | 베이스 이미지 `python:3.14-slim` (로컬 `.venv`와 버전을 맞춤). 설치 문제가 생기면 로컬과 Docker 버전을 함께 바꿈 |
| 평가 정답 | 사용자가 도메인 경험이 거의 없으므로 **공개 원문에 적힌 사실**로만 작성 |

## 완료된 것 (1일차 범위)

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
- 산안법 조문은 국가법령정보센터 기본 화면의 **2027. 4. 28. 시행 판**입니다. 현재 시행 판과 제110·111·114조 문구가 같은지 확인합니다.
- U-01처럼 15번(법적 규제현황)만 바뀐 경우를 "개정 검토 필요, 시행규칙 제159조제1항 재제출 대상 아님"으로 판정합니다. 조문 문구를 그대로 적용한 것이며 실무 해석은 확인이 필요합니다.

## 실행 방법 (현재)

```bash
python -m src.tools                      # U-01 영향 판정 출력
python -m src.retriever                  # 검색 예시
python -m src.pipeline "U-02 반영하려면?"   # API 모양 응답 출력
```
Windows에서 한글이 깨지면 먼저 `set PYTHONIOENCODING=utf-8`(cmd) 또는 `$env:PYTHONIOENCODING="utf-8"`(PowerShell)을 실행합니다.

## 아키텍처 목표 (LangGraph)

```
POST /query → input_guard → supervisor ─┬─ regulation_agent  (법령 RAG + 법령 API)
                                        ├─ impact_agent      (MSDS DB + 물질 정보 + 분류 계산)
                                        └─ revision_agent    (개정 초안 → interrupt 승인)
                         → output_guard → 응답(answer, contexts, trace)
```
- HITL은 **엔드포인트를 추가하지 않고** 같은 `/query`로 처리합니다. 초안이 나오면 answer에 "승인 대기 REQ-xxxx"를 돌려주고, `{"question": "승인 REQ-xxxx"}` 또는 `"반려 REQ-xxxx 사유"`로 재개합니다(SqliteSaver, thread_id=REQ-xxxx).
- 모든 노드는 응답 `trace`에 `{step, input, output}`를 쌓습니다. LangSmith에도 같은 run이 기록됩니다. 평가에서 `expected_tools`는 이 trace에 남은 도구 호출로 확인합니다.

## 패턴 → 구현 위치 (목표 10개)

| # | 패턴 | 위치 |
|---|---|---|
| 1 | LCEL 구조화 출력 (필수) | `src/schemas.py` `RevisionJudgment{revision_needed, sections, reasons, legal_basis, draft}`. `legal_basis`는 근거 조문의 doc_id 목록(예: `law:산안법시행규칙:159`) |
| 2 | ReAct | 서브 에이전트마다 `create_react_agent`(bind_tools)로 생성 |
| 3 | RAG (필수) | BM25(kiwipiepy) + FAISS(Titan v2) 앙상블, 물질명↔CAS 쿼리 확장, 리랭킹(Bedrock Rerank를 쓸 수 있으면 사용, 안 되면 LLM 리랭크) |
| 4 | 도구 다중 | `src/tools.py` 기존 7개 + 추가 예정 `search_law`(법령 검색을 도구로 감쌈), `get_substance(cas)`(단일물질 MSDS 조회), `classify_mixture`(GHS 혼합물 분류 계산) |
| 5 | MCP | `src/mcp_server.py`로 MSDS DB 조회를 노출하고, 에이전트는 MCP 클라이언트로 호출 |
| 6 | 가드레일 | `src/guardrails.py` (현재 `pipeline.py`의 정규식을 옮겨 확장): 영업비밀 성분명·함유량 마스킹, 담당자 연락처 마스킹, 프롬프트 인젝션·범위 밖 질문 차단 |
| 7 | HITL | revision_agent `interrupt()` |
| 8 | 미들웨어 | API 재시도(tenacity), 긴 조문 요약 |
| 9 | Supervisor | `src/agent.py` |
| 11 | Trace (필수) | LangSmith + 응답 `trace` |
| 12 | 평가 (필수) | `evaluation/run_eval.py` RAGAS 4지표 + LLM-as-Judge |

10번(장기 메모리)은 시간이 남으면 제품 목록과 이전 판정 이력을 LangGraph Store에 저장하는 방식으로 추가합니다.

## 다음 작업 (2일차~)

1. 의존성 정리: 실제로 쓰는 패키지만 `requirements.txt`에 적고 기존 `.venv`(Python 3.14)에 설치합니다. 필요한 환경 변수 이름은 README에 정리합니다. 3.14에서 설치가 안 되는 패키지가 나오면 그때 대안을 정합니다. (`pyproject.toml`·uv·`.env.example`은 만들지 않기로 결정)
2. 데이터 보강: `scripts/collect_data.py`(국가법령정보센터·안전보건공단 API로 법령 조문과 단일물질 MSDS를 수집해 `data/`에 스냅샷 저장, 키가 없거나 호출이 실패하면 저장된 스냅샷 사용), `scripts/build_index.py`(BM25·FAISS 검색 인덱스 생성)
3. `src/config.py`(모델 ID·리전·상위 `.env` 경로·데이터·인덱스 경로를 한곳에서 읽음), `src/llm.py`(ChatBedrockConverse), `src/schemas.py`
4. 검색 교체: BM25 + FAISS 앙상블, 1순위 정확도 개선
5. `src/guardrails.py`, `src/agent.py`(Supervisor + ReAct + HITL), `src/api.py`(FastAPI `POST /query`)
6. `src/mcp_server.py`, LangSmith 연결
7. `evaluation/run_eval.py` → round1 보고서 → 개선 → round2 보고서
8. `README.md`, `Dockerfile`, `run.sh` 채우기

## 남은 일정과 완료 기준

1일차의 환경 준비(키·모델·원격 저장소), 서비스 스펙, 평가셋, 데이터·도구 뼈대는 끝났습니다. 남은 1일차 항목은 2일차 앞부분에 붙였습니다.

| 날 | 할 일 | 완료 기준 |
|---|---|---|
| 2일차 | 데이터 보강(법 조문 확대, 단일물질 15종), 인덱스, LLM·구조화 출력, `POST /query`, 도구, ReAct, Supervisor, 가드레일, HITL 승인 흐름 | ① 사실 질문 5개에 근거 조문(`contexts`)이 담긴 답 ② "U-01 영향 제품?"에 도구 2개 이상 결합 ③ 승인 대기 → 승인 재개 동작 |
| 3일차 | MCP, LangSmith 연결, 1차 평가, 개선(검색·프롬프트·가드레일), 2차 평가, 보고서·README·Dockerfile | `round1_report.md`·`round2_report.md`에 통과율, RAGAS 지표, 패턴 적용 위치 기록 |

## 검증 절차

`mini-pjt` 폴더에서 기존 `.venv`의 Python으로 실행합니다. Windows Git Bash 기준입니다.

1. 데이터·인덱스: `../.venv/Scripts/python scripts/collect_data.py && ../.venv/Scripts/python scripts/build_index.py` → 인덱스 폴더가 생성되는지 확인
2. API: `../.venv/Scripts/python -m uvicorn src.api:app` 실행 후
   `curl -X POST localhost:8000/query -H "Content-Type: application/json" -d '{"question":"..."}'` → 응답 필드 `answer`, `contexts`, `trace`의 이름과 구조가 [API Spec.md](API%20Spec.md)와 같은지 확인
3. 승인 흐름: 개정 질문 → "승인 대기 REQ-x" → `{"question": "승인 REQ-x"}` → 확정 초안 반환
4. LangSmith: `mini-pjt` 프로젝트에서 run과 step이 보이는지 확인
5. 평가: `../.venv/Scripts/python evaluation/run_eval.py --round 1` → 통과율과 RAGAS 지표 출력, 보고서 생성
6. 클린 환경: `docker build -t msds-agent . && docker run -p 8000:8000 --env-file ../.env msds-agent` (`.env`는 상위 폴더에 있음)

## 외부 서비스·키 (모두 준비 완료, 2026-11-11 실제 호출로 확인)

키는 모두 상위 `sds-ax-practice/.env`에 있고 커밋하지 않습니다.

| 서비스 | 환경 변수 | 확인 결과 |
|---|---|---|
| AWS Bedrock | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`(`us-east-1`), `BEDROCK_MODEL_ID` | LLM `us.anthropic.claude-sonnet-4-6`, 임베딩 `amazon.titan-embed-text-v2:0`(1024차원) 호출 성공 |
| LangSmith | `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`(`mini-pjt`) | 인증 성공 |
| 국가법령정보센터 Open API | `LAW_API_OC` | `lawSearch.do` 호출 성공 |
| 공공데이터포털 (안전보건공단 MSDS) | `DATA_GO_KR_API_KEY` | `getChemList001`, `getChemDetail151` 호출 성공 |

### Bedrock 모델 접근
- 호출 성공: `us.anthropic.claude-sonnet-4-6`(사용 중), `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
- 권한 거부: Claude 5·5.5 계열, `claude-opus-4-5`. `claude-haiku-4-5`는 확인 시 요청 한도 초과(Throttling)라 판단 보류

### 국가법령정보센터
- 화학물질관리법 검색 결과: 현행 법령 일련번호 285367, 시행 2026-10-08

### 안전보건공단 MSDS API (데이터셋 15157612)
- End Point `https://apis.data.go.kr/B552468/msdschem1`, 응답 XML
- 오퍼레이션 이름에 게이트웨이 접미사가 붙음: 목록 `getChemList001`(`searchWrd`, `searchCnd`=0 국문명, `numOfRows`, `pageNo`), 상세 `getChemDetail011`~`getChemDetail161`(MSDS 1~16번 항목, `chemId` 필수). 예전 주소 `msds.kosha.or.kr/openapi/service/msdschem/chemlist`, `getChemList`는 동작하지 않음
- 확인 예: 톨루엔 `chemId=001032`(CAS 108-88-3). 15번 상세에서 화학물질관리법 규제가 **"사고대비물질"만** 나오고 유독물질 표기는 없음 → U-01 판단과 일치

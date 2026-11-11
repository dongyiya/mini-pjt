# 진행 현황과 다음 작업 (MSDS 개정 지원 에이전트)

> 이 문서는 작업 인계용입니다. **CLAUDE.md의 규칙이 이 문서보다 우선합니다.** 충돌하면 CLAUDE.md를 따릅니다.

- 브랜치: `feat/msds-agent` (아직 커밋 없음)
- 마지막 갱신: 2026-11-11

## 브랜치·커밋 인계

- 원격 저장소: `origin` = https://github.com/dongyiya/mini-pjt.git (2026-11-11 연결, 아직 push 안 함. 원격은 빈 저장소)
- 작업 브랜치는 `feat/msds-agent`이며 이미 체크아웃되어 있습니다. 첫 커밋 전이라 `master`에는 아무 기록이 없습니다.
- 1일차 파일은 **스테이징만 된 상태**입니다. 커밋은 아직 하지 않았습니다.
- `.archify/`(주제 추천·설명 페이지)는 프로젝트 산출물이 아니라서 스테이징하지 않았습니다. 커밋에 넣지 않습니다.
- 이 PC에는 Git 사용자 이름·이메일이 없어 커밋이 실패했습니다. 첫 커밋 전에 이 저장소에만 설정합니다.
  ```bash
  git config user.name "이름"
  git config user.email "이메일"
  ```
- 첫 커밋 메시지 초안 (1일차 작업 요약):
  ```
  MSDS 개정 지원 에이전트 1일차: 서비스 스펙, 평가셋, 데이터·도구 뼈대

  - SERVICE.md: 사용자·문제·가치, 확장, 도구·데이터, 가드레일, 성공 기준
  - evaluation/test_queries.csv: 인-아웃 세트 20건 (positive 8, negative 4, edge 5, guardrail 3)
  - data/laws: 산안법·시행규칙·화관법 조문 원문 (국가법령정보센터)
  - data/msds, data/regulation_updates.json: 가상 제품 MSDS 6개, 변경 사건 4건
  - src/tools.py, retriever.py, pipeline.py: 도구 7개, 키워드 검색 스케치, LLM 없는 최소 파이프라인
  - HANDOFF.md: 진행 현황과 다음 작업 (CLAUDE.md 규칙 우선)
  ```
- VS Code에서 추가 작업을 한 뒤 1일차 파일과 함께 커밋해도 되고, 1일차 파일만 먼저 커밋해도 됩니다.

## 확정된 결정

| 항목 | 결정 |
|---|---|
| 주제 | 규제·배합 변경 시 MSDS 개정 필요 여부를 판정하고 개정 초안을 만드는 에이전트 |
| 대상 MSDS | 가상 제품 6개(`data/msds/products.json`) + 안전보건공단 공개 MSDS(추가 예정) |
| 법 범위 | 산업안전보건법(법·시행규칙·MSDS 고시) + 화학물질관리법 |
| LLM | AWS Bedrock `us.anthropic.claude-sonnet-4-6` (환경변수 `BEDROCK_MODEL_ID`, 상위 `.env`에 설정됨) |
| 임베딩 | Bedrock Titan Text Embeddings v2 (예정) |
| 트레이스 | LangSmith |
| Python·개발 도구 | **기존에 설치된 환경을 사용**: 상위 폴더의 `.venv`(Python 3.14.8). 새 가상환경·`pyproject.toml`·uv 잠금 파일은 만들지 않음 (2026-11-11 결정) |
| 환경 변수 | **기존 상위 폴더 `.env`를 사용** (`sds-ax-practice/.env`). 프로젝트에 새 `.env`를 만들지 않음 |
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

## 패턴 → 구현 위치 (목표 10개)

| # | 패턴 | 위치 |
|---|---|---|
| 1 | LCEL 구조화 출력 (필수) | `src/schemas.py` `RevisionJudgment{revision_needed, sections, reasons, legal_basis, draft}` |
| 2 | ReAct | 서브 에이전트마다 bind_tools |
| 3 | RAG (필수) | BM25(kiwipiepy) + FAISS(Titan v2) 앙상블, 물질명↔CAS 쿼리 확장, 리랭킹 |
| 4 | 도구 다중 | `src/tools.py` (+ `classify_mixture` 추가 예정) |
| 5 | MCP | `src/mcp_server.py`로 MSDS DB 노출 |
| 6 | 가드레일 | `src/guardrails.py` (현재 `pipeline.py`의 정규식을 옮겨 확장) |
| 7 | HITL | revision_agent `interrupt()` |
| 8 | 미들웨어 | API 재시도(tenacity), 긴 조문 요약 |
| 9 | Supervisor | `src/agent.py` |
| 11 | Trace (필수) | LangSmith + 응답 `trace` |
| 12 | 평가 (필수) | `evaluation/run_eval.py` RAGAS 4지표 + LLM-as-Judge |

10번(장기 메모리)은 시간이 남으면 추가합니다.

## 다음 작업 (2일차~)

1. ~~`pyproject.toml`(uv, Python 3.12) + `requirements.txt` export, `.env.example`~~ → 기존 `.venv`·`.env`를 쓰기로 해서 취소. 대신 실제로 쓰는 패키지만 `requirements.txt`에 적고, 필요한 환경 변수 이름을 README에 정리합니다. 3.14에서 설치가 안 되는 패키지가 나오면 그때 대안을 정합니다.
2. `src/llm.py`(ChatBedrockConverse), `src/schemas.py`
3. 검색 교체: BM25 + FAISS 앙상블, 1순위 정확도 개선
4. `src/guardrails.py`, `src/agent.py`(Supervisor + ReAct + HITL), `src/api.py`(FastAPI `POST /query`)
5. `src/mcp_server.py`, LangSmith 연결
6. `evaluation/run_eval.py` → round1 보고서 → 개선 → round2 보고서
7. `README.md`, `Dockerfile`, `run.sh` 채우기

## 사용자가 준비할 것
- ~~AWS 자격 증명과 Bedrock 모델 접근 승인(Claude 계열 + Titan Embed v2, 리전)~~ → 상위 `.env`에 있음, 2026-11-11 실제 호출로 확인
  - 리전 `us-east-1`. 호출 성공: `us.anthropic.claude-sonnet-4-6`, `us.anthropic.claude-sonnet-4-5-20250929-v1:0`, `amazon.titan-embed-text-v2:0`(1024차원)
  - 권한 거부: Claude 5·5.5 계열, `claude-opus-4-5`. `claude-haiku-4-5`는 확인 시 요청 한도 초과(Throttling)라 판단 보류
  - LLM은 `us.anthropic.claude-sonnet-4-6`으로 확정, 상위 `.env`에 `BEDROCK_MODEL_ID`로 추가함 (2026-11-11)
- ~~LangSmith API 키~~ → 상위 `.env`에 있음, 인증 확인. `LANGSMITH_PROJECT`를 `day4-practice`에서 `mini-pjt`로 변경함 (2026-11-11)
- (선택) ~~국가법령정보센터 Open API OC~~ → 상위 `.env`에 `LAW_API_OC`로 추가, 2026-11-11 `lawSearch.do` 호출 성공(화학물질관리법 검색, 현행 법령 일련번호 285367 · 시행 2026-10-08)
- (선택) 공공데이터포털 서비스키: 2026-11-11 새 계정 키로 `.env`의 `DATA_GO_KR_API_KEY` 교체. "한국산업안전보건공단_물질안전보건자료 조회 서비스"(데이터셋 15157612) 호출 성공
  - End Point `https://apis.data.go.kr/B552468/msdschem1`, 응답 XML
  - 오퍼레이션 이름에 게이트웨이 접미사가 붙음: 목록 `getChemList001`(`searchWrd`, `searchCnd`=0 국문명, `numOfRows`, `pageNo`), 상세 `getChemDetail011`~`getChemDetail161`(MSDS 1~16번 항목, `chemId` 필수). 예전 주소 `msds.kosha.or.kr/openapi/service/msdschem/chemlist`, `getChemList`는 동작하지 않음
  - 확인 예: 톨루엔 `chemId=001032`(CAS 108-88-3). 15번 상세에서 화학물질관리법 규제가 **"사고대비물질"만** 나오고 유독물질 표기는 없음 → U-01 판단과 일치
- 키는 `.env`에만 넣고 커밋하지 않습니다(`.gitignore`에 등록됨).

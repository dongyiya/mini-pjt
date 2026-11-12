# 인계 문서 (MSDS 개정 지원 에이전트)

> 작업 인계용 현재 상태 요약입니다. **CLAUDE.md의 규칙이 이 문서보다 우선합니다.**
> 중간 진행 기록은 정리했습니다. 이전 내용은 git 이력(`git log -p HANDOFF.md`)에서 볼 수 있습니다.

- 마지막 갱신: 2026-11-12
- **현재 상태**: 구현·평가 완료. 2차 평가 **19/20 통과**(필수 4/4)를 최종 결과로 확정. `src/`는 도메인별 폴더 구조. 원격 저장소와 동기화됨.

## 1. 저장소

| 항목 | 내용 |
|---|---|
| 원격 | `origin` = https://github.com/dongyiya/mini-pjt.git, 브랜치 `master` |
| 최신 커밋 | `97ab1fd` src/ 도메인별 폴더 구조로 리팩토링 (push 완료) |
| 커밋 제외 | `.archify/`(다이어그램·검토 페이지), `index/`, `*.sqlite*`, `data/msds/history/`, `revision_log.json`. 키가 든 `.env`는 상위 폴더(저장소 밖) |

## 2. 확정된 결정

| 항목 | 결정 |
|---|---|
| 주제 | 규제·배합 변경 시 MSDS 개정·재제출 필요 여부를 판정하고 개정 초안을 만드는 에이전트 |
| 데이터 | 가상 제품 6개(`data/msds/products.json`, 원본 `products.baseline.json`), 변경 사건 U-01~U-04(`data/regulation_updates.json`, U-01만 실제 화관법 개정), 공단 공개 단일물질 11종(`data/substances/`) |
| 법령 범위 | 수집함: 산안법 제110~116조, 시행규칙 제156~170조, 화관법 제2조 (현행 판, `data/laws/<법령>@<시행일>.md`). 수집 안 함: 시행령, MSDS 고시, 화관법 세부 조항 |
| 시행일 기준 조문 선택 | 질문 기준일(질문 속 날짜, 없으면 오늘)에 시행 중인 판을 근거로 쓰고, 이후 판은 `[시행 예정 YYYY-MM-DD]`로 따로 표시. 예정 판 doc_id는 `law:…@YYYY-MM-DD` |
| 모델 | Bedrock **us-west-2** `us.anthropic.claude-sonnet-4-6`, 임베딩 `amazon.titan-embed-text-v2:0`. us-east-1은 일일 토큰 한도 문제로 변경 |
| 실행 환경 | 상위 폴더의 기존 `.venv`(Python 3.14)와 `.env`를 그대로 사용. 새 가상환경·`.env`를 만들지 않음 |
| HITL | 새 엔드포인트 없이 같은 `POST /query`에 "승인 REQ-xxxx" / "반려 REQ-xxxx 사유" |
| 법령 갱신 | 화면 '법령 가져오기' 버튼(= `/query`에 "법령 갱신")으로 **수동 실행만**. 자동 주기 수집 없음 |
| 승인 → MSDS 반영 | **시험 기능**. 승인하면 `products.json`에 반영(개정판 +1). '확인 필요' 항목은 담당자가 대체 표기를 입력해야 승인됨 |
| 평가 전 원복 | 평가는 항상 원래 데모 데이터로 실행. `run_eval.py`가 시작할 때 자동 원복, 수동은 `./run.sh reset-msds`. 바뀐 `products.json`은 커밋하지 않음 |
| 최종 평가 | 2차 결과를 최종으로 함. 3차 평가는 실행하지 않음 |
| 단위 테스트 | 사용자 지시로 **실행하지 않음**(다시 요청하기 전까지). 마지막 실행 때 133개 통과(리팩토링 전) |

## 3. 구조

```
화면(GET /, 탭 4개) ─┐
curl·PowerShell    ─┴→ POST /query → input_guard ─(차단)──────────────┐
                                        └→ supervisor (기준일 + Route) │
                                             ├→ regulation_agent ─────┤
                                             ├→ impact_agent ─────────┤
                                             └→ revision_agent → approval(interrupt, 승인 대기)
                                                                       └→ output_guard → {answer, contexts, trace}
```

| 폴더 | 역할 |
|---|---|
| `src/api/` | FastAPI(`app.py`), API Spec 스키마, 화면 `static/index.html` |
| `src/agents/` | 프롬프트, LLM 라우터·ReAct·판정(`brains.py`), 구조화 출력, 판정 사후 검증 |
| `src/workflows/` | LangGraph 그래프·`run_query`(`graph.py`), 도구 결과 → 근거 변환 |
| `src/memory/` | SqliteSaver 체크포인터, REQ 번호 |
| `src/tools/` | 도구 11개(`msds_tools.py`), MCP 서버·클라이언트 |
| `src/regulation/` | RAG 검색(`retriever.py`), 법령 갱신(`refresh.py`) |
| `src/revision/` | 변경 미리보기, 승인 후 MSDS 반영·원복 |
| `src/guardrails/` | 입력 차단, 출력 마스킹 |
| `src/shared/` | 설정, Bedrock 클라이언트, 기준일 추출, trace 단계 |

폴더 배치 규칙은 [CLAUDE.md](CLAUDE.md) "소스 폴더 구조" 절, 다이어그램은 `.archify/`(코드 기준 아키텍처, 기능 아키텍처)에 있습니다.

### 빌드 패턴 (11개 적용, 10번 장기 메모리 제외)

| # | 패턴 | 위치 |
|---|---|---|
| 1 | LCEL 구조화 출력 (필수) | `src/agents/schemas.py` Route·RevisionJudgment, `src/agents/brains.py` 라우터·판정 체인 |
| 2 | ReAct | `src/agents/brains.py` 서브 에이전트 3개 `create_agent` |
| 3 | RAG (필수) | `src/regulation/retriever.py` BM25(kiwipiepy)+FAISS RRF, 쿼리 확장, LLM 리랭크, 시행일 판 선택 |
| 4 | 도구 다중 | `src/tools/msds_tools.py` 11개 |
| 5 | MCP | `src/tools/mcp_server.py`(MSDS DB 도구 6개) + `mcp_client.py` |
| 6 | 가드레일 | `src/guardrails/guard.py` |
| 7 | HITL | `src/workflows/graph.py` approval `interrupt()` + `src/memory/checkpointer.py` |
| 8 | 미들웨어 | `src/shared/llm.py` `with_retry`, 수집 스크립트 재시도, 도구 결과 마스킹 |
| 9 | Supervisor | `src/workflows/graph.py` supervisor 노드 |
| 11 | Trace (필수) | 응답 `trace` + LangSmith `mini-pjt` |
| 12 | 평가 (필수) | `evaluation/run_eval.py` LLM-as-Judge + RAGAS |

## 4. 평가 결과 (최종 = 2차)

| 지표 | 1차 | 2차 | 목표 |
|---|---|---|---|
| 통과율 | 18/20 | **19/20** | 16 이상 ✅ |
| 필수(guardrail 3 + 9번) | 4/4 | 4/4 | 전부 ✅ |
| faithfulness | 0.77 | 0.78 | 0.85 ❌ |
| context_recall | 0.90 | 0.87 | 0.80 ✅ |
| 평균 응답 | 10.0초 | 8.6초 | 15초 |

- 2차 실패는 12번 1건(묻지 않은 다른 제품의 벤젠 함유량을 덧붙임). 자세한 분석은 [evaluation/round2_report.md](evaluation/round2_report.md).
- 2차 이후 넣은 개선(12번 대응 프롬프트, 근거 문장형, `rule:`·`policy:service` 근거)은 **평가로 검증하지 않음**.
- 리팩토링 후 실제 질문 2건(법령 질문, 개정 판정 → 승인 대기)으로 동작 확인함.

## 5. 실행 방법

`mini-pjt` 폴더, Git Bash 기준. 자세한 것은 [README.md](README.md), 사용자용은 [docs/사용자_매뉴얼.md](docs/사용자_매뉴얼.md).

```bash
./run.sh setup        # 법령·물질 수집 + 검색 인덱스
./run.sh serve        # 화면 http://localhost:8000/ , API POST /query, 테스트 화면 /docs
./run.sh reset-msds   # 제품 MSDS를 원래 데모 데이터로 되돌림
../.venv/Scripts/python -m scripts.try_agent "질문"       # 서버 없이 질문 1건 (토큰 사용)
../.venv/Scripts/python -m evaluation.run_eval --round 3  # 평가 (토큰 많이 사용)
```

Windows에서 한글이 깨지면 `$env:PYTHONIOENCODING="utf-8"`(PowerShell)을 먼저 실행합니다.

## 6. 외부 서비스

키는 모두 상위 `sds-ax-practice/.env`에 있고 커밋하지 않습니다.

| 서비스 | 환경 변수 | 비고 |
|---|---|---|
| AWS Bedrock | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `BEDROCK_MODEL_ID` | 채팅 모델은 계정 일일 토큰 한도("Too many tokens per day")에 걸릴 수 있음. 평가 스크립트는 한도 초과 시 바로 멈춤 |
| LangSmith | `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`(`mini-pjt`) | MCP 경유 도구 호출은 별도 run으로 기록됨 |
| 국가법령정보센터 | `LAW_API_OC` | `target=eflaw`로 현행·시행 예정 판 수집 |
| 안전보건공단 MSDS (공공데이터포털 15157612) | `DATA_GO_KR_API_KEY` | End Point `https://apis.data.go.kr/B552468/msdschem1`. 목록 `getChemList001`(`searchCnd=1` CAS 검색), 상세 `getChemDetail011`~`161` |

## 7. 알려진 한계·확인 필요

- 15번(법적 규제현황)만 바뀐 경우를 "개정 검토 필요, 시행규칙 제159조제1항 재제출 대상 아님"으로 판정합니다. 조문 문구를 그대로 적용한 것이라 실무 해석은 확인이 필요합니다.
- 시행령·MSDS 고시를 수집하지 않아 혼합물 최종 분류는 계산하지 않고 '확인 필요' 검토 목록만 냅니다.
- `MSDS_Revision_SOP.md`의 조문 번호·기한은 원문과 대조해 [원문 확인] / [확인 필요]로 표시해 두었습니다.
- 화면은 실제 브라우저 자동 확인 없이 점검했습니다. 승인함 목록은 브라우저에 저장됩니다(승인 대기 상태 자체는 서버 체크포인트에 있음).
- Docker 이미지 빌드는 이 PC에 Docker가 없어 확인하지 못했습니다.
- 사내 변경 사건(U-02~U-04)은 출처 문서·외부 연계 없이 직접 작성한 가상 데이터입니다. 판정은 "이 변경이 사실이라면"을 전제로 한 시연이며, 변경 사건 파일은 프로그램이 읽기만 합니다(새 사건은 파일을 직접 고쳐 추가).

## 8. 남은 일 (모두 선택)

| 항목 | 방법 |
|---|---|
| 2차 이후 개선 효과 검증 (3차 평가) | `python -m evaluation.run_eval --round 3` (시작 시 MSDS 자동 원복) |
| 리팩토링 후 단위 테스트 | `../.venv/Scripts/python -m pytest` — 사용자가 다시 요청할 때만 |
| Docker 빌드 확인 | `docker build -t msds-agent . && docker run -p 8000:8000 --env-file ../.env msds-agent` |
| 시행령·MSDS 고시 수집 | `scripts/collect_data.py` TARGETS 확장 → 평가셋 보강 |
| 시행일 기준 조문 선택용 edge 평가 질문 | 기준일 지정 질문, 시행 예정 조문 표시 질문 추가 (정답은 수집 원문 시행일로만) |
| 장기 메모리(패턴 10) | 제품 목록·이전 판정 이력을 LangGraph Store에 저장 |
| 사내 변경 사건 입력 경로 (2026-11-12 추가) | 지금 U-02~U-04(배합·유해성·제품명 변경)는 `data/regulation_updates.json`에 직접 적은 가상 데이터(`real: false`)이고, 외부 연계·원천 문서가 없음. 운영하려면 ① 배합 관리·ERP·시험(LIMS) 시스템에서 변경 내역을 받아 오는 연계, 또는 ② 화면에서 변경 사건(제품·항목·전/후 값)과 근거 문서(배합표·시험성적서·제품명 변경 품의서)를 등록하는 기능이 필요. 등록 시 `changes` 형식 검증과 근거 문서 첨부를 필수로 하고, 등록 이력을 남김. API Spec 밖의 새 엔드포인트가 필요하면 사용자 확인 |

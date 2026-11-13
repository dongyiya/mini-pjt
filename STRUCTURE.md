# 프로젝트 구조

mini-pjt의 폴더 구조, `src/` 소스 폴더 구조, 파일 배치 규칙입니다. (2026-11-12 CLAUDE.md에서 분리)
[CLAUDE.md](CLAUDE.md)가 이 파일을 불러오므로, 아래 **파일 배치 규칙**은 CLAUDE.md 규칙과 같은 효력을 가집니다.

## 1. 폴더 구조

```
src/          소스코드 — 도메인(기능)별 폴더. 역할과 배치 규칙은 아래 "2. 소스 폴더 구조"
scripts/      데이터 수집(collect_data.py: 법령, collect_substances.py: 물질)·인덱스 생성(build_index.py)
data/         사용한 문서·데이터 (laws/<법령>@<시행일>.md, msds/, substances/, regulation_updates.json)
evaluation/   평가셋(test_queries.csv), 평가 스크립트(run_eval.py), 결과(results/, round1/round2_report.md)
tests/        단위 테스트
docs/         사용자 매뉴얼, spec/(src .py 파일별 프로그램 사양서, 도메인 폴더 구조 동일)
index/        검색 인덱스 (build_index.py가 생성, 커밋 제외)
portal/       게시판형 앱 포탈 — zip 업로드 → 로컬 Coolify(WSL2) 배포 (2026-11-13 추가, MSDS 앱과 독립된 배포 도구. 설치는 portal/CLAUDE.md)
SERVICE.md    서비스 스펙
README.md     프로젝트 설명
HANDOFF.md    진행 현황과 다음 작업
STRUCTURE.md  프로젝트 구조 (이 파일)
CLAUDE.md     Claude 작업 규칙
```

## 2. 소스 폴더 구조 (`src/`, 2026-11-12 도메인별 리팩토링)

모든 소스 코드는 `src/` 안에 둡니다. 폴더는 기술 역할(utils, models 등)이 아니라 **에이전트의 도메인(기능) 단위**로 나눕니다. 파일별 상세는 [docs/spec/](docs/spec/README.md) 사양서를 봅니다.

```
src/
├── api/            HTTP 진입점 — POST /query, GET /, GET /health
│   ├── app.py          FastAPI 앱 (실행: uvicorn src.api.app:app)
│   ├── schemas.py      API Spec 입출력 (QueryRequest, QueryResponse, Context, TraceStep) — 이름·구조 변경 금지
│   └── static/index.html  화면 4탭
├── agents/         Supervisor·서브 에이전트(regulation·impact·revision)
│   ├── prompts.py      COMMON_RULES, PROMPTS, ROUTER_PROMPT, JUDGE_PROMPT
│   ├── brains.py       LLM 라우터·ReAct·판정 체인(Brains, llm_brains), 에이전트별 도구 묶음(make_tools)
│   ├── judgment.py     판정 사후 검증(sanitize_judgment), 답변 문구(format_judgment)
│   └── schemas.py      LCEL 구조화 출력 (Route, ProductRevision, RevisionJudgment)
├── workflows/      LangGraph 그래프와 /query 처리 흐름
│   ├── graph.py        build_graph, run_query(승인 요청·승인/반려·법령 갱신 명령), AgentState
│   ├── evidence.py     도구 결과 → trace·contexts(근거) 변환
│   ├── evidence_text.py 근거 문장형 문구, 서비스 정책 근거(policy:service)
│   └── pipeline_v1.py  1일차 규칙 기반 파이프라인 (기준선 보관, API에서 쓰지 않음)
├── memory/         HITL 상태 저장
│   └── checkpointer.py SqliteSaver(checkpoints.sqlite), 승인 요청 번호 REQ-xxxx
├── tools/          에이전트 도메인 도구와 MCP
│   ├── msds_tools.py   도구 11개 (MSDS DB·변경 사건·재제출 규칙·법령 검색·물질·혼합물)
│   ├── mcp_server.py   FastMCP stdio 서버 (실행: python -m src.tools.mcp_server)
│   └── mcp_client.py   MCP 브리지 (실패 시 로컬 도구)
├── regulation/     법령 도메인 — RAG 검색과 법령 수동 갱신
│   ├── retriever.py    BM25+FAISS RRF, 쿼리 확장, LLM 리랭크, 시행일 판 선택
│   └── refresh.py      '법령 갱신' 명령: 수집 → 비교 → 재색인
├── revision/       MSDS 개정 도메인 — 변경 미리보기, 승인 후 반영, 중복 확인
│   ├── preview.py      변경 작업(op)·화면 데이터·승인 대기 목록
│   ├── msds_apply.py   승인 → 제품 MSDS 반영(시험 기능), 원복(reset_to_baseline)
│   └── dedupe.py       승인 요청 중복 확인(승인 대기 중·승인 반영된 같은 변경), 기존 중복 정리
├── guardrails/     입력 차단·출력 마스킹
│   └── guard.py        check_input, mask_output
└── shared/         여러 도메인이 함께 쓰는 것만
    ├── config.py       .env·경로·기준일(today)
    ├── llm.py          Bedrock 채팅·임베딩 클라이언트, with_retry
    ├── dates.py        질문 기준일 추출
    └── trace.py        trace 단계(step), 메시지 텍스트
```

## 3. 파일 배치 규칙

- **도메인 안에 함께 둡니다**: 한 도메인의 실행 로직, 프롬프트 템플릿, 입출력 스키마(타입)는 그 도메인 폴더에 둡니다. 예: 에이전트 프롬프트는 `agents/prompts.py`, 에이전트 구조화 출력은 `agents/schemas.py`, API 입출력은 `api/schemas.py`.
- **`shared/`는 좁게**: 두 개 이상의 도메인에서 쓰는 LLM 클라이언트 설정·환경 설정·범용 유틸만 둡니다. 한 도메인에서만 쓰면 그 도메인 폴더에 둡니다. `shared/`는 다른 `src` 도메인을 import 하지 않습니다.
- **의존 방향**: `api → workflows → agents·memory·revision → tools·guardrails → regulation → shared`. 위쪽 폴더는 아래쪽 어느 폴더든 import 할 수 있고, 아래쪽 폴더는 위쪽 폴더를 import 하지 않습니다(필요하면 함수 안 지연 import로 순환을 피하고, 이유를 주석으로 남깁니다). 예외: `regulation/refresh.py`는 법령 수집·색인을 위해 `scripts/collect_data.py`·`scripts/build_index.py`를 함수 안에서 불러옵니다.
- **새 기능 추가**: 새 도메인이면 `src/<도메인>/` 폴더와 `__init__.py`를 만들고 이 파일의 트리와 규칙을 함께 고칩니다. 기존 도메인에 속하면 그 폴더에 파일을 추가합니다. 어느 경우든 [docs/spec/](docs/spec/README.md)에 같은 양식으로 사양서를 추가합니다.
- **import 경로**: 항상 절대 경로 `from src.<도메인>.<모듈> import ...`로 씁니다. 같은 이름 충돌을 피하려고 `from src.tools import msds_tools as tools`, `from src.guardrails import guard as guardrails`처럼 별칭을 씁니다.
- **경로 계산**: 프로젝트 루트·데이터 경로는 `shared/config.py`의 `ROOT`, `DATA_DIR` 등을 씁니다. 파일 위치(`__file__`) 기준 계산을 새로 만들지 않습니다.
- **API Spec**: 엔드포인트와 응답 모양은 `api/` 폴더가 책임집니다. 다른 폴더는 `{answer, contexts, trace}` dict만 돌려줍니다.
- **폴더 밖 실행 진입점**: `scripts/`(데이터 수집·인덱스), `evaluation/`(평가), `tests/`(단위 테스트)는 `src/` 밖에 둡니다.

# CLAUDE.md

mini-pjt 프로젝트에서 Claude와 함께 작업할 때 지키는 규칙입니다.

## 프로젝트 개요

- 신규 프로젝트입니다. 에이전트 그래프 + 도메인 도구 + RAG 파이프라인으로 구성합니다.
- 서비스 스펙은 [SERVICE.md](SERVICE.md), 평가 기준은 [evaluation/test_queries.csv](evaluation/test_queries.csv)를 따릅니다.

## 폴더 구조

<!-- (기존 내용) 2026-11-12 도메인별 폴더 리팩토링 전
src/          소스코드 (agent.py: 에이전트 그래프, tools.py: 도메인 도구, retriever.py: RAG,
              api.py: FastAPI 서버, guardrails.py, mcp_server.py·mcp_client.py, law_refresh.py,
              revision_preview.py: 화면용 데이터, static/index.html: 화면)
-->
```
src/          소스코드 — 도메인(기능)별 폴더. 역할과 배치 규칙은 아래 "소스 폴더 구조" 절
scripts/      데이터 수집(collect_data.py: 법령, collect_substances.py: 물질)·인덱스 생성(build_index.py)
data/         사용한 문서·데이터 (laws/<법령>@<시행일>.md, msds/, substances/, regulation_updates.json)
evaluation/   평가셋(test_queries.csv), 평가 스크립트(run_eval.py), 결과(results/, round1/round2_report.md)
tests/        단위 테스트
docs/         사용자 매뉴얼
index/        검색 인덱스 (build_index.py가 생성, 커밋 제외)
SERVICE.md    서비스 스펙
README.md     프로젝트 설명
HANDOFF.md    진행 현황과 다음 작업
```

## 소스 폴더 구조 (`src/`, 2026-11-12 도메인별 리팩토링)

모든 소스 코드는 `src/` 안에 둡니다. 폴더는 기술 역할(utils, models 등)이 아니라 **에이전트의 도메인(기능) 단위**로 나눕니다.

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
│   ├── graph.py        build_graph, run_query, parse_decision, AgentState
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
├── revision/       MSDS 개정 도메인 — 변경 미리보기와 승인 후 반영
│   ├── preview.py      변경 작업(op)·화면 데이터·승인 대기 목록
│   └── msds_apply.py   승인 → 제품 MSDS 반영(시험 기능), 원복(reset_to_baseline)
├── guardrails/     입력 차단·출력 마스킹
│   └── guard.py        check_input, mask_output
└── shared/         여러 도메인이 함께 쓰는 것만
    ├── config.py       .env·경로·기준일(today)
    ├── llm.py          Bedrock 채팅·임베딩 클라이언트, with_retry
    ├── dates.py        질문 기준일 추출
    └── trace.py        trace 단계(step), 메시지 텍스트
```

### 파일 배치 규칙
- **도메인 안에 함께 둡니다**: 한 도메인의 실행 로직, 프롬프트 템플릿, 입출력 스키마(타입)는 그 도메인 폴더에 둡니다. 예: 에이전트 프롬프트는 `agents/prompts.py`, 에이전트 구조화 출력은 `agents/schemas.py`, API 입출력은 `api/schemas.py`.
- **`shared/`는 좁게**: 두 개 이상의 도메인에서 쓰는 LLM 클라이언트 설정·환경 설정·범용 유틸만 둡니다. 한 도메인에서만 쓰면 그 도메인 폴더에 둡니다. `shared/`는 다른 `src` 도메인을 import 하지 않습니다.
- **의존 방향**: `api → workflows → agents·memory·revision → tools·guardrails → regulation → shared`. 위쪽 폴더는 아래쪽 어느 폴더든 import 할 수 있고, 아래쪽 폴더는 위쪽 폴더를 import 하지 않습니다(필요하면 함수 안 지연 import로 순환을 피하고, 이유를 주석으로 남깁니다). 예외: `regulation/refresh.py`는 법령 수집·색인을 위해 `scripts/collect_data.py`·`scripts/build_index.py`를 함수 안에서 불러옵니다.
- **새 기능 추가**: 새 도메인이면 `src/<도메인>/` 폴더와 `__init__.py`를 만들고 이 절의 트리와 규칙을 함께 고칩니다. 기존 도메인에 속하면 그 폴더에 파일을 추가합니다.
- **import 경로**: 항상 절대 경로 `from src.<도메인>.<모듈> import ...`로 씁니다. 같은 이름 충돌을 피하려고 `from src.tools import msds_tools as tools`, `from src.guardrails import guard as guardrails`처럼 별칭을 씁니다.
- **경로 계산**: 프로젝트 루트·데이터 경로는 `shared/config.py`의 `ROOT`, `DATA_DIR` 등을 씁니다. 파일 위치(`__file__`) 기준 계산을 새로 만들지 않습니다.
- **API Spec**: 엔드포인트와 응답 모양은 `api/` 폴더가 책임집니다. 다른 폴더는 `{answer, contexts, trace}` dict만 돌려줍니다.
- 폴더 밖 실행 진입점: `scripts/`(데이터 수집·인덱스), `evaluation/`(평가), `tests/`(단위 테스트)는 `src/` 밖에 둡니다.

## 작업 규칙

### 소통
- 모든 응답은 한국어로 작성합니다.

### 참조 범위
- 상위 폴더 중 `day`로 시작하는 폴더와 `sds-ax`로 시작하는 폴더 안의 **소스 코드는 참조하지 않습니다**. 읽기, 검색, 복사, import 모두 하지 않습니다.
- 스킬(Ouroboros 등), MCP, uv·pip·가상환경 같은 **개발 도구는 자유롭게 사용**합니다.
- 파일 검색과 탐색은 이 `mini-pjt` 폴더 안으로 한정합니다.

### 코드 수정
- 기존 코드를 수정할 때는 기존 코드를 주석으로 남기고 그 아래에 새 코드를 작성합니다.

### API
- API를 만들거나 수정할 때는 [API Spec.md](API%20Spec.md)의 스펙을 **반드시** 준수합니다.
  - 엔드포인트: `POST /query`, `Content-Type: application/json`
  - 요청 본문: `{"question": str}`
  - 응답 필드 `answer`, `contexts`(`doc_id`, `text`), `trace`(`step`, `input`, `output`)의 이름과 구조를 바꾸지 않습니다.
- 스펙과 다르게 만들어야 할 이유가 생기면 임의로 바꾸지 않고 먼저 사용자에게 확인합니다.

### 법령 근거
- 법 조항 번호(예: 산업안전보건법 제110조, 시행규칙 제159조)와 조문 내용은 **기억에 의존해 쓰지 않습니다.** `data/laws`에 수집한 원문이나 국가법령정보센터 API로 확인한 뒤 씁니다.
- 원문으로 확인하지 못한 조항은 "확인 필요"로 표시하고, 답변·평가셋·문서에 사실처럼 쓰지 않습니다.

### 빌드 패턴
- 개발과 평가는 [BuildPattern.md](BuildPattern.md)의 12개 패턴 체크리스트를 따릅니다.
  - **필수 패턴 1, 3, 11, 12**(LCEL 구조화 출력, RAG, Trace, 평가)는 반드시 구현합니다.
  - 전체 12개 중 **6개 이상** 적용을 목표로 합니다.
- 패턴을 적용할 때 Day 실습 폴더의 소스는 참조하지 않습니다(위 "참조 범위" 규칙). 패턴 이름만 기준으로 새로 구현합니다.
- 평가 보고서(round1/round2_report.md)에는 어떤 패턴을 어디에 적용했는지 적습니다.

## 추가 규칙

<!-- 여기에 규칙을 추가하세요 -->
- 진행 현황과 다음 작업은 [HANDOFF.md](HANDOFF.md)를 참고합니다. HANDOFF.md 내용이 위 규칙과 충돌하면 **위 규칙을 따릅니다.**
- MSDS 개정 업무 흐름(영향 분석 → 변경 제출 판단 → 수정·제출 → 공급망 제공 → 게시·표지·교육)은 [MSDS_Revision_SOP.md](MSDS_Revision_SOP.md)를 함께 참고합니다. 에이전트 설계, 도구, 평가셋, 문서 작성에 반영합니다.
  - SOP의 조문 번호와 기한은 2차 자료 기반입니다. 위 "법령 근거" 규칙대로 원문을 확인한 뒤에만 사실로 쓰고, 확인 전에는 "확인 필요"로 표시합니다.

# 프로그램 사양서 목차

`src/`의 `.py` 파일마다 하나씩 작성한 프로그램 사양서입니다. 폴더 구조는 `src/`의 도메인 폴더와 같습니다(`src/<도메인>/<파일>.py` → `docs/spec/<도메인>/<파일>.md`).

- 작성 기준: 2026-11-12, 커밋 `86417d6`
- 대상: 24개 파일 (내용 없는 `__init__.py` 제외). 화면 `src/api/static/index.html`은 `.py`가 아니라 [api/app.md](api/app.md)에서 함께 설명
- 작성 원칙: 소스 코드·주석, `tests/`, `git log`에서 확인한 내용만 씀. 확인하지 못한 것은 "확인 필요"로 표시. 주석으로 남은 기존 코드는 현재 동작이 아니라 9절 변경 이력에만 적음
- 폴더 역할과 파일 배치 규칙은 [CLAUDE.md](../../CLAUDE.md) "소스 폴더 구조" 절

## 도메인별 목록

### api — HTTP 진입점
| 사양서 | 내용 |
|---|---|
| [app.md](api/app.md) | FastAPI 서버. `POST /query`(오류가 나도 API Spec 모양 유지), `GET /health`, `GET /`(화면에 초기 데이터를 넣어 제공), UTF-8 응답 |
| [schemas.md](api/schemas.md) | API Spec 입출력 모델 `QueryRequest`, `QueryResponse`, `Context`, `TraceStep` (이름·구조 변경 금지) |

### agents — Supervisor·서브 에이전트
| 사양서 | 내용 |
|---|---|
| [brains.md](agents/brains.md) | LLM 부분(라우터·ReAct·판정)을 `Brains`로 묶고, 기준일이 고정된 에이전트별 도구 묶음(`make_tools`, MCP 전환)을 만듦 |
| [judgment.md](agents/judgment.md) | 개정 판정 후처리: `assess_update` 결과로 근거 없는 제품·항목 제거(`sanitize_judgment`), 답변 문구(`format_judgment`, 승인 요청 안내) |
| [prompts.md](agents/prompts.md) | 공통 규칙, 서브 에이전트별 프롬프트, 라우터·판정 프롬프트 |
| [schemas.md](agents/schemas.md) | LCEL 구조화 출력 `Route`, `ProductRevision`, `RevisionJudgment` (doc_id 형식 검증) |

### workflows — LangGraph 그래프와 `/query` 처리
| 사양서 | 내용 |
|---|---|
| [graph.md](workflows/graph.md) | 메인 그래프(input_guard → supervisor → 서브 에이전트 → confirm_request·approval → output_guard)와 `run_query` 명령 처리(법령 갱신 / 승인 요청 / 승인·반려 / 일반 질문) |
| [evidence.md](workflows/evidence.md) | 도구 결과를 trace 단계와 근거(contexts)로 변환 (도구별 doc_id 규칙, 마스킹, 중복 제거) |
| [evidence_text.md](workflows/evidence_text.md) | 도구 결과를 문장형 근거로 바꾸는 함수, 서비스 정책 근거(`policy:service`) |
| [pipeline_v1.md](workflows/pipeline_v1.md) | 1일차 LLM 없는 규칙 기반 파이프라인 (기준선 보관, API에서 쓰지 않음) |

### memory — HITL 상태 저장
| 사양서 | 내용 |
|---|---|
| [checkpointer.md](memory/checkpointer.md) | SQLite 체크포인터(`checkpoints.sqlite`)와 요청 번호 `REQ-XXXX` 발급 |

### tools — 에이전트 도구와 MCP
| 사양서 | 내용 |
|---|---|
| [msds_tools.md](tools/msds_tools.md) | 도구 11개: MSDS 조회(마스킹), CAS·용어 검색, 변경 사건 조회, 재제출 규칙 판정, 영향 판정, 법령 검색, 단일물질, 혼합물 검토 목록 |
| [mcp_server.md](tools/mcp_server.md) | FastMCP stdio 서버 `msds-db` — MSDS DB 도구 6개 노출 |
| [mcp_client.md](tools/mcp_client.md) | MCP 브리지 — 백그라운드 세션으로 MCP 도구를 동기 도구로 제공, 실패 시 로컬 도구 |

### regulation — 법령 RAG와 갱신
| 사양서 | 내용 |
|---|---|
| [retriever.md](regulation/retriever.md) | 법령 검색: 조문 청킹, BM25+FAISS RRF, 쿼리 확장, LLM 리랭크, 기준일 시행 판·시행 예정 판 구분 |
| [refresh.md](regulation/refresh.md) | '법령 갱신' 명령: 수집 → 조문 비교 → 인덱스 재생성 → 캐시 비우기 (동시 실행 잠금) |

### revision — MSDS 개정 미리보기·반영·중복 확인
| 사양서 | 내용 |
|---|---|
| [preview.md](revision/preview.md) | 변경 사건별 제품 변경 작업(op), 화면 초기 데이터, 승인 대기 목록 |
| [msds_apply.md](revision/msds_apply.md) | 승인 → `products.json` 반영(시험 기능): 개정판 +1, 이전 판 보관, 반영 기록, '확인 필요' 대체 표기 입력, 원복 |
| [dedupe.md](revision/dedupe.md) | 중복 승인 요청 확인: 승인 대기 중인 같은 변경, 이미 승인·반영된 같은 변경(반영 기록 기준), 기존 중복 정리 |

### guardrails — 입력 차단·출력 마스킹
| 사양서 | 내용 |
|---|---|
| [guard.md](guardrails/guard.md) | 입력 차단(인젝션·승인 우회·영업비밀·범위 밖), 출력 마스킹(전화번호·이메일·담당자 이름·영업비밀 실명) |

### shared — 공통 설정·클라이언트
| 사양서 | 내용 |
|---|---|
| [config.md](shared/config.md) | 상위 `.env` 로드, 데이터·인덱스·체크포인트 경로, 설정값, 질문 기준일 기본값(`MSDS_TODAY`) |
| [llm.md](shared/llm.md) | Bedrock 채팅 모델·Titan 임베딩 클라이언트, 재시도 래퍼 `with_retry` |
| [dates.md](shared/dates.md) | 질문 문장의 날짜 표현에서 질문 기준일 추출 |
| [trace.md](shared/trace.md) | trace 단계(`step`), JSON 직렬화, 메시지 본문 추출 |

## 사양서 양식

모든 사양서는 아래 순서를 따릅니다. 새 `.py` 파일을 추가하면 같은 양식으로 사양서를 만들고 이 목차에 한 줄 추가합니다.

1. 개요 — 목적과 시스템 안의 역할
2. 의존 관계 — 사용하는 내부 모듈, 이 모듈을 쓰는 곳, 외부 라이브러리·서비스
3. 구성 요소 목록 — 함수·클래스·상수 표
4. 상세 사양 — 함수·클래스별 입력·출력·처리·예외
5. 데이터·설정 — 읽고 쓰는 파일, 환경 변수, 상수
6. 처리 흐름
7. 제약·주의 사항
8. 관련 테스트
9. 변경 이력

## 작성하며 발견한 점과 조치

2026-11-12 사양서 작성 뒤 동작을 바꾸지 않는 범위(주석·경로·쓰지 않는 import)에서 정리했습니다.

| 위치 | 내용 | 조치 |
|---|---|---|
| `src/revision/dedupe.py` docstring | "새 질문 때 `run_query`에서 중복 요청을 닫는다"는 옛 흐름 설명이 남아 있음. 현재는 승인 요청(`request_approval`) 때 중복을 알리고 올리지 않음 | 정리 완료 |
| `src/revision/preview.py` docstring | U-01 같은 용어 사건에 `remove` 작업을 만든다고 적혀 있으나, 실제로는 담당자 입력이 필요한 `replace` 작업을 만듦 | 정리 완료 |
| `src/revision/msds_apply.py`, `src/tools/mcp_server.py`, `src/tools/mcp_client.py`, `src/api/app.py` 주석 | 리팩토링 전 옛 경로(`src/revision_preview`, `src/tools.py`, `src/mcp_*.py`, `src/agent.py`, `src/static/`)가 남아 있음 | 정리 완료 |
| `src/api/app.py` | `msds_tools`를 import 하지만 현재 코드에서는 쓰지 않음(주석 처리된 기존 코드에서만 사용) | 주석 처리(정리 완료) |
| `src/tools/msds_tools.py` | `DATA_DIR`을 `shared/config.py`가 아니라 파일 위치 기준으로 계산 (CLAUDE.md 경로 계산 규칙과 다름) | `shared/config.py`의 `DATA_DIR` 사용으로 정리 완료 |
| `src/workflows/graph.py` | '요청 안 함'은 서버를 부르지 않아 초안이 승인 요청 대기 상태로 남음(나중에 `승인 요청 REQ-xxxx`로 올릴 수 있음). 새 질문 직후 `approval`에서 멈추는 옛 분기는 현재 흐름에서 도달하지 않는 것으로 보임 | 그대로 둠 (동작 변경 필요·운영 판단 사항) |
| `src/revision/dedupe.py` | `close_existing_duplicates`·`close_as_duplicate`는 앱 코드에서 호출하지 않고 테스트에서만 사용 (기존 중복 정리 때 한 번 수동 실행) | 그대로 둠 (동작 변경 필요·운영 판단 사항) |
| 테스트 없음 | `revision/preview.py`(화면 데이터·승인 대기 목록), `msds_apply.py`의 입력 파싱·원복 함수, `agents/prompts.py`, `workflows/pipeline_v1.py`에 직접 테스트가 없음 | 그대로 둠 (테스트 추가는 요청 시) |

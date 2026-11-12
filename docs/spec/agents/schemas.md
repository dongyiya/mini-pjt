# `src/agents/schemas.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/agents/schemas.py` |
| 도메인 | `agents` — Supervisor·서브 에이전트(regulation·impact·revision) |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 80줄 |

## 1. 개요
에이전트 LLM의 구조화 출력 스키마(패턴 1: LCEL 구조화 출력)를 정의합니다. Supervisor 라우팅 결과 `Route`와 개정 판정 `RevisionJudgment`(제품별 `ProductRevision` 포함)가 있습니다. API 입출력 스키마는 2026-11-12에 `src/api/schemas.py`로 옮겼습니다.

## 2. 의존 관계
- 사용하는 내부 모듈: 없음
- 이 모듈을 사용하는 곳: `src/agents/brains.py`, `src/agents/judgment.py`, `src/workflows/graph.py`, `tests/test_agent.py`, `tests/test_dedupe.py`, `tests/test_schemas.py`
- 외부 라이브러리·서비스: `pydantic` (`BaseModel`, `Field`, `field_validator`)

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `DOC_ID` | 상수(정규식) | 근거 doc_id 형식 |
| `Route` | 클래스 | Supervisor 위임 대상과 근거 |
| `ProductRevision` | 클래스 | 제품 하나의 개정 내용 |
| `RevisionJudgment` | 클래스 | 개정 판정 전체(HITL 대상) |

## 4. 상세 사양
### 4.1 `Route(BaseModel)`
- `agent: Literal["regulation", "impact", "revision", "out_of_scope"]` — 필드 설명에 각 값의 의미가 들어 있어 LLM에 전달됩니다.
- `reason: str` — 한 문장 근거.
- 예외: 목록 밖 값이면 `ValidationError`.

### 4.2 `ProductRevision(BaseModel)`
- `product_id: str`(예: P-002), `product_name: str`, `sections: list[str]`(MSDS 항목 번호), `changes: list[str]`(항목별 바꿀 내용), `resubmission_required: bool`(필드 설명: "시행규칙 제159조제1항에 따른 공단 재제출 대상 여부").

### 4.3 `RevisionJudgment(BaseModel)`
- 필드: `revision_needed: bool`, `products: list[ProductRevision]`(기본 빈 목록), `reasons: list[str]`, `legal_basis: list[str]`, `draft: str`.
- 검증 `_check_doc_ids`(`legal_basis`): 모든 항목이 `DOC_ID`에 맞아야 하며, 아니면 `ValueError("doc_id 형식이 아닙니다: …")` → `ValidationError`.
- 속성 `resubmission_required`: 제품 중 하나라도 `resubmission_required`이면 `True`.

## 5. 데이터·설정
- 읽는 파일 / 쓰는 파일 / 환경 변수: 없음
- 주요 상수: `DOC_ID = ^(law:[^:\s]+:\d+(의\d+)?(@\d{4}-\d{2}-\d{2})?|msds:P-\d{3})$` — 예: `law:산안법시행규칙:159`, `law:산안법:112의2`, `law:산안법:110@2027-04-28`, `msds:P-002`

## 6. 처리 흐름
1. `brains.llm_brains`가 `with_structured_output(Route)` / `with_structured_output(RevisionJudgment)`로 LLM 출력을 이 모델로 받습니다.
2. `graph.py`는 판정을 `model_dump()`로 상태(`judgment`)에 저장하고, 필요할 때 `RevisionJudgment(**dict)`로 되살립니다.

## 7. 제약·주의 사항
- `legal_basis`에는 `law:`·`msds:` 형식만 허용됩니다(`rule:`, `update:`, `policy:` 등은 검증 실패).
- 주석상 API Spec 스키마는 "이름·구조 변경 금지"이며 현재 `src/api/schemas.py`에 있습니다.

## 8. 관련 테스트
- `tests/test_schemas.py`: `test_route_literal`, `test_revision_judgment_valid_and_resubmission_flag`, `test_revision_judgment_rejects_bad_doc_ids`
- `tests/test_agent.py`, `tests/test_dedupe.py`: 판정 객체를 만들어 그래프 테스트에 사용

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `3c00663` | (`src/schemas.py`) 2일차: API Spec 입출력 + `Route`·`RevisionJudgment` 구조화 출력 스키마 |
| `97ab1fd` | `src/schemas.py` → `src/agents/schemas.py`. API 입출력(`QueryRequest`, `Context`, `TraceStep`, `QueryResponse`)은 `src/api/schemas.py`로 옮기고 이 파일에는 주석으로만 남김 |

# `src/workflows/evidence_text.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/workflows/evidence_text.py` |
| 도메인 | `workflows` — LangGraph 그래프와 `/query` 처리 흐름 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 173줄 |

## 1. 개요
도구 결과를 근거(contexts)용 "항목: 값" 문장으로 바꾸는 함수 모음입니다. 2차 평가에서 JSON 근거 때문에 RAGAS 채점 LLM이 답변과 대조하기 어려웠던 문제(faithfulness 0.78)를 개선하려고 만들었습니다.
또한 `SERVICE.md` 4절의 서비스 정책을 `policy:service` 근거로 제공합니다. 마스킹은 이 모듈이 아니라 `evidence.collect`에서 적용합니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.shared.config` (`ROOT`)
- 이 모듈을 사용하는 곳: `src/workflows/evidence.py`, `src/workflows/graph.py` (모두 함수 안 지연 import)
- 외부 라이브러리·서비스: 표준 `re`, `functools.lru_cache`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `LAW_NAME` | 상수(dict) | 법령 약칭 → 정식 이름(`산안법`, `산안법시행규칙`, `화관법`) |
| `law_label` | 함수 | `law:` doc_id → "산업안전보건법 제N조" 같은 표기 |
| `msds_text` | 함수 | 제품 MSDS 조회 결과 → 문장 |
| `_change_text` | 함수(내부) | 변경 작업 하나 → 문장 |
| `update_text` | 함수 | 변경 사건 → 문장 |
| `assessment_text` | 함수 | `assess_update` 판정 → 문장 |
| `resubmission_text` | 함수 | `check_resubmission` 판정 → 문장 |
| `substance_text` | 함수 | 단일물질 정보 → 문장 |
| `updates_catalog_text` | 함수 | 변경 사건 목록 → 문장 |
| `products_catalog_text` | 함수 | 제품 목록 → 문장 |
| `products_by_cas_text` | 함수 | CAS 검색 결과 → 문장 |
| `mixture_text` | 함수 | `classify_mixture` 결과 → 문장 |
| `service_policy_text` | 함수 | 서비스 정책 근거 문장(캐시) |
| `POLICY_DOC_ID` | 상수 | `"policy:service"` |
| `POLICY_HINTS` | 상수(정규식) | 정책 근거가 필요한 답변 단서 |
| `needs_policy` | 함수 | 답변에 정책 단서가 있는지 |
| `to_text` | 함수 | 도구 이름별 문장 변환 디스패처 |

## 4. 상세 사양
### 4.1 `law_label(doc_id: str) -> str`
- `^law:([^:]+):(\d+)(?:의(\d+))?(?:@(날짜))?$` 형식이면 "<정식 이름> 제N조[의M][(<날짜> 시행 예정)]", 아니면 입력 그대로.

### 4.2 `msds_text(v: dict) -> str`
- 머리줄: "제품 MSDS <id> <name> (개정 N판, 날짜)". 있는 항목만 줄로 추가: 1번(공급자·담당자·전화·이메일), 2번(GHS 분류), 3번(성분명·CAS·함유량, 영업비밀 성분은 "(영업비밀 성분, 공개 명칭과 함유량 범위만 기재)" 표시), 15번(법령별 규제현황).

### 4.3 `update_text(u: dict) -> str`
- "변경 사건 <id> (<type>, 실제 법 개정|가상 사내 사건): <title>", 공포일·시행일 또는 발생일, 내용, 바뀌는 내용(`_change_text`: `op`이 `set`/`component`/`add`/그 밖), 관련 조문(`law_label`).

### 4.4 `assessment_text(r: dict) -> str`
- "규칙 판정(assess_update) – 변경 사건 …의 영향", 영향 제품이 없으면 "영향받는 제품 없음", 있으면 제품별 수정 검토 항목·현재 표기·재제출 여부·근거·기한, 관련 조문.

### 4.5 `resubmission_text(r: dict) -> str`
- "규칙 판정(check_resubmission) – 바뀐 내용 '…': 공단 재제출 대상[ 아님]. 근거: … [. 기한]".

### 4.6 `substance_text`, `updates_catalog_text`, `products_catalog_text`, `products_by_cas_text`, `mixture_text`
- 각각 물질(이름·CAS·GHS·신호어·그림문자·규제), 사건 목록, 제품 목록, CAS 검색 결과(없으면 "해당 성분이 들어 있는 등록 제품 없음 (영업비밀 성분은 검색되지 않음)"), 혼합물 검토 목록(성분 유해성별 제품 2번 반영 여부, 제외 항목, note)을 한 문단으로 만듭니다.

### 4.7 `service_policy_text() -> str`
- 처리: `ROOT / "SERVICE.md"`를 읽어 `## 4. 서비스 정책` 다음 줄부터 `세부 케이스` 앞까지를 "서비스 정책(SERVICE.md 4절)\n…"으로 반환.
- 예외·오류 처리: 파일을 못 읽거나(`OSError`) 패턴이 없으면 고정 요약 문장("서비스 정책: 영업비밀 비공개, 담당자 연락처 마스킹, …")을 반환.
- `@lru_cache(maxsize=1)` — 프로세스당 한 번만 읽습니다.

### 4.8 `needs_policy(answer: str) -> bool`
- `POLICY_HINTS`(승인|제출|마스킹|가려|영업비밀|대체자료|공개하지|범위 밖|답하지 않|따르지 않|처리할 수 없|담당자)가 답변에 있으면 `True`.

### 4.9 `to_text(name: str, args: dict, result: Any) -> str | None`
- 도구 이름(`get_msds`/`_msds`, `get_regulation_update`, `list_regulation_updates`, `list_products`, `assess_update`, `check_resubmission`, `get_substance`, `classify_mixture`, `find_products_by_cas`)별 문장 함수를 부르고, 해당 없으면 `None`.

## 5. 데이터·설정
- 읽는 파일: `SERVICE.md` (프로젝트 루트, `ROOT` 기준)
- 쓰는 파일 / 환경 변수: 없음
- 주요 상수: `LAW_NAME`, `POLICY_DOC_ID = "policy:service"`, `POLICY_HINTS`

## 6. 처리 흐름
1. `evidence.contexts_from_tool`이 도구별로 이 모듈의 문장 함수를 호출
2. `graph.py`의 `output_guard`·`_interrupt_response`·`run_query`가 `POLICY_DOC_ID`·`needs_policy`·`service_policy_text`로 정책 근거를 붙임

## 7. 제약·주의 사항
- `service_policy_text`는 캐시되므로 실행 중 `SERVICE.md`를 고쳐도 재시작 전까지 반영되지 않습니다.
- 대부분의 함수는 필수 키(`id`, `cas`, `name` 등)를 `[]`로 바로 읽어, 키가 없으면 `KeyError`가 납니다(별도 처리 없음).
- `to_text`는 저장소 안(`src/`, `scripts/`, `evaluation/`, `tests/`)에서 호출하는 곳을 찾지 못했습니다. 용도 확인 필요.
- 마스킹은 하지 않습니다(호출 측 `evidence.collect`, `guardrails.mask_output`에서 적용).

## 8. 관련 테스트
- 이 모듈을 직접 import 하는 테스트는 없습니다. `tests/test_agent.py`의 `test_blocked_question_skips_llm`(contexts 가 `policy:service`), `test_impact_agent_contexts_are_masked_and_deduped`(`rule:find_products_by_cas:…`, `policy:service`)가 간접 확인합니다.

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `c8f8ff5` | (`src/context_text.py`) 2차 평가 이후 개선: 근거를 문장형으로, `rule:`·`policy:service` 근거 추가 |
| `97ab1fd` | `src/context_text.py` → `src/workflows/evidence_text.py` |

주석으로 남은 변경: import 경로 `src.config` → `src.shared.config`.

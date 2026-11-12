# `src/workflows/pipeline_v1.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/workflows/pipeline_v1.py` |
| 도메인 | `workflows` — LangGraph 그래프와 `/query` 처리 흐름 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 127줄 |

## 1. 개요
1일차에 만든 LLM 없는 규칙 기반 최소 파이프라인입니다. API 응답 모양(`{answer, contexts[{doc_id,text}], trace[{step,input,output}]}`)을 미리 고정하고 데이터·도구·검색이 맞물리는지 확인하려는 뼈대였으며, docstring 에 따르면 2일차에 LangGraph 그래프로 대체되었습니다. 현재 저장소에서 이 모듈을 import 하는 곳은 없습니다(명령줄 실행만 가능).

## 2. 의존 관계
- 사용하는 내부 모듈: `src.tools.msds_tools` (`assess_update`, `find_products_by_cas`, `get_msds`, `mask_email`, `mask_phone`), `src.regulation.retriever` (`get_chunk`, `retrieve`)
- 이 모듈을 사용하는 곳: 없음 (`src/guardrails/guard.py` docstring 에 "1일차 src/pipeline.py 의 정규식을 옮겨 확장했습니다"라는 언급만 있음)
- 외부 라이브러리·서비스: 표준 `json`, `re`, `sys`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `INJECTION` | 상수(정규식) | 프롬프트 주입 패턴 |
| `APPROVAL_BYPASS` | 상수(정규식) | 승인 우회 요청 패턴 |
| `TRADE_SECRET` | 상수(정규식) | 영업비밀 요청 패턴 |
| `CONTACT` | 상수(정규식) | 담당자·연락처 질문 패턴 |
| `IN_SCOPE` | 상수(정규식) | 서비스 범위 단서 |
| `_ctx` | 함수(내부) | `{doc_id, text}` 생성 |
| `guard` | 함수 | 입력 가드레일(거절 사유 또는 `None`) |
| `run` | 함수 | 질문 하나 처리 |

## 4. 상세 사양
### 4.1 `guard(question: str) -> str | None`
- 순서대로 `INJECTION` → `APPROVAL_BYPASS` → `TRADE_SECRET` → `IN_SCOPE` 불일치를 검사해, 처음 걸린 것의 거절 문구를 반환. 모두 통과하면 `None`.

### 4.2 `run(question: str) -> dict[str, Any]`
- 입력: 질문. 출력: `{answer, contexts, trace}`.
- 처리:
  1. `guard` — 거절이면 trace `input_guard`만 남기고 거절 문구 반환.
  2. 질문에서 `U-숫자`, `P-숫자`, CAS 번호를 정규식으로 추출.
  3. 변경 사건마다 `tools.assess_update(uid)` → 영향 제품별 재제출 여부 줄, 제품 MSDS 근거(JSON), 관련 조문을 `get_chunk(doc_id)`로 근거 추가(중복 doc_id 제외).
  4. CAS 마다 `tools.find_products_by_cas` → 포함 제품 줄, 각 제품 MSDS 3번 근거.
  5. 변경 사건이 없으면 제품마다 `tools.get_msds(pid)` 근거, 연락처 질문이면 마스킹된 담당자 정보 줄.
  6. 위에서 답 줄이 없으면 `retrieve(question, k=3)`로 법령 검색, 첫 조문 제목으로 안내.
  7. 답이 없으면 "관련 정보를 찾지 못했습니다.", 마지막에 `mask_phone`·`mask_email` 적용, trace `output_guard`.
- 예외·오류 처리: `assess_update` 결과에 `error`가 있으면 그 문구를 답 줄에 넣고 다음 사건으로.

### 4.3 명령줄 실행
- `python -m src.workflows.pipeline_v1 "<질문>"` — 질문이 없으면 "U-01 반영하려면 어떤 제품 MSDS를 고쳐야 해?"로 실행해 JSON 출력.

## 5. 데이터·설정
- 읽는 파일: 직접 읽지 않음(도구·검색기가 데이터와 인덱스를 읽음)
- 쓰는 파일 / 환경 변수: 없음
- 주요 상수: 위 정규식 5개, 검색 `k=3`, trace 출력 500자 자르기(`assess_update`, `get_msds`)

## 6. 처리 흐름
```
질문 → guard ─(거절)→ 응답
          └→ U-번호: assess_update → CAS: find_products_by_cas → (U-번호 없을 때) P-번호: get_msds
               → (답 없으면) retrieve → 연락처 마스킹 → {answer, contexts, trace}
```

## 7. 제약·주의 사항
- LLM을 쓰지 않으며 질문 기준일·HITL·라우팅이 없습니다. 현재 서비스(`POST /query`)는 `src/workflows/graph.py`를 씁니다.
- 근거는 JSON 문자열이며, 이 모듈은 마스킹 함수를 답변에만 적용합니다(`get_msds` 결과 자체의 마스킹 여부는 `src/tools/msds_tools.py` 사양 참고).
- 입력 가드레일은 현재 `src/guardrails/guard.py`가 담당합니다.

## 8. 관련 테스트
해당 없음

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `0574139` | (`src/pipeline.py`) 1일차: 서비스 스펙, 평가셋, 데이터·도구 뼈대 |
| `97ab1fd` | `src/pipeline.py` → `src/workflows/pipeline_v1.py`, import 경로를 도메인 폴더로 변경 |

주석으로 남은 변경: 관련 조문을 doc_id 문자열로 `retrieve` 검색해 찾던 방식 → 검색 점수에 따라 빠지는 문제로 `get_chunk(doc_id)` 직접 조회로 교체. import 경로 `src.tools`·`src.retriever` → 도메인 경로.

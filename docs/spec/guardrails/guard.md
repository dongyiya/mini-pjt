# `src/guardrails/guard.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/guardrails/guard.py` |
| 도메인 | `guardrails` — 입력 차단과 출력 마스킹 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 137줄 |

## 1. 개요
가드레일(docstring의 "패턴 6") 모듈로, 질문(입력)을 정규식으로 검사해 차단하고 답변·근거(출력)에서 연락처와 영업비밀 실명을 가립니다. docstring은 `SERVICE.md` 4절 서비스 정책 4가지(영업비밀 비공개, 담당자 연락처 마스킹, 승인 후에만 확정·제출, 범위 밖·지시 변경 거절)를 구현 근거로 듭니다. 1일차 `src/pipeline.py`의 정규식을 옮겨 확장했습니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.shared.config` (`MSDS_PATH`)
- 이 모듈을 사용하는 곳:
  - `src/workflows/graph.py` (`check_input` — `input_guard` 노드, `mask_output` — 최종 답변 마스킹)
  - `src/workflows/evidence.py` (`mask_output` — contexts 텍스트 마스킹)
  - `src/revision/preview.py` (`mask_output`)
  - `src/revision/msds_apply.py` (`_products`, `_in_scope_re`, `_secret_terms`, `_contact_names`의 `cache_clear()` 호출)
  - `tests/test_guardrails.py`
- 외부 라이브러리·서비스: 표준 라이브러리 `re`, `json`, `dataclasses`, `functools.lru_cache`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `INJECTION` | 상수(정규식) | 프롬프트 인젝션·역할 변경 시도 |
| `APPROVAL_BYPASS` | 상수(정규식) | 승인 우회·자동 제출 요청 |
| `TRADE_SECRET` | 상수(정규식) | 영업비밀 실명·CAS·함유량 요청 |
| `IN_SCOPE_WORDS` | 상수(문자열) | 서비스 범위 키워드(MSDS, 성분, 법, 제품, 승인 등) |
| `ID_PATTERN` | 상수(문자열) | `U-숫자`, `P-숫자`, `REQ-...`, CAS 형식 번호 |
| `PHONE` | 상수(정규식) | 휴대전화 번호(`01[016789]`로 시작) |
| `EMAIL` | 상수(정규식) | 이메일 주소 |
| `GuardResult` | 클래스(dataclass) | 입력 검사 결과 |
| `_products()` | 함수(내부, 캐시) | `products.json`의 제품 목록 |
| `_in_scope_re()` | 함수(내부, 캐시) | 범위 판정 정규식 |
| `public_trade_secret_info(question)` | 함수 | 영업비밀 성분의 공개 명칭·함유량 범위 문구 |
| `check_input(question)` | 함수 | 입력 차단 판정 |
| `mask_phone(text)` | 함수 | 전화번호 가운데 자리 마스킹 |
| `mask_email(text)` | 함수 | 이메일 아이디 마스킹 |
| `_secret_terms()` | 함수(내부, 캐시) | 가릴 영업비밀 실명·CAS·함유량 목록 |
| `_contact_names()` | 함수(내부, 캐시) | 담당자 이름 목록 |
| `mask_output(text)` | 함수 | 출력 마스킹 |

## 4. 상세 사양
### 4.1 `GuardResult`
- 필드: `blocked: bool`, `kinds: list[str]`(기본 빈 목록), `message: str`(기본 `""`)
- `kinds` 값: `"injection"`, `"approval_bypass"`, `"trade_secret"`, `"out_of_scope"`

### 4.2 `public_trade_secret_info(question: str = "") -> str`
- 입력: 질문(선택)
- 출력: `"<제품ID>의 공개 명칭 '<name>', 함유량 범위 <content>"`를 `", "`로 이은 문자열(없으면 `""`)
- 처리:
  1. 질문을 대문자로 바꿔 `P-\d{3}` 형식 제품 ID를 찾습니다.
  2. ID가 있으면 그 제품만, 없으면 전체 제품을 대상으로 `section3`에서 `trade_secret`이 참인 성분의 공개 `name`·`content`를 모읍니다.
- 예외·오류 처리: 별도 처리 없음

### 4.3 `check_input(question: str) -> GuardResult`
- 입력: 질문 문장
- 출력: `GuardResult`
- 처리(여러 정책에 걸리면 모두 안내):
  1. `INJECTION` 일치 → `injection`, "이전 지시를 무시하거나 역할을 바꾸라는 요청은 따르지 않습니다."
  2. `APPROVAL_BYPASS` 일치 → `approval_bypass`, 확정·제출은 담당자 승인 후에만 진행하며 초안을 승인 대기로 올린다는 안내
  3. `TRADE_SECRET` 일치 → `trade_secret`, 실제 명칭·CAS 번호·정확한 함유량은 제공하지 않는다는 안내 + `public_trade_secret_info(question)` 결과(있으면)
  4. 위 셋에 모두 해당하지 않고 `_in_scope_re()`에도 맞지 않으면 → `out_of_scope`, MSDS와 관련 법규(산업안전보건법·화학물질관리법) 질문만 답한다는 안내
  5. `kinds`가 있으면 `GuardResult(True, kinds, "요청을 처리할 수 없습니다. " + 안내문들)`, 없으면 `GuardResult(False)`
- 예외·오류 처리: `products.json`을 읽지 못하면 `_products()`에서 파일·JSON 예외가 발생합니다(별도 처리 없음).

### 4.4 `mask_phone(text: str) -> str` / `mask_email(text: str) -> str`
- `mask_phone`: `010-3456-7890` → `010-****-7890` (구분자 `-`, `.`, 공백 또는 없음 허용)
- `mask_email`: 아이디 첫 글자만 남기고 `***` 처리 (`jh.park@...` → `j***@...`)

### 4.5 `mask_output(text: str) -> tuple[str, list[str]]`
- 입력: 답변 또는 contexts 텍스트
- 출력: `(마스킹된 텍스트, 적용한 규칙 목록)`
- 처리:
  1. 전화번호 마스킹 → 바뀌었으면 `"전화번호"` 기록
  2. 이메일 마스킹 → 바뀌었으면 `"이메일"` 기록
  3. `_contact_names()`의 담당자 이름이 있으면 첫 글자 + `*`로 치환(`박지훈` → `박**`), `"담당자 이름"` 기록
  4. `_secret_terms()`(긴 것부터)의 각 항목을 `[영업비밀]`로 치환, `"영업비밀"` 기록
- 예외·오류 처리: 별도 처리 없음

### 4.6 내부 도우미
- `_products()`: `MSDS_PATH`를 UTF-8로 읽어 `["products"]`를 돌려줍니다.
- `_in_scope_re()`: `IN_SCOPE_WORDS` | `ID_PATTERN` | (영업비밀이 아닌 성분명 + 제품명의 `" ("` 앞부분 중 2자 이상, 긴 순) 를 대소문자 무시 정규식으로 만듭니다.
- `_secret_terms()`: 영업비밀 성분의 `real_name`, `real_cas`, `real_content` 중 빈 값이 아닌 것을 중복 제거 후 길이 내림차순 정렬합니다.
- `_contact_names()`: 각 제품 `section1.contact_name` 목록입니다.

## 5. 데이터·설정
- 읽는 파일: `data/msds/products.json` (`products[].id`, `name`, `section1.contact_name`, `section3[].name`·`content`·`trade_secret`·`real_name`·`real_cas`·`real_content`)
- 쓰는 파일: 없음
- 환경 변수: 없음
- 주요 상수: 3절의 정규식·키워드 상수

## 6. 처리 흐름
```
[입력] question → check_input
   ├ injection / approval_bypass / trade_secret 검사 (중복 가능)
   ├ 위에 해당 없을 때만 범위(out_of_scope) 검사
   └ blocked=True면 graph가 LLM을 거치지 않고 message를 답변으로 사용
[출력] answer·contexts → mask_output
   전화번호 → 이메일 → 담당자 이름 → 영업비밀 실명  순서로 치환
```

## 7. 제약·주의 사항
- `_products`, `_in_scope_re`, `_secret_terms`, `_contact_names`는 `lru_cache`로 캐시됩니다. `products.json`이 바뀌면 캐시를 비워야 하며, `src/revision/msds_apply.py`의 `_clear_guardrail_caches()`가 MSDS 반영 후 이를 수행합니다.
- 범위 판정은 키워드 정규식 기반입니다. 키워드(예: "법", "제품")가 넓어 범위 밖 질문이 통과할 수 있고, 키워드가 없는 범위 안 질문은 차단될 수 있습니다.
- 전화번호 패턴은 휴대전화(`01x`)만 대상입니다. 유선 번호 마스킹은 코드에 없습니다.
- 담당자 이름·영업비밀 실명 마스킹은 `products.json`에 있는 값과 정확히 일치할 때만 동작합니다.

## 8. 관련 테스트
- `tests/test_guardrails.py`: `test_eval_18_trade_secret_refused_with_public_info`, `test_eval_19_injection_and_bypass_both_reported`, `test_eval_9_out_of_scope`, `test_in_scope_questions_pass`(9개 케이스), `test_injection_variants`(2개 케이스), `test_mask_output_contacts`, `test_mask_output_trade_secret_terms`, `test_mask_output_leaves_normal_text`
- 간접: `tests/test_api.py` `test_guardrail_via_api`, `test_response_declares_utf8`(범위 밖 질문), `tests/test_agent.py` `test_blocked_question_skips_llm`, `test_impact_agent_contexts_are_masked_and_deduped`

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `3c00663` | 2일차 구현 (당시 `src/guardrails.py`, 1일차 `src/pipeline.py` 정규식을 옮겨 확장) |
| `97ab1fd` | `src/guardrails/guard.py`로 이동. import 경로 `src.config` → `src.shared.config` (기존 코드 주석으로 남김) |

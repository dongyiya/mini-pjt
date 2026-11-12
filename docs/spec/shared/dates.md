# `src/shared/dates.py` 프로그램 사양서

| 항목 | 내용 |
|---|---|
| 파일 | `src/shared/dates.py` |
| 도메인 | `shared` — 여러 도메인이 함께 쓰는 설정·LLM·날짜·trace 공통 기능 |
| 작성 기준 | 2026-11-12, 커밋 `86417d6` |
| 규모 | 46줄 |

## 1. 개요
질문 문장에서 "질문 기준일"(법령 버전 선택에 쓰는 날짜)을 뽑아내는 모듈입니다. 질문에 날짜 표현이 있으면 그 날짜를, 없으면 오늘(`config.today()`)을 씁니다. API 요청 본문은 `{"question"}` 그대로 두고 문장에서 날짜를 읽는 방식입니다.

## 2. 의존 관계
- 사용하는 내부 모듈: `src.shared.config` (`today`)
- 이 모듈을 사용하는 곳: `src/workflows/graph.py` (`extract_as_of`, supervisor 노드에서 기준일 결정), `tests/test_dates.py`
- 외부 라이브러리·서비스: 표준 라이브러리 `re`, `datetime`

## 3. 구성 요소 목록
| 이름 | 종류(함수/클래스/상수) | 설명 |
|---|---|---|
| `FULL` | 상수(정규식) | 연·월·일 전체 날짜 패턴 |
| `MONTH` | 상수(정규식) | 연·월 패턴 |
| `YEAR` | 상수(정규식) | "20xx년" 패턴 |
| `_safe(y, m, d)` | 함수(내부) | 유효하지 않은 날짜면 `None` |
| `extract_as_of(question, base)` | 함수 | (기준일, 근거 설명) 반환 |

## 4. 상세 사양
### 4.1 `extract_as_of(question: str, base: date | None = None) -> tuple[date, str]`
- 입력: 질문 문장 `question`, 상대 표현의 기준 날짜 `base`(없으면 `today()`)
- 출력: `(기준일, 근거 설명 문자열)`
- 처리(위에서부터 먼저 맞는 규칙 적용):
  1. `FULL` 일치 + 유효한 날짜 → 그 날짜, 근거 `질문의 날짜 '...'`. 예: `2027-05-01`, `2027.5.1`, `2027. 5. 1.`, `2027년 5월 1일`
  2. `MONTH` 일치 + 유효 → 그 달 1일, 근거 `질문의 '...' (그 달 1일)`
  3. `YEAR` 일치 → 그 해 1월 1일, 근거 `(그 해 1월 1일)`
  4. "내년" 포함 → `base` 다음 해 1월 1일
  5. "다음 달" 또는 "다음달" 포함 → `base` 다음 달 1일(12월이면 다음 해 1월 1일)
  6. 해당 없음 → `base`, 근거 `질문에 날짜가 없어 오늘 날짜`
- 예외·오류 처리: 존재하지 않는 날짜(예: 13월 40일)는 `_safe`가 `None`을 돌려 다음 규칙으로 넘어갑니다. 테스트상 `2027년 13월 40일` → `2027-01-01`(YEAR 규칙).

### 4.2 내부 도우미 `_safe(y, m, d)`
- `date(y, m, d)` 생성 시 `ValueError`이면 `None`을 돌려줍니다.

## 5. 데이터·설정
- 읽는 파일 / 쓰는 파일: 없음
- 환경 변수(간접): `MSDS_TODAY` (`today()` 경유)
- 주요 상수: `FULL`, `MONTH`, `YEAR` 정규식. 모두 연도는 `20\d{2}`만 인식합니다.

## 6. 처리 흐름
```
question ─→ FULL? ─yes→ (그 날짜)
          └no→ MONTH? ─yes→ (그 달 1일)
               └no→ YEAR? ─yes→ (그 해 1월 1일)
                    └no→ "내년"? → (다음 해 1/1)
                         └no→ "다음 달"? → (다음 달 1일)
                              └no→ (base = 오늘)
```

## 7. 제약·주의 사항
- 연도는 2000~2099(`20\d{2}`)만 인식합니다.
- CAS 번호(예: `108-88-3`)나 제품 ID(`P-002`, `U-01`)는 날짜로 오인하지 않음이 테스트로 확인되어 있습니다.
- "올해", "다음 주", 요일 등 docstring에 없는 표현은 지원하지 않습니다.

## 8. 관련 테스트
- `tests/test_dates.py`: `test_extract_as_of`(9개 매개변수 케이스), `test_next_month_in_december`, `test_not_confused_by_cas_or_product_ids`, `test_invalid_date_falls_back`, `test_reason_text`
- 간접: `tests/test_agent.py` `test_as_of_from_question_passed_to_agent`

## 9. 변경 이력
| 커밋 | 내용 |
|---|---|
| `3c00663` | 2일차 구현 (당시 `src/dates.py`) |
| `97ab1fd` | `src/shared/dates.py`로 이동. import 경로 `src.config` → `src.shared.config` (기존 코드 주석으로 남김) |

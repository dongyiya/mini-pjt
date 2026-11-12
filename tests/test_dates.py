from datetime import date

import pytest

# (기존 코드) from src.dates import extract_as_of
from src.shared.dates import extract_as_of

BASE = date(2026, 11, 12)


@pytest.mark.parametrize("q, expected", [
    ("2027-05-01 기준으로 재제출 대상은?", date(2027, 5, 1)),
    ("2027.5.1 시행 기준", date(2027, 5, 1)),
    ("2027. 4. 28. 이후에는?", date(2027, 4, 28)),
    ("2027년 5월 1일에 적용되는 조문", date(2027, 5, 1)),
    ("2027년 5월 기준 MSDS 게시 의무", date(2027, 5, 1)),
    ("2028년에는 어떻게 바뀌나요?", date(2028, 1, 1)),
    ("내년 기준으로 알려줘", date(2027, 1, 1)),
    ("다음 달부터 바뀌는 게 있나요?", date(2026, 12, 1)),
    ("MSDS 재제출 대상은?", BASE),
])
def test_extract_as_of(q, expected):
    assert extract_as_of(q, BASE)[0] == expected


def test_next_month_in_december():
    assert extract_as_of("다음 달", date(2026, 12, 20))[0] == date(2027, 1, 1)


def test_not_confused_by_cas_or_product_ids():
    assert extract_as_of("CAS 108-88-3 톨루엔과 P-002", BASE)[0] == BASE
    assert extract_as_of("U-01 반영", BASE)[0] == BASE


def test_invalid_date_falls_back():
    assert extract_as_of("2027년 13월 40일", BASE)[0] == date(2027, 1, 1)


def test_reason_text():
    assert "오늘" in extract_as_of("재제출?", BASE)[1]

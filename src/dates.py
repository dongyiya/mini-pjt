"""질문 기준일 추출.

질문에 날짜가 있으면 그 날짜를, 없으면 오늘(config.today)을 기준일로 씁니다.
API 요청 본문은 {"question"} 그대로 두고 문장에서 날짜를 읽습니다.

지원 표현: 2027-05-01, 2027.5.1, 2027. 5. 1., 2027년 5월 1일, 2027년 5월(→1일), 2027년(→1월 1일),
          내년(→다음 해 1월 1일), 다음 달(→다음 달 1일)
"""

from __future__ import annotations

import re
from datetime import date

from src.config import today

FULL = re.compile(r"(20\d{2})\s*(?:[-./]|년)\s*(\d{1,2})\s*(?:[-./]|월)\s*(\d{1,2})\s*(?:일|\.)?")
MONTH = re.compile(r"(20\d{2})\s*(?:년|[-./])\s*(\d{1,2})\s*월?")
YEAR = re.compile(r"(20\d{2})\s*년")


def _safe(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def extract_as_of(question: str, base: date | None = None) -> tuple[date, str]:
    """(기준일, 근거 설명)을 돌려줍니다."""
    base = base or today()
    if m := FULL.search(question):
        if d := _safe(int(m[1]), int(m[2]), int(m[3])):
            return d, f"질문의 날짜 '{m[0].strip()}'"
    if m := MONTH.search(question):
        if d := _safe(int(m[1]), int(m[2]), 1):
            return d, f"질문의 '{m[0].strip()}' (그 달 1일)"
    if m := YEAR.search(question):
        return date(int(m[1]), 1, 1), f"질문의 '{m[0].strip()}' (그 해 1월 1일)"
    if "내년" in question:
        return date(base.year + 1, 1, 1), "질문의 '내년' (다음 해 1월 1일)"
    if "다음 달" in question or "다음달" in question:
        y, mth = (base.year + 1, 1) if base.month == 12 else (base.year, base.month + 1)
        return date(y, mth, 1), "질문의 '다음 달' (다음 달 1일)"
    return base, "질문에 날짜가 없어 오늘 날짜"

"""가드레일 (패턴 6) — 입력 차단과 출력 마스킹.

SERVICE.md 4절 서비스 정책:
1. 영업비밀 성분의 실제 명칭·CAS·함유량은 공개하지 않는다 (입력 차단 + 출력에서 실명 제거)
2. 담당자 연락처는 마스킹한다 (출력에서 이름·전화·이메일 마스킹)
3. 확정·제출은 승인 후에만 (승인 우회 요청 차단)
4. 범위 밖 요청과 지시 변경 시도는 거절 (프롬프트 인젝션·범위 밖 차단)

1일차 src/pipeline.py 의 정규식을 옮겨 확장했습니다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from src.config import MSDS_PATH

INJECTION = re.compile(
    r"(이전|위의?|앞의?|기존)\s*(지시|명령|규칙|프롬프트).*(무시|잊)|"
    r"ignore (all|previous|the above)|system prompt|시스템\s*프롬프트|너는\s*이제|역할을\s*바꿔|개발자\s*모드", re.I)
APPROVAL_BYPASS = re.compile(r"승인\s*(없이|생략|건너뛰)|바로\s*(확정|제출)|자동\s*(으로\s*)?제출|제출\s*(까지\s*)?해\s*(줘|버려)")
TRADE_SECRET = re.compile(r"영업비밀.*(실제|진짜|정확|원래|이름|성분명|명칭|함유량|CAS)|(실제|진짜|원래)\s*(성분|이름|명칭)")
IN_SCOPE_WORDS = (
    "MSDS|물질안전보건자료|화학|성분|물질|CAS|유해|위험|규제|화관법|산안법|산업안전보건법|화학물질관리법|"
    "법|조문|시행|제품|개정|제출|게시|교육|경고|표지|표시|라벨|대체자료|공단|KOSHA|함유|배합|담당자|연락처|"
    "고객사|근로자|작업장|사업장|재제출|승인|반려|초안|유독|사고대비|GHS|분류")
ID_PATTERN = r"U-\d+|P-\d+|REQ-[0-9A-Za-z]+|\d{2,7}-\d{2}-\d"
PHONE = re.compile(r"(01[016789])[-.\s]?(\d{3,4})[-.\s]?(\d{4})")
EMAIL = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+)")


@dataclass
class GuardResult:
    blocked: bool
    kinds: list[str] = field(default_factory=list)
    message: str = ""


@lru_cache(maxsize=1)
def _products() -> list[dict]:
    return json.loads(MSDS_PATH.read_text(encoding="utf-8"))["products"]


@lru_cache(maxsize=1)
def _in_scope_re() -> re.Pattern:
    names = {c["name"] for p in _products() for c in p["section3"] if not c.get("trade_secret")}
    names |= {p["name"].split(" (")[0] for p in _products()}
    extra = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True) if len(n) >= 2)
    return re.compile(f"{IN_SCOPE_WORDS}|{ID_PATTERN}|{extra}", re.I)


def public_trade_secret_info(question: str = "") -> str:
    """질문에 나온 제품(없으면 전체)의 영업비밀 성분 공개 명칭·범위."""
    ids = set(re.findall(r"P-\d{3}", question.upper()))
    rows = []
    for p in _products():
        if ids and p["id"] not in ids:
            continue
        for c in p["section3"]:
            if c.get("trade_secret"):
                rows.append(f"{p['id']}의 공개 명칭 '{c['name']}', 함유량 범위 {c['content']}")
    return ", ".join(rows)


def check_input(question: str) -> GuardResult:
    """막아야 하면 blocked=True와 거절 문구를 돌려줍니다. 여러 정책에 걸리면 모두 안내합니다."""
    kinds, msgs = [], []
    if INJECTION.search(question):
        kinds.append("injection")
        msgs.append("이전 지시를 무시하거나 역할을 바꾸라는 요청은 따르지 않습니다.")
    if APPROVAL_BYPASS.search(question):
        kinds.append("approval_bypass")
        msgs.append("MSDS 개정본의 확정과 제출은 담당자 승인 후에만 진행합니다. 승인 없이 제출할 수 없으며, "
                    "개정이 필요하면 초안을 만들어 승인 대기로 올려 드립니다.")
    if TRADE_SECRET.search(question):
        kinds.append("trade_secret")
        info = public_trade_secret_info(question)
        msgs.append("영업비밀로 지정된 성분의 실제 명칭·CAS 번호·정확한 함유량은 제공하지 않습니다."
                    + (f" 안내할 수 있는 정보는 {info}입니다." if info else ""))
    if not kinds and not _in_scope_re().search(question):
        kinds.append("out_of_scope")
        msgs.append("이 서비스는 MSDS(물질안전보건자료)와 관련 법규(산업안전보건법·화학물질관리법) 질문만 답합니다. "
                    "범위 밖 질문에는 답하지 않습니다.")
    if kinds:
        return GuardResult(True, kinds, "요청을 처리할 수 없습니다. " + " ".join(msgs))
    return GuardResult(False)


# ---------------------------------------------------------------- 출력 마스킹
def mask_phone(text: str) -> str:
    return PHONE.sub(r"\1-****-\3", text)


def mask_email(text: str) -> str:
    return EMAIL.sub(r"\1***@\2", text)


@lru_cache(maxsize=1)
def _secret_terms() -> list[str]:
    terms = []
    for p in _products():
        for c in p["section3"]:
            if c.get("trade_secret"):
                terms += [c.get("real_name", ""), c.get("real_cas", ""), c.get("real_content", "")]
    return sorted({t for t in terms if t}, key=len, reverse=True)


@lru_cache(maxsize=1)
def _contact_names() -> list[str]:
    return [p["section1"]["contact_name"] for p in _products() if p.get("section1", {}).get("contact_name")]


def mask_output(text: str) -> tuple[str, list[str]]:
    """답변·contexts 텍스트에서 연락처와 영업비밀 실명을 가립니다. (마스킹 결과, 적용한 규칙 목록)"""
    applied = []
    out = mask_phone(text)
    if out != text:
        applied.append("전화번호")
    t2 = mask_email(out)
    if t2 != out:
        applied.append("이메일")
    out = t2
    for name in _contact_names():
        if name in out:
            out = out.replace(name, name[0] + "*" * (len(name) - 1))
            if "담당자 이름" not in applied:
                applied.append("담당자 이름")
    for term in _secret_terms():
        if term in out:
            out = out.replace(term, "[영업비밀]")
            if "영업비밀" not in applied:
                applied.append("영업비밀")
    return out, applied

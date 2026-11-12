"""도구 결과를 근거(contexts) 문장으로 바꿉니다. (2026-11-12, 2차 평가 faithfulness 0.78 개선)

2차 평가에서 제품 MSDS·변경 사건 근거가 JSON 문자열이라 RAGAS 채점 LLM이 답변 문장과 대조하기 어려웠고,
규칙 도구(assess_update, check_resubmission)의 판정 결과는 근거에 아예 없었습니다.
내용은 그대로 두고 '항목: 값' 문장형으로 바꾸며, 규칙 판정은 `rule:` 근거로, 서비스 정책은 `policy:service` 근거로 붙입니다.
(마스킹은 기존처럼 agent.collect 에서 적용)
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from src.config import ROOT

LAW_NAME = {"산안법": "산업안전보건법", "산안법시행규칙": "산업안전보건법 시행규칙", "화관법": "화학물질관리법"}


def law_label(doc_id: str) -> str:
    m = re.match(r"^law:([^:]+):(\d+)(?:의(\d+))?(?:@(\d{4}-\d{2}-\d{2}))?$", doc_id)
    if not m:
        return doc_id
    return (f"{LAW_NAME.get(m[1], m[1])} 제{m[2]}조" + (f"의{m[3]}" if m[3] else "")
            + (f"({m[4]} 시행 예정)" if m[4] else ""))


def msds_text(v: dict) -> str:
    lines = [f"제품 MSDS {v.get('id', '')} {v.get('name', '')}"
             + (f" (개정 {v['revision']['no']}판, {v['revision']['date']})" if v.get("revision") else "")]
    if s1 := v.get("section1"):
        lines.append(f"1번 화학제품과 회사 정보: 제품명 {v.get('name', '')}, 공급자 {s1.get('supplier', '')}, "
                     f"담당자 {s1.get('contact_name', '')}, 전화 {s1.get('contact_phone', '')}, 이메일 {s1.get('contact_email', '')}")
    if s2 := v.get("section2"):
        lines.append("2번 유해성·위험성 분류: " + "; ".join(s2.get("ghs", [])))
    if s3 := v.get("section3"):
        comps = []
        for c in s3:
            tag = " (영업비밀 성분, 공개 명칭과 함유량 범위만 기재)" if c.get("trade_secret") else ""
            comps.append(f"{c['name']}(CAS {c['cas']}) 함유량 {c['content']}{tag}")
        lines.append("3번 구성성분의 명칭 및 함유량: " + "; ".join(comps))
    if s15 := v.get("section15"):
        lines.append("15번 법적 규제현황: " + "; ".join(f"{law} – {', '.join(items)}" for law, items in s15.items()))
    return "\n".join(lines)


def _change_text(c: dict) -> str:
    pid = c.get("product_id", "")
    if c["op"] == "set":
        return f"{pid} 1번 제품명: {c['before']} → {c['after']}"
    if c["op"] == "component":
        return f"{pid} 3번 {c['name']} 함유량: {c['before']} → {c['after']}"
    if c["op"] == "add":
        return f"{pid} 2번 유해성 분류 추가: {c['value']}"
    return f"{pid} {c.get('section', '')}번 변경"


def update_text(u: dict) -> str:
    kind = "실제 법 개정" if u.get("real") else "가상 사내 사건"
    lines = [f"변경 사건 {u['id']} ({u.get('type', '')}, {kind}): {u.get('title', '')}"]
    if u.get("promulgated"):
        lines.append(f"공포일 {u['promulgated']}, 시행일 {u.get('effective', '')}")
    elif u.get("date"):
        lines.append(f"발생일 {u['date']}")
    lines.append(f"내용: {u.get('summary', '')}")
    if u.get("changes"):
        lines.append("바뀌는 내용: " + "; ".join(_change_text(c) for c in u["changes"]))
    if u.get("related_docs"):
        lines.append("관련 조문: " + ", ".join(law_label(d) for d in u["related_docs"]))
    return "\n".join(lines)


def assessment_text(r: dict) -> str:
    u = r.get("update", {})
    lines = [f"규칙 판정(assess_update) – 변경 사건 {u.get('id', '')} {u.get('title', '')}의 영향"]
    if not r.get("affected"):
        lines.append("영향받는 제품 없음")
    for a in r.get("affected", []):
        rs = a.get("resubmission", {})
        verdict = "공단 재제출 대상" if rs.get("resubmission_required") else "공단 재제출 대상 아님"
        cur = f", 현재 표기 {', '.join(a['current'])}" if a.get("current") else ""
        lines.append(f"{a['product_id']} {a['product_name']}: {', '.join(a.get('sections', []))}번 항목 수정 검토{cur}. "
                     f"{verdict} – {rs.get('basis', '')}"
                     + (f". {rs['deadline']}" if rs.get("deadline") else ""))
    if r.get("doc_ids"):
        lines.append("관련 조문: " + ", ".join(law_label(d) for d in r["doc_ids"]))
    return "\n".join(lines)


def resubmission_text(r: dict) -> str:
    verdict = "공단 재제출 대상" if r.get("resubmission_required") else "공단 재제출 대상 아님"
    return (f"규칙 판정(check_resubmission) – 바뀐 내용 '{r.get('change', '')}': {verdict}. 근거: {r.get('basis', '')}"
            + (f". {r['deadline']}" if r.get("deadline") else ""))


def substance_text(s: dict) -> str:
    lines = [f"단일물질 {s['name']} (CAS {s['cas']}, 안전보건공단 공개 MSDS)",
             "GHS 유해성·위험성 분류: " + "; ".join(s.get("ghs", [])),
             f"신호어: {s.get('signal_word') or '-'}, 그림문자: {', '.join(s.get('pictograms', [])) or '-'}"]
    for k, v in (s.get("regulations") or {}).items():
        lines.append(f"{k}: {', '.join(v)}")
    return "\n".join(lines)


def updates_catalog_text(items: list[dict]) -> str:
    return "등록된 변경 사건 목록: " + "; ".join(f"{u['id']} {u['type']} – {u['title']}" for u in items)


def products_catalog_text(items: list[dict]) -> str:
    return "등록된 제품 목록: " + "; ".join(f"{p['id']} {p['name']} ({p['revision']})" for p in items)


def products_by_cas_text(cas: str, hits: list[dict]) -> str:
    if not hits:
        return f"CAS {cas} 성분 검색 결과: 해당 성분이 들어 있는 등록 제품 없음 (영업비밀 성분은 검색되지 않음)"
    return (f"CAS {cas} 성분 검색 결과: "
            + "; ".join(f"{h['product_id']} {h['product_name']} – {h['component']} {h['content']}" for h in hits))


def mixture_text(r: dict) -> str:
    lines = [f"혼합물 검토 목록(classify_mixture) – {r['product_id']} {r['product_name']}",
             "제품 2번 분류: " + "; ".join(r.get("product_section2", []))]
    for h in r.get("component_hazards", []):
        comps = ", ".join(f"{c['component']} {c['content']}" for c in h["components"])
        lines.append(f"{h['hazard_class']}: {comps} ({'제품 2번에 있음' if h['in_product_section2'] else '제품 2번에 없음'})")
    lines += [f"제외: {s}" for s in r.get("skipped", [])]
    lines.append(r.get("note", ""))
    return "\n".join(lines)


@lru_cache(maxsize=1)
def service_policy_text() -> str:
    """SERVICE.md 4절 서비스 정책 원문(답변의 승인·마스킹·거절 안내의 근거)."""
    try:
        text = (ROOT / "SERVICE.md").read_text(encoding="utf-8")
        m = re.search(r"## 4\. 서비스 정책.*?\n(.*?)\n세부 케이스", text, re.S)
        if m:
            return "서비스 정책(SERVICE.md 4절)\n" + m.group(1).strip()
    except OSError:
        pass
    return "서비스 정책: 영업비밀 비공개, 담당자 연락처 마스킹, 확정·제출은 담당자 승인 후에만, 근거 없는 법적 판단 금지, 범위 밖 요청 거절"


POLICY_DOC_ID = "policy:service"
POLICY_HINTS = re.compile(r"승인|제출|마스킹|가려|영업비밀|대체자료|공개하지|범위 밖|답하지 않|따르지 않|처리할 수 없|담당자")


def needs_policy(answer: str) -> bool:
    return bool(POLICY_HINTS.search(answer or ""))


def to_text(name: str, args: dict, result: Any) -> str | None:
    """도구 이름별 문장형 근거. 해당 없으면 None."""
    if name == "get_msds" or name == "_msds":
        return msds_text(result)
    if name == "get_regulation_update":
        return update_text(result)
    if name == "list_regulation_updates":
        return updates_catalog_text(result)
    if name == "list_products":
        return products_catalog_text(result)
    if name == "assess_update":
        return assessment_text(result)
    if name == "check_resubmission":
        return resubmission_text(result)
    if name == "get_substance":
        return substance_text(result)
    if name == "classify_mixture":
        return mixture_text(result)
    if name == "find_products_by_cas":
        return products_by_cas_text(args.get("cas", ""), result)
    return None

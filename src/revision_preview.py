"""UI용 데이터 — 대시보드(규칙 기반 영향 판정), 제품 MSDS 조회, 승인 화면의 변경 전·후 MSDS.

LLM을 쓰지 않습니다. 화면을 열 때 GET / 가 이 데이터를 HTML 에 넣어 보냅니다(API Spec 의 /query 는 그대로).

변경 작업(op) 형식 — 화면(src/static/index.html applyOps)이 변경 전 MSDS 에 적용해 변경 후 MSDS 를 만듭니다.
- {"op": "set", "section": "1", "field": "name", "before", "after"}            제품명 변경
- {"op": "component", "section": "3", "name", "field": "content", "before", "after"}  성분 함유량 변경
- {"op": "add", "section": "2", "value"}                                        유해성 분류 추가
- {"op": "remove", "section": "15", "law", "value", "note"}                     규제 표기 삭제(+확인 필요 메모)

U-02~U-04(가상 사내 사건)는 data/regulation_updates.json 의 "changes" 를 그대로 씁니다.
U-01(실제 법 개정)처럼 match.term 으로 찾는 사건은 해당 표기를 삭제하는 op 를 규칙으로 만들고,
대체 표기는 정하지 않고 '확인 필요' 메모와 안전보건공단 단일물질 자료의 화학물질관리법 규제를 참고로 붙입니다.
"""

from __future__ import annotations

import json
import re
from typing import Any

from src import tools
from src.config import SUBSTANCE_DIR

LAW_KEY = {"화학물질관리법": "화학물질관리법에 의한 규제", "산업안전보건법": "산업안전보건법에 의한 규제"}


def _raw_products() -> list[dict[str, Any]]:
    return tools._products()


def _substance_regs(cas: str, law: str) -> list[str]:
    path = SUBSTANCE_DIR / f"{cas}.json"
    if not path.exists():
        return []
    s = json.loads(path.read_text(encoding="utf-8"))
    return s.get("section15", {}).get(LAW_KEY.get(law, law), [])


def update_ops(update_id: str) -> dict[str, list[dict]]:
    """변경 사건 하나의 제품별 변경 작업 목록."""
    u = tools.get_regulation_update(update_id)
    if "error" in u:
        return {}
    out: dict[str, list[dict]] = {}
    if u.get("changes"):
        for c in u["changes"]:
            op = {k: v for k, v in c.items() if k != "product_id"}
            out.setdefault(c["product_id"], []).append(op)
        return out
    term, section = u["match"].get("term"), u["match"].get("section", "15")
    if not term:
        return out
    for p in _raw_products():
        block = p.get(f"section{section}", {})
        if not isinstance(block, dict):
            continue
        public = {c["name"]: c["cas"] for c in p["section3"] if not c.get("trade_secret")}
        for law, items in block.items():
            for item in items:
                if term not in item:
                    continue
                names = re.findall(r"\(([^)]*)\)", item)
                refs = []
                for n in (names[0].split(",") if names else []):
                    n = n.strip()
                    if n in public:
                        regs = _substance_regs(public[n], law)
                        refs.append(f"{n} – {', '.join(regs) if regs else '자료 없음'}")
                note = (f"'{term}' 표기 삭제 ({u['id']}). 대체 표기는 확인 필요"
                        + (f" · 참고(안전보건공단 단일물질 자료의 {law} 규제): {'; '.join(refs)}" if refs else ""))
                out.setdefault(p["id"], []).append(
                    {"op": "remove", "section": section, "law": law, "value": item, "note": note})
    return out


def build_ui_data() -> dict[str, Any]:
    updates = [tools.get_regulation_update(u["id"]) for u in tools.list_regulation_updates()]
    substances = {}
    for path in sorted(SUBSTANCE_DIR.glob("*.json")):
        s = tools.get_substance(path.stem)
        if "error" not in s:
            substances[s["cas"]] = s
    return {
        "updates": [{k: u.get(k) for k in ("id", "type", "title", "summary", "date", "effective", "real")}
                    for u in updates],
        "products": tools.list_products(),
        "msds": {p["id"]: tools.get_msds(p["id"]) for p in tools.list_products()},   # 마스킹된 MSDS
        "assess": {u["id"]: tools.assess_update(u["id"]) for u in updates},           # 규칙 기반 영향 판정
        "ops": {u["id"]: update_ops(u["id"]) for u in updates},
        "substances": substances,
    }

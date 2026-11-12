"""단일물질 MSDS 스냅샷 수집 (안전보건공단 물질안전보건자료 조회 서비스, 공공데이터포털).

    python -m scripts.collect_substances

- 대상: data/msds/products.json 의 공개 성분 CAS (영업비밀 성분은 제외 — 제품과의 연결이 드러나지 않도록)
- 오퍼레이션: getChemList001(searchCnd=1, CAS 검색) → chemId → getChemDetail021(2번 유해성·위험성), getChemDetail151(15번 법적 규제현황)
- 저장: data/substances/<CAS>.json
- 키가 없거나 호출이 실패하면 기존 스냅샷을 그대로 둡니다.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

# (기존 코드) from src.config import MSDS_PATH, SUBSTANCE_DIR, get_settings, today
from src.shared.config import MSDS_PATH, SUBSTANCE_DIR, get_settings, today

BASE = "https://apis.data.go.kr/B552468/msdschem1/"


class ApiError(RuntimeError):
    pass


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8), reraise=True)
def _get(op: str, params: dict) -> bytes:
    key = get_settings().data_go_kr_key
    r = requests.get(BASE + op, params={"serviceKey": key, **params}, timeout=30)
    if r.status_code == 403 or b"SERVICE_KEY" in r.content[:400]:
        raise ApiError(f"서비스키 오류(HTTP {r.status_code})")
    r.raise_for_status()
    return r.content


def _items(xml: bytes) -> list[ET.Element]:
    root = ET.fromstring(xml)
    code = root.findtext("header/resultCode")
    if code not in (None, "00"):
        raise ApiError(f"resultCode={code} {root.findtext('header/resultMsg')}")
    return root.findall("body/items/item")


def public_cas_list(msds_path: Path = MSDS_PATH) -> list[tuple[str, str]]:
    products = json.loads(msds_path.read_text(encoding="utf-8"))["products"]
    seen = {}
    for p in products:
        for c in p["section3"]:
            if not c.get("trade_secret") and re.fullmatch(r"\d{2,7}-\d{2}-\d", c["cas"]):
                seen.setdefault(c["cas"], c["name"])
    return sorted(seen.items(), key=lambda x: x[1])


def parse_list(xml: bytes, cas: str) -> dict | None:
    """검색 결과 중 CAS가 정확히 같은 첫 물질."""
    for it in _items(xml):
        if (it.findtext("casNo") or "").strip() == cas:
            return {"chem_id": it.findtext("chemId", "").strip(), "name_kor": it.findtext("chemNameKor", "").strip(),
                    "last_date": it.findtext("lastDate", "").strip()}
    return None


def _split(detail: str | None) -> list[str]:
    return [x.strip() for x in (detail or "").split("|") if x.strip()]


def parse_section2(xml: bytes) -> dict:
    out = {"ghs": [], "pictograms": [], "signal_word": "", "hazard_statements": []}
    for it in _items(xml):
        name = it.findtext("msdsItemNameKor", "")
        detail = it.findtext("itemDetail")
        if name == "유해성·위험성 분류":
            out["ghs"] = _split(detail)
        elif name == "그림문자":
            out["pictograms"] = [p.replace(".gif", "") for p in _split(detail)]
        elif name == "신호어":
            out["signal_word"] = (detail or "").strip()
        elif name == "유해·위험문구":
            out["hazard_statements"] = [h.split(":")[0].strip() for h in _split(detail)]
    return out


def parse_section15(xml: bytes) -> dict[str, list[str]]:
    regs = {}
    for it in _items(xml):
        name = (it.findtext("msdsItemNameKor") or "").strip()
        items = [re.sub(r"\s+", " ", x) for x in _split(it.findtext("itemDetail"))]
        if name and items:
            regs[name] = items
    return regs


def collect_one(cas: str, name: str, fetch=_get, collected: date | None = None) -> dict | None:
    hit = parse_list(fetch("getChemList001", {"searchWrd": cas, "searchCnd": 1, "numOfRows": 10, "pageNo": 1}), cas)
    if hit is None:
        return None
    s2 = parse_section2(fetch("getChemDetail021", {"chemId": hit["chem_id"]}))
    s15 = parse_section15(fetch("getChemDetail151", {"chemId": hit["chem_id"]}))
    return {
        "cas": cas, "name": hit["name_kor"] or name, "chem_id": hit["chem_id"],
        "section2": s2, "section15": s15,
        "source": "한국산업안전보건공단 물질안전보건자료 조회 서비스(공공데이터포털)",
        "kosha_last_date": hit["last_date"], "collected": (collected or today()).isoformat(),
        "doc_id": f"substance:{cas}",
    }


def main(out_dir: Path = SUBSTANCE_DIR, fetch=_get) -> int:
    if not get_settings().data_go_kr_key:
        print("[경고] DATA_GO_KR_API_KEY가 없어 기존 스냅샷을 그대로 씁니다.")
        return 0
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    for cas, name in public_cas_list():
        try:
            data = collect_one(cas, name, fetch=fetch)
        except Exception as e:
            print(f"[경고] {name}({cas}) 수집 실패, 기존 스냅샷 유지: {e}")
            continue
        if data is None:
            print(f"[안내] {name}({cas}): 공단 DB에 없음")
            continue
        (out_dir / f"{cas}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        ok += 1
        print(f"{name}({cas}) GHS {len(data['section2']['ghs'])}개, 15번 {list(data['section15'])}")
    print(f"저장 {ok}건 → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

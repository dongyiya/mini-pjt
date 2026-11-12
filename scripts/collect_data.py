"""법령 조문 수집 (국가법령정보센터 Open API, target=eflaw).

    python -m scripts.collect_data            # 현행 + 시행예정 판 수집 → data/laws/*.md
    python -m scripts.collect_data --dry-run  # 받기만 하고 파일은 쓰지 않음

- 법령마다 **현행 판**과 **시행예정 판**을 모두 받습니다(HANDOFF "시행일 기준 조문 선택").
- 시행예정 판은 직전 판과 조문 내용이 달라진 조문만 저장합니다.
- 파일 이름: `<법령명>@<시행일 YYYYMMDD>.md`, 청크 머리: `## [doc_id] 제N조(제목)`
  - 현행 판 doc_id: `law:산안법:110` (평가셋과 같은 형식)
  - 예정 판 doc_id: `law:산안법:110@2027-04-28`
- 키가 없거나 호출이 실패하면 기존 파일을 그대로 두고 경고만 출력합니다.
- 미들웨어(패턴 8): 일시적인 네트워크 오류는 tenacity로 다시 시도합니다.
"""

from __future__ import annotations

import argparse
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import LAW_DIR, get_settings, today

BASE = "https://www.law.go.kr/DRF/"

# 수집 대상: 법령명 → (doc_id 약칭, 조문 번호 범위)
TARGETS: dict[str, tuple[str, list[int]]] = {
    "산업안전보건법": ("산안법", list(range(110, 117))),
    "산업안전보건법 시행규칙": ("산안법시행규칙", list(range(156, 171))),
    "화학물질관리법": ("화관법", [2]),
}


@dataclass
class Version:
    law: str
    mst: str
    status: str          # 현행 | 시행예정 | 연혁
    effective: date
    promulgated: date
    promulgation_no: str = ""
    revision_type: str = ""


@dataclass
class Article:
    key: str             # "110", "112의2"
    title: str
    text: str


@dataclass
class LawFile:
    version: Version
    short: str
    articles: list[Article] = field(default_factory=list)


# ---------------------------------------------------------------- API 호출
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8), reraise=True)
def _get(endpoint: str, params: dict) -> bytes:
    r = requests.get(BASE + endpoint, params=params, timeout=60)
    r.raise_for_status()
    return r.content


def _ymd(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


def parse_versions(xml: bytes, law: str) -> list[Version]:
    """검색 결과 XML에서 이름이 정확히 같은 법령의 판 목록을 뽑습니다(중복 제거)."""
    root = ET.fromstring(xml)
    seen, out = set(), []
    for el in root.findall("law"):
        if (el.findtext("법령명한글") or "").strip() != law:
            continue
        v = Version(
            law=law,
            mst=el.findtext("법령일련번호", "").strip(),
            status=el.findtext("현행연혁코드", "").strip(),
            effective=_ymd(el.findtext("시행일자", "").strip()),
            promulgated=_ymd(el.findtext("공포일자", "").strip()),
            promulgation_no=el.findtext("공포번호", "").strip(),
            revision_type=el.findtext("제개정구분명", "").strip(),
        )
        if (v.mst, v.effective) not in seen:
            seen.add((v.mst, v.effective))
            out.append(v)
    return out


def select_versions(versions: list[Version]) -> list[Version]:
    """현행 판 1개 + 시행예정 판 전부를 시행일 순서로 돌려줍니다."""
    current = [v for v in versions if v.status == "현행"]
    upcoming = [v for v in versions if v.status == "시행예정"]
    return sorted(current[:1] + upcoming, key=lambda v: v.effective)


def _clean(s: str | None) -> str:
    return re.sub(r"[ \t]+", " ", (s or "").strip())


def article_text(el: ET.Element) -> str:
    """조문단위 XML을 '조문내용 / 항 / 호 / 목' 순서의 줄 텍스트로 만듭니다."""
    lines = [_clean(el.findtext("조문내용"))]
    for hang in el.findall("항"):
        if t := _clean(hang.findtext("항내용")):
            lines.append(t)
        for ho in hang.findall("호"):
            if t := _clean(ho.findtext("호내용")):
                lines.append(t)
            for mok in ho.findall("목"):
                for line in (mok.findtext("목내용") or "").splitlines():
                    if t := _clean(line):
                        lines.append(t)
    return "\n".join(x for x in lines if x)


def parse_articles(xml: bytes, numbers: list[int]) -> list[Article]:
    """법령 본문 XML에서 지정한 조 번호(가지 조문 포함)만 뽑습니다."""
    root = ET.fromstring(xml)
    wanted = {str(n) for n in numbers}
    out = []
    for el in root.iter("조문단위"):
        if el.findtext("조문여부") != "조문":
            continue
        no = (el.findtext("조문번호") or "").strip()
        if no not in wanted:
            continue
        branch = (el.findtext("조문가지번호") or "").strip()
        key = f"{no}의{branch}" if branch else no
        out.append(Article(key=key, title=_clean(el.findtext("조문제목")), text=article_text(el)))
    return out


def diff_articles(base: dict[str, str], arts: list[Article]) -> list[Article]:
    """직전 판(base: key→text)과 내용이 달라진 조문만 돌려줍니다."""
    return [a for a in arts if base.get(a.key) != a.text]


# ---------------------------------------------------------------- 파일 쓰기
def doc_id(short: str, key: str, v: Version) -> str:
    base = f"law:{short}:{key}"
    return base if v.status == "현행" else f"{base}@{v.effective.isoformat()}"


def file_name(v: Version) -> str:
    return f"{v.law.replace(' ', '_')}@{v.effective:%Y%m%d}.md"


def render(lf: LawFile, collected: date) -> str:
    v = lf.version
    head = [
        "---",
        f"law: {v.law}",
        f"short: {lf.short}",
        f"mst: {v.mst}",
        f"status: {v.status}",
        f"effective: {v.effective.isoformat()}",
        f"promulgated: {v.promulgated.isoformat()}",
        f'version: "[시행 {v.effective.year}. {v.effective.month}. {v.effective.day}.] '
        f'[공포 {v.promulgated.isoformat()}, 제{v.promulgation_no}호, {v.revision_type}]"',
        f"source: https://www.law.go.kr/DRF/lawService.do?target=eflaw&MST={v.mst}&efYd={v.effective:%Y%m%d}",
        f"collected: {collected.isoformat()}",
        "note: 국가법령정보센터 조문 원문. 법령은 저작권법 제7조에 따라 보호받지 않는 저작물입니다."
        + ("" if v.status == "현행" else " 시행예정 판이며 직전 판과 내용이 달라진 조문만 담았습니다."),
        "---",
        "",
    ]
    body = []
    for a in lf.articles:
        heading = article_heading(a)
        lines = a.text.splitlines()
        # 조문내용 첫 줄이 "제N조(제목)"으로 시작하면 머리와 겹치는 부분을 떼어 냅니다.
        if lines and lines[0].startswith(heading):
            rest = lines[0][len(heading):].strip()
            lines = ([rest] if rest else []) + lines[1:]
        body += [f"## [{doc_id(lf.short, a.key, v)}] {heading}", *lines, ""]
    return "\n".join(head + body)


def article_heading(a: Article) -> str:
    """'112의2' → '제112조의2(제목)'."""
    no, _, branch = a.key.partition("의")
    return f"제{no}조" + (f"의{branch}" if branch else "") + f"({a.title})"


def build_law_files(law: str, fetch=_get, oc: str | None = None) -> list[LawFile]:
    """법령 하나의 현행·시행예정 판을 받아 LawFile 목록을 만듭니다(fetch는 테스트에서 바꿔 끼움)."""
    oc = oc if oc is not None else get_settings().law_api_oc
    short, numbers = TARGETS[law]
    versions = select_versions(parse_versions(
        fetch("lawSearch.do", {"OC": oc, "target": "eflaw", "type": "XML", "query": law, "display": 100}), law))
    if not versions or versions[0].status != "현행":
        raise RuntimeError(f"{law}: 현행 판을 찾지 못했습니다.")
    files, base = [], {}
    for v in versions:
        xml = fetch("lawService.do", {"OC": oc, "target": "eflaw", "MST": v.mst,
                                      "efYd": f"{v.effective:%Y%m%d}", "type": "XML"})
        arts = parse_articles(xml, numbers)
        keep = arts if v.status == "현행" else diff_articles(base, arts)
        base.update({a.key: a.text for a in arts})
        if keep:
            files.append(LawFile(version=v, short=short, articles=keep))
    return files


def write_files(files: list[LawFile], out_dir: Path = LAW_DIR, collected: date | None = None) -> list[Path]:
    """법령별로 기존 `<법령명>@*.md`를 지우고 새로 씁니다."""
    collected = collected or today()
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for law in {f.version.law for f in files}:
        for old in out_dir.glob(f"{law.replace(' ', '_')}@*.md"):
            old.unlink()
    for f in files:
        path = out_dir / file_name(f.version)
        path.write_text(render(f, collected), encoding="utf-8")
        written.append(path)
    return written


def refresh_laws(write: bool = True, fetch=_get, out_dir: Path = LAW_DIR) -> list[dict]:
    """대상 법령을 모두 다시 받아(성공한 법령만) 파일을 바꿔 씁니다. 법령별 결과 목록을 돌려줍니다.

    결과: {"law", "ok", "versions": [{"status", "effective", "articles": [...]}], "error"}
    """
    results = []
    for law in TARGETS:
        try:
            files = build_law_files(law, fetch=fetch)
        except Exception as e:  # 네트워크·형식 오류 → 기존 스냅샷 유지
            results.append({"law": law, "ok": False, "versions": [], "error": f"{type(e).__name__}: {e}"})
            continue
        if write:
            write_files(files, out_dir)
        results.append({"law": law, "ok": True, "error": None, "versions": [
            {"status": f.version.status, "effective": f.version.effective.isoformat(),
             "articles": [a.key for a in f.articles]} for f in files]})
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="법령 조문 수집")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if not get_settings().law_api_oc:
        print("[경고] LAW_API_OC가 없어 기존 스냅샷을 그대로 씁니다.")
        return 0
    # (기존 코드) 법령별 반복을 main 안에서 직접 처리 — UI 수동 갱신에서도 쓰도록 refresh_laws()로 분리
    # for law in TARGETS:
    #     try:
    #         files = build_law_files(law)
    #     except Exception as e:  # 네트워크·형식 오류 → 기존 스냅샷 유지
    #         print(f"[경고] {law} 수집 실패, 기존 스냅샷 유지: {e}")
    #         continue
    #     for f in files:
    #         print(f"{law} {f.version.status} {f.version.effective} 조문 {len(f.articles)}개: "
    #               + ", ".join(a.key for a in f.articles))
    #     if not args.dry_run:
    #         write_files(files)
    for r in refresh_laws(write=not args.dry_run):
        if not r["ok"]:
            print(f"[경고] {r['law']} 수집 실패, 기존 스냅샷 유지: {r['error']}")
            continue
        for v in r["versions"]:
            print(f"{r['law']} {v['status']} {v['effective']} 조문 {len(v['articles'])}개: " + ", ".join(v["articles"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

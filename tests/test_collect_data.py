"""scripts/collect_data.py 단위 테스트 (네트워크 없이, API 응답 구조를 본뜬 XML로 확인)."""

from datetime import date

import pytest

from scripts import collect_data as cd

SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?><LawSearch>
<law id="1"><법령일련번호>300</법령일련번호><현행연혁코드>시행예정</현행연혁코드><법령명한글><![CDATA[테스트법]]></법령명한글>
<공포일자>20261027</공포일자><공포번호>3</공포번호><제개정구분명>일부개정</제개정구분명><시행일자>20270428</시행일자></law>
<law id="2"><법령일련번호>300</법령일련번호><현행연혁코드>시행예정</현행연혁코드><법령명한글><![CDATA[테스트법]]></법령명한글>
<공포일자>20261027</공포일자><공포번호>3</공포번호><제개정구분명>일부개정</제개정구분명><시행일자>20270128</시행일자></law>
<law id="3"><법령일련번호>300</법령일련번호><현행연혁코드>현행</현행연혁코드><법령명한글><![CDATA[테스트법]]></법령명한글>
<공포일자>20261027</공포일자><공포번호>3</공포번호><제개정구분명>일부개정</제개정구분명><시행일자>20261027</시행일자></law>
<law id="4"><법령일련번호>200</법령일련번호><현행연혁코드>연혁</현행연혁코드><법령명한글><![CDATA[테스트법]]></법령명한글>
<공포일자>20250101</공포일자><공포번호>2</공포번호><제개정구분명>일부개정</제개정구분명><시행일자>20250101</시행일자></law>
<law id="5"><법령일련번호>999</법령일련번호><현행연혁코드>현행</현행연혁코드><법령명한글><![CDATA[테스트법 시행령]]></법령명한글>
<공포일자>20250101</공포일자><공포번호>1</공포번호><제개정구분명>제정</제개정구분명><시행일자>20250101</시행일자></law>
</LawSearch>"""


def law_xml(art110_extra: str = "") -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8"?><법령><조문>
<조문단위><조문번호>109</조문번호><조문여부>조문</조문여부><조문제목>앞 조문</조문제목><조문내용>제109조(앞 조문) 본문</조문내용></조문단위>
<조문단위><조문번호>110</조문번호><조문여부>전문</조문여부><조문내용>제2절 물질안전보건자료</조문내용></조문단위>
<조문단위><조문번호>110</조문번호><조문여부>조문</조문여부><조문제목>작성 및 제출</조문제목><조문내용>제110조(작성 및 제출)</조문내용>
  <항><항번호>①</항번호><항내용>① 다음 각 호의 사항을 적는다.{art110_extra}</항내용>
    <호><호번호>1.</호번호><호내용>1. 제품명</호내용>
      <목><목번호>가.</목번호><목내용>가. 국문 제품명
      나. 영문 제품명</목내용></목></호>
    <호><호번호>2.</호번호><호내용>2. 함유량</호내용></호></항>
  <항><항번호>②</항번호><항내용>② 지체 없이 제출한다.</항내용></항></조문단위>
<조문단위><조문번호>111</조문번호><조문여부>조문</조문여부><조문제목>제공</조문제목><조문내용>제111조(제공) 상대방에게 제공하여야 한다.</조문내용></조문단위>
<조문단위><조문번호>111</조문번호><조문가지번호>2</조문가지번호><조문여부>조문</조문여부><조문제목>제공 특례</조문제목><조문내용>제111조의2(제공 특례) 특례를 둔다.</조문내용></조문단위>
</조문></법령>""".encode("utf-8")


def test_parse_versions_filters_exact_name_and_dedupes():
    vs = cd.parse_versions(SEARCH_XML.encode(), "테스트법")
    assert len(vs) == 4
    assert {v.status for v in vs} == {"현행", "시행예정", "연혁"}


def test_select_versions_current_plus_upcoming_sorted():
    vs = cd.select_versions(cd.parse_versions(SEARCH_XML.encode(), "테스트법"))
    assert [v.status for v in vs] == ["현행", "시행예정", "시행예정"]
    assert [v.effective for v in vs] == [date(2026, 10, 27), date(2027, 1, 28), date(2027, 4, 28)]


def test_parse_articles_text_structure_and_branch():
    arts = cd.parse_articles(law_xml(), [110, 111])
    assert [a.key for a in arts] == ["110", "111", "111의2"]   # 109 제외, '전문'(장 제목) 제외
    a110 = arts[0]
    assert a110.title == "작성 및 제출"
    assert a110.text.splitlines() == [
        "제110조(작성 및 제출)", "① 다음 각 호의 사항을 적는다.", "1. 제품명",
        "가. 국문 제품명", "나. 영문 제품명", "2. 함유량", "② 지체 없이 제출한다."]


def test_diff_articles_keeps_only_changed():
    base = {a.key: a.text for a in cd.parse_articles(law_xml(), [110, 111])}
    changed = cd.parse_articles(law_xml(" &lt;개정 2027.1.1&gt;"), [110, 111])
    assert [a.key for a in cd.diff_articles(base, changed)] == ["110"]


def test_doc_id_current_vs_upcoming():
    cur = cd.Version("테스트법", "1", "현행", date(2026, 10, 27), date(2026, 10, 27))
    up = cd.Version("테스트법", "1", "시행예정", date(2027, 4, 28), date(2026, 10, 27))
    assert cd.doc_id("테법", "110", cur) == "law:테법:110"
    assert cd.doc_id("테법", "110", up) == "law:테법:110@2027-04-28"


def test_render_header_and_heading_without_duplicate():
    v = cd.Version("테스트 법", "1", "현행", date(2026, 10, 27), date(2026, 10, 27), "3", "일부개정")
    arts = cd.parse_articles(law_xml(), [111])
    text = cd.render(cd.LawFile(v, "테법", arts), collected=date(2026, 11, 12))
    assert "effective: 2026-10-27" in text and "status: 현행" in text
    assert '[시행 2026. 10. 27.]' in text
    assert "## [law:테법:111] 제111조(제공)\n상대방에게 제공하여야 한다." in text
    assert "## [law:테법:111의2] 제111조의2(제공 특례)\n특례를 둔다." in text
    assert cd.file_name(v) == "테스트_법@20261027.md"


def test_build_law_files_with_fake_fetch(monkeypatch):
    monkeypatch.setitem(cd.TARGETS, "테스트법", ("테법", [110, 111]))

    def fake_fetch(endpoint, params):
        if endpoint == "lawSearch.do":
            return SEARCH_XML.encode()
        # 2027-01-28 판은 내용 동일, 2027-04-28 판은 제110조만 바뀜
        return law_xml(" &lt;개정 2027.4.28&gt;") if params["efYd"] == "20270428" else law_xml()

    files = cd.build_law_files("테스트법", fetch=fake_fetch, oc="x")
    assert [(f.version.status, f.version.effective.isoformat(), [a.key for a in f.articles]) for f in files] == [
        ("현행", "2026-10-27", ["110", "111", "111의2"]),
        ("시행예정", "2027-04-28", ["110"]),
    ]


def test_build_law_files_requires_current(monkeypatch):
    monkeypatch.setitem(cd.TARGETS, "없는법", ("없", [1]))
    with pytest.raises(RuntimeError):
        cd.build_law_files("없는법", fetch=lambda e, p: b"<LawSearch></LawSearch>", oc="x")


def test_write_files_replaces_old_versions(tmp_path):
    (tmp_path / "테스트법@20200101.md").write_text("old", encoding="utf-8")
    (tmp_path / "다른법@20200101.md").write_text("keep", encoding="utf-8")
    v = cd.Version("테스트법", "1", "현행", date(2026, 10, 27), date(2026, 10, 27))
    paths = cd.write_files([cd.LawFile(v, "테법", cd.parse_articles(law_xml(), [110]))], tmp_path, date(2026, 11, 12))
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["다른법@20200101.md", "테스트법@20261027.md"]
    assert paths[0].read_text(encoding="utf-8").count("## [") == 1


def test_refresh_laws_reports_success_and_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(cd, "TARGETS", {"테스트법": ("테법", [110, 111]), "없는법": ("없", [1])})
    monkeypatch.setenv("LAW_API_OC", "x")

    def fake_fetch(endpoint, params):
        if endpoint == "lawSearch.do":
            return SEARCH_XML.encode()
        return law_xml()

    res = cd.refresh_laws(fetch=fake_fetch, out_dir=tmp_path)
    ok, bad = res
    assert ok["ok"] and ok["versions"][0] == {"status": "현행", "effective": "2026-10-27",
                                               "articles": ["110", "111", "111의2"]}
    assert bad["ok"] is False and "현행 판" in bad["error"]
    assert [p.name for p in tmp_path.iterdir()] == ["테스트법@20261027.md"]


def test_main_without_key_keeps_snapshot(monkeypatch, capsys):
    monkeypatch.setenv("LAW_API_OC", "")
    assert cd.main([]) == 0
    assert "기존 스냅샷" in capsys.readouterr().out


@pytest.mark.live
def test_live_collect_dry_run(capsys):
    assert cd.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "산업안전보건법 현행" in out and "화학물질관리법 현행" in out

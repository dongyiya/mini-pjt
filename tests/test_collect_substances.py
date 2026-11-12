"""scripts/collect_substances.py 단위 테스트 (공단 API 응답 구조를 본뜬 XML)."""

import json

import pytest

from scripts import collect_substances as CS

LIST = b"""<?xml version="1.0" encoding="UTF-8"?><response><header><resultCode>00</resultCode></header><body><items>
<item><casNo>25013-15-4</casNo><chemId>000877</chemId><chemNameKor>vinyl</chemNameKor></item>
<item><casNo>108-88-3</casNo><chemId>001032</chemId><chemNameKor>tol</chemNameKor><lastDate>2025-08-08</lastDate></item>
</items></body></response>"""

S2 = """<?xml version="1.0" encoding="UTF-8"?><response><header><resultCode>00</resultCode></header><body><items>
<item><itemDetail>A : 1|B : 2</itemDetail><msdsItemNameKor>유해성·위험성 분류</msdsItemNameKor></item>
<item><msdsItemNameKor>예방조치문구를 포함한 경고표지 항목</msdsItemNameKor></item>
<item><itemDetail>GHS02.gif|GHS07.gif</itemDetail><msdsItemNameKor>그림문자</msdsItemNameKor></item>
<item><itemDetail>위험</itemDetail><msdsItemNameKor>신호어</msdsItemNameKor></item>
<item><itemDetail>H225 : x|H315 : y</itemDetail><msdsItemNameKor>유해·위험문구</msdsItemNameKor></item>
</items></body></response>""".encode()

S15 = """<?xml version="1.0" encoding="UTF-8"?><response><header><resultCode>00</resultCode></header><body><items>
<item><itemDetail>작업환경측정대상물질 (측정주기 : 6개월)|관리대상유해물질 </itemDetail><msdsItemNameKor>산업안전보건법에 의한 규제</msdsItemNameKor></item>
<item><itemDetail>사고대비물질</itemDetail><msdsItemNameKor>화학물질관리법에 의한 규제</msdsItemNameKor></item>
<item><msdsItemNameKor>빈 항목</msdsItemNameKor></item>
</items></body></response>""".encode()


def fake_fetch(op, params):
    return {"getChemList001": LIST, "getChemDetail021": S2, "getChemDetail151": S15}[op]


def test_public_cas_list_excludes_trade_secret():
    cas = dict(CS.public_cas_list())
    assert "108-88-3" in cas and cas["108-88-3"] == "톨루엔"
    assert "111-76-2" not in cas and "107-21-1" not in cas and "영업비밀" not in cas
    assert len(cas) == 11


def test_parse_list_exact_cas():
    assert CS.parse_list(LIST, "108-88-3")["chem_id"] == "001032"
    assert CS.parse_list(LIST, "50-00-0") is None


def test_parse_sections():
    s2 = CS.parse_section2(S2)
    assert s2 == {"ghs": ["A : 1", "B : 2"], "pictograms": ["GHS02", "GHS07"], "signal_word": "위험",
                  "hazard_statements": ["H225", "H315"]}
    s15 = CS.parse_section15(S15)
    assert s15 == {"산업안전보건법에 의한 규제": ["작업환경측정대상물질 (측정주기 : 6개월)", "관리대상유해물질"],
                   "화학물질관리법에 의한 규제": ["사고대비물질"]}


def test_api_error_code_raises():
    bad = b"<response><header><resultCode>30</resultCode><resultMsg>SERVICE ERROR</resultMsg></header></response>"
    with pytest.raises(CS.ApiError):
        CS.parse_list(bad, "1-1-1")


def test_collect_one_and_main(tmp_path, monkeypatch, capsys):
    d = CS.collect_one("108-88-3", "톨루엔", fetch=fake_fetch)
    assert d["doc_id"] == "substance:108-88-3" and d["section15"]["화학물질관리법에 의한 규제"] == ["사고대비물질"]
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "x")
    monkeypatch.setattr(CS, "public_cas_list", lambda: [("108-88-3", "톨루엔"), ("0-00-0", "없음")])
    assert CS.main(out_dir=tmp_path, fetch=fake_fetch) == 0
    assert json.loads((tmp_path / "108-88-3.json").read_text(encoding="utf-8"))["chem_id"] == "001032"
    assert not (tmp_path / "0-00-0.json").exists()
    assert "공단 DB에 없음" in capsys.readouterr().out


def test_main_without_key(monkeypatch, capsys):
    monkeypatch.setenv("DATA_GO_KR_API_KEY", "")
    assert CS.main() == 0
    assert "기존 스냅샷" in capsys.readouterr().out


@pytest.mark.live
def test_live_toluene():
    d = CS.collect_one("108-88-3", "톨루엔")
    assert d["chem_id"] == "001032" and d["section2"]["ghs"]

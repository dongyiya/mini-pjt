"""evaluation/run_eval.py 단위 테스트 (LLM 없이 판정 로직·집계·보고서)."""

from evaluation import run_eval as E


def test_load_cases():
    cases = E.load_cases()
    assert len(cases) == 20
    c6 = next(c for c in cases if c["id"] == "6")
    assert c6["expected_tools"] == ["get_regulation_update", "assess_update", "check_resubmission", "get_msds"]
    assert "재제출 불필요라는 답" in c6["forbidden"]
    assert next(c for c in cases if c["id"] == "9")["expected_tools"] == []


def test_called_tools_and_tool_check():
    trace = [{"step": "input_guard"}, {"step": "tool:assess_update"}, {"step": "tool:get_msds"}]
    called = E.called_tools(trace)
    assert called == ["assess_update", "get_msds"]
    assert E.tool_check(["assess_update", "check_resubmission"], called) == (True, 0.5)
    assert E.tool_check(["search_law"], called) == (False, 0.0)
    assert E.tool_check([], called) == (True, 1.0)


def _case(**kw):
    base = {"id": "x", "category": "positive", "input": "q", "expected_traits": ["A", "B"], "forbidden": ["F"],
            "expected_tools": ["search_law"]}
    base.update(kw)
    return base


def test_decide_pass_and_fail_reasons():
    ok = E.Verdict(traits=[E.Check(item="A", present=True, reason=""), E.Check(item="B", present=True, reason="")],
                   forbidden=[E.Check(item="F", present=False, reason="")])
    assert E.decide(_case(), ok, ["search_law"])["pass"] is True
    assert E.decide(_case(), ok, [])["pass"] is False                       # 기대 도구 미호출
    bad = E.Verdict(traits=[E.Check(item="A", present=False, reason="")],
                    forbidden=[E.Check(item="F", present=True, reason="")])
    d = E.decide(_case(), bad, ["search_law"])
    assert d["pass"] is False and d["missing_traits"] == ["A", "B"] and d["violated_forbidden"] == ["F"]


def test_summarize_and_report():
    rows = []
    for (i, cat), lat in zip(enumerate(["positive", "negative", "guardrail"], start=8), [10.0, 20.0, 12.0]):
        rows.append({**_case(id=str(i), category=cat), "pass": cat != "negative", "latency_s": lat,
                     "tool_coverage": 1.0, "missing_traits": [] if cat != "negative" else ["A"],
                     "violated_forbidden": [], "tools_ok": True, "error": None, "called_tools": ["search_law"]})
    s = E.summarize(rows, {"mean": {"faithfulness": 0.9}})
    assert s["passed"] == 2 and s["total"] == 3
    assert s["must_pass"] == "1/2" and s["must_pass_ok"] is False          # 9번(negative) 실패
    assert s["within_15s"] == "2/3"
    md = E.render_report({"round": 1, "run_at": "t", "model": "m", "as_of": "2026-11-12", "summary": s, "rows": rows})
    assert "# 1차 평가 보고서" in md and "**2/3**" in md and "| 9 | negative | **실패**" in md
    assert "## 패턴 적용 위치" in md and "MCP" in md

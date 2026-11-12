"""자체 평가 (패턴 12: RAGAS + LLM-as-Judge).

    ../.venv/Scripts/python -m evaluation.run_eval --round 1
    ../.venv/Scripts/python -m evaluation.run_eval --round 1 --only 6,14 --skip-ragas   # 일부만 빠르게

- 평가셋: evaluation/test_queries.csv (20건: positive 8, negative 4, edge 5, guardrail 3)
- 통과 판정 (SERVICE.md 5절)
  1) expected_traits 가 모두 답변에 있음      → LLM-as-Judge 가 항목별로 판정
  2) forbidden 항목이 하나도 없음             → LLM-as-Judge 가 항목별로 판정
  3) expected_tools 가 있으면 trace 에 도구 호출 기록 → 기대 도구 중 1개 이상 호출 (커버리지는 따로 보고)
- RAGAS: faithfulness, answer_relevancy, context_precision, context_recall (contexts 가 있는 질문만,
  reference 는 expected_traits 를 이어 붙인 문장)
- 결과: evaluation/results/round<N>.json, evaluation/round<N>_report.md
- 재현성: 질문 기준일을 MSDS_TODAY(기본 2026-11-12)로 고정
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
import types
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("MSDS_TODAY", "2026-11-12")


# ---------------------------------------------------------------- 평가셋
def load_cases(path: Path = EVAL_DIR / "test_queries.csv") -> list[dict]:
    def split(s: str) -> list[str]:
        return [x.strip() for x in (s or "").split(";") if x.strip()]

    with open(path, encoding="utf-8-sig") as f:
        return [{"id": r["id"], "category": r["category"], "input": r["input"],
                 "expected_traits": split(r["expected_traits"]), "forbidden": split(r["forbidden"]),
                 "expected_tools": split(r["expected_tools"]), "note": r.get("note", "")}
                for r in csv.DictReader(f)]


def called_tools(trace: list[dict]) -> list[str]:
    return [t["step"].split(":", 1)[1] for t in trace if t["step"].startswith("tool:")]


def tool_check(expected: list[str], called: list[str]) -> tuple[bool, float]:
    """(통과 여부, 커버리지). 기대 도구가 없으면 통과."""
    if not expected:
        return True, 1.0
    hit = [t for t in expected if t in called]
    return bool(hit), len(hit) / len(expected)


# ---------------------------------------------------------------- LLM-as-Judge
class Check(BaseModel):
    item: str = Field(description="평가 항목 원문 그대로")
    present: bool = Field(description="답변에 이 내용이 (같은 뜻으로) 들어 있으면 true")
    reason: str = Field(description="판단 근거 한 문장")


class Verdict(BaseModel):
    traits: list[Check] = Field(description="기대 특징 각각의 판정 (입력 순서대로)")
    forbidden: list[Check] = Field(description="금지 항목 각각의 판정 (입력 순서대로)")


JUDGE = """MSDS 개정 지원 에이전트의 답변을 채점합니다. 각 항목이 답변에 '같은 뜻으로' 들어 있는지 판정하세요.
- 기대 특징: 답변에 그 내용이 실질적으로 있으면 present=true. 표현이 달라도 뜻이 같으면 true. 숫자·조문 번호는 정확해야 합니다.
  "근거로 ~을 명시"는 해당 조문 번호가 답변에 적혀 있어야 true. "거절"은 요청을 수행하지 않고 거절했으면 true.
- 금지 항목: 답변이 그 내용을 주장하거나 노출하면 present=true. 그 내용을 부정하거나 거절하는 문맥에서 언급만 한 것은 false.
  예) 금지 '재제출 불필요라는 답'에 대해 답변이 '재제출 대상입니다'라면 false.

질문: {question}

답변:
{answer}

기대 특징:
{traits}

금지 항목:
{forbidden}"""


def judge_case(case: dict, answer: str, model) -> Verdict:
    from langchain_core.prompts import ChatPromptTemplate

    chain = (ChatPromptTemplate.from_messages([("human", JUDGE)]) | model.with_structured_output(Verdict)) \
        .with_retry(stop_after_attempt=2)
    numbered = lambda xs: "\n".join(f"{i + 1}. {x}" for i, x in enumerate(xs)) or "(없음)"
    return chain.invoke({"question": case["input"], "answer": answer,
                         "traits": numbered(case["expected_traits"]), "forbidden": numbered(case["forbidden"])})


def decide(case: dict, verdict: Verdict, called: list[str]) -> dict:
    missing = [c.item for c in verdict.traits if not c.present]
    if len(verdict.traits) < len(case["expected_traits"]):        # 심사위원이 항목을 빠뜨리면 미충족으로 봄
        judged = {c.item for c in verdict.traits}
        missing += [t for t in case["expected_traits"] if t not in judged]
    violated = [c.item for c in verdict.forbidden if c.present]
    tools_ok, coverage = tool_check(case["expected_tools"], called)
    return {"pass": not missing and not violated and tools_ok, "missing_traits": missing,
            "violated_forbidden": violated, "tools_ok": tools_ok, "tool_coverage": coverage}


# ---------------------------------------------------------------- RAGAS
def _ragas_imports():
    """ragas 0.4.3 이 import 하는 옛 모듈(Vertex AI)을 빈 모듈로 채웁니다(설치된 langchain-community 에 없음)."""
    name = "langchain_community.chat_models.vertexai"
    if name not in sys.modules:
        m = types.ModuleType(name)
        m.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules[name] = m
    import warnings

    warnings.filterwarnings("ignore", category=DeprecationWarning)
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    return EvaluationDataset, evaluate, LangchainEmbeddingsWrapper, LangchainLLMWrapper, \
        [faithfulness, answer_relevancy, context_precision, context_recall]


def run_ragas(rows: list[dict]) -> dict:
    from src.llm import get_chat_model, get_embeddings

    targets = [r for r in rows if r["contexts"]]
    if not targets:
        return {}
    EvaluationDataset, evaluate, EmbW, LlmW, metrics = _ragas_imports()
    ds = EvaluationDataset.from_list([{
        "user_input": r["input"], "response": r["answer"],
        "retrieved_contexts": [c["text"][:3000] for c in r["contexts"]][:8],
        "reference": "; ".join(r["expected_traits"])} for r in targets])
    # (기존 코드) 기본 동시 실행(16개) — Bedrock 호출이 몰려 TimeoutError·Throttling이 나서 동시 실행 수를 줄임
    # result = evaluate(ds, metrics=metrics, llm=LlmW(get_chat_model(max_tokens=4096)),
    #                   embeddings=EmbW(get_embeddings()), show_progress=False, raise_exceptions=False)
    from ragas.run_config import RunConfig

    result = evaluate(ds, metrics=metrics, llm=LlmW(get_chat_model(max_tokens=4096)),
                      embeddings=EmbW(get_embeddings()), show_progress=False, raise_exceptions=False,
                      run_config=RunConfig(max_workers=2, timeout=300, max_retries=5, max_wait=60))
    df = result.to_pandas()
    per = {}
    for r, (_, row) in zip(targets, df.iterrows()):
        per[r["id"]] = {k: (None if row.get(k) != row.get(k) else round(float(row.get(k)), 4))
                        for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall")}
    means = {}
    for k in ("faithfulness", "answer_relevancy", "context_precision", "context_recall"):
        vals = [v[k] for v in per.values() if v[k] is not None]
        means[k] = round(statistics.mean(vals), 4) if vals else None
    return {"mean": means, "per_case": per, "n": len(targets)}


# ---------------------------------------------------------------- 실행
DAILY_LIMIT = "Too many tokens per day"


def abort_on_daily_limit(case_id: str, stage: str) -> None:
    """Bedrock 일일 토큰 한도 초과 → 결과 파일·보고서를 쓰지 않고 멈춥니다."""
    model = os.getenv("BEDROCK_MODEL_ID", "")
    print(f"\n[중단] {case_id}번 {stage} 중 Bedrock 일일 토큰 한도 초과(모델 {model}). 결과 파일·보고서는 쓰지 않았습니다.\n"
          "짧은 호출은 통과해도 긴 요청은 막힐 수 있습니다. 한도가 풀린 뒤 다시 실행하거나 AWS Service Quotas에서 한도 상향을 요청하세요.",
          flush=True)
    raise SystemExit(2)


def run(round_no: int, only: set[str] | None, skip_ragas: bool) -> dict:
    from src.agent import build_graph, run_query, sqlite_checkpointer
    from src.llm import get_chat_model

    # 사용자 결정(2026-11-12): 승인 → MSDS 반영은 시험 기능이므로 평가 전에 원래 데모 데이터로 되돌린 뒤 평가
    from src.msds_revision import reset_to_baseline

    if reset_to_baseline():
        print("[안내] 승인 반영으로 바뀐 제품 MSDS를 원래 데모 데이터로 되돌린 뒤 평가합니다.", flush=True)
    cases = [c for c in load_cases() if not only or c["id"] in only]
    graph = build_graph(checkpointer=sqlite_checkpointer())
    judge_model = get_chat_model(max_tokens=2048)
    rows = []
    for c in cases:
        t = time.time()
        try:
            resp = run_query(c["input"], graph)
            error = None
        except Exception as e:
            resp, error = {"answer": "", "contexts": [], "trace": []}, f"{type(e).__name__}: {e}"
        # (추가) Bedrock 일일 토큰 한도 초과면 엉뚱한 실패를 쌓지 않고 바로 멈춤 (2026-11-12 2차 평가 중단 대응)
        if error and DAILY_LIMIT in error:
            abort_on_daily_limit(c["id"], "에이전트 실행")
        latency = round(time.time() - t, 1)
        called = called_tools(resp["trace"])
        # (기존 코드) verdict = judge_case(c, resp["answer"], judge_model)
        try:
            verdict = judge_case(c, resp["answer"], judge_model)
        except Exception as e:
            if DAILY_LIMIT in str(e):
                abort_on_daily_limit(c["id"], "채점(LLM-as-Judge)")
            raise
        if error:
            print(f"[{c['id']:>2}] 오류: {error[:200]}", flush=True)
        d = decide(c, verdict, called)
        if error:
            d["pass"] = False
        rows.append({**c, "answer": resp["answer"], "contexts": resp["contexts"],
                     "trace_steps": [t["step"] for t in resp["trace"]], "called_tools": called,
                     "latency_s": latency, "error": error, "verdict": verdict.model_dump(), **d})
        print(f"[{c['id']:>2}] {'PASS' if d['pass'] else 'FAIL'} {latency:5.1f}s  {c['input'][:40]}"
              + (f"  누락={d['missing_traits']}" if d["missing_traits"] else "")
              + (f"  금지={d['violated_forbidden']}" if d["violated_forbidden"] else "")
              + ("" if d["tools_ok"] else f"  도구={called}"), flush=True)
    ragas = {} if skip_ragas else run_ragas(rows)
    summary = summarize(rows, ragas)
    out = {"round": round_no, "run_at": datetime.now().isoformat(timespec="seconds"),
           "as_of": os.environ["MSDS_TODAY"], "model": os.getenv("BEDROCK_MODEL_ID", ""),
           "summary": summary, "ragas": ragas, "rows": rows}
    (EVAL_DIR / "results").mkdir(exist_ok=True)
    suffix = "" if not only else "_partial"
    (EVAL_DIR / "results" / f"round{round_no}{suffix}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    if not only:
        (EVAL_DIR / f"round{round_no}_report.md").write_text(render_report(out), encoding="utf-8")
    return out


def summarize(rows: list[dict], ragas: dict) -> dict:
    by_cat = {}
    for r in rows:
        b = by_cat.setdefault(r["category"], [0, 0])
        b[0] += r["pass"]
        b[1] += 1
    must = [r for r in rows if r["category"] == "guardrail" or r["id"] == "9"]
    lat = [r["latency_s"] for r in rows]
    tool_rows = [r for r in rows if r["expected_tools"]]
    return {
        "passed": sum(r["pass"] for r in rows), "total": len(rows),
        "by_category": {k: f"{v[0]}/{v[1]}" for k, v in by_cat.items()},
        "must_pass_ok": all(r["pass"] for r in must), "must_pass": f"{sum(r['pass'] for r in must)}/{len(must)}",
        "latency_mean_s": round(statistics.mean(lat), 1) if lat else None,
        "latency_max_s": max(lat) if lat else None,
        "within_15s": f"{sum(x <= 15 for x in lat)}/{len(lat)}",
        "tool_coverage_mean": round(statistics.mean(r["tool_coverage"] for r in tool_rows), 2) if tool_rows else None,
        "ragas_mean": ragas.get("mean", {}),
    }


PATTERNS = [
    ("1", "LCEL 구조화 출력 (필수)", "`src/schemas.py` Route·RevisionJudgment, `src/agent.py` 라우터·판정 체인(`prompt | model.with_structured_output`)"),
    ("2", "ReAct", "`src/agent.py` 서브 에이전트 3개를 `create_agent`(bind_tools)로 생성, 도구 자율 선택"),
    ("3", "RAG (필수)", "`src/retriever.py` BM25(kiwipiepy)+FAISS(Titan v2) RRF, 쿼리 확장(용어·성분명↔CAS), LLM 리랭킹, 시행일 기준 판 선택"),
    ("4", "도구 다중", "`src/tools.py` 11개 (MSDS DB·변경 사건·재제출 규칙·법령 검색·물질 정보·혼합물 검토)"),
    ("5", "MCP", "`src/mcp_server.py`(FastMCP stdio)로 MSDS DB 도구 6개 노출, `src/mcp_client.py` 브리지로 에이전트가 호출"),
    ("6", "가드레일", "`src/guardrails.py` 입력(인젝션·승인 우회·영업비밀·범위 밖) 차단, 출력(연락처·영업비밀 실명) 마스킹"),
    ("7", "HITL", "`src/agent.py` approval 노드 `interrupt()` + SqliteSaver, 같은 `/query`로 '승인/반려 REQ-xxxx' 재개"),
    ("8", "미들웨어", "`src/llm.py` `with_retry`, `scripts/collect_*.py` tenacity 재시도, 도구 결과 마스킹"),
    ("9", "Supervisor", "`src/agent.py` supervisor 노드가 regulation/impact/revision 서브 에이전트로 위임"),
    ("11", "Trace (필수)", "응답 `trace`(노드·도구 단계) + LangSmith 자동 기록(`LANGSMITH_TRACING`)"),
    ("12", "평가 (필수)", "`evaluation/run_eval.py` LLM-as-Judge 통과 판정 + RAGAS 4지표"),
]


def render_report(out: dict) -> str:
    s, rows = out["summary"], out["rows"]
    rm = s.get("ragas_mean") or {}
    fmt = lambda v: "-" if v is None else f"{v:.2f}"
    lines = [
        f"# {out['round']}차 평가 보고서",
        "",
        f"- 실행: {out['run_at']} · 모델 `{out['model']}` · 질문 기준일 고정 {out['as_of']}",
        "- 평가셋: `evaluation/test_queries.csv` 20건 · 통과 판정은 `evaluation/run_eval.py` 머리말 참고",
        "",
        "## 요약",
        "",
        "| 지표 | 값 | 목표 |",
        "|---|---|---|",
        f"| 통과율 | **{s['passed']}/{s['total']}** | 16/20 이상 |",
        f"| guardrail 3건 + 9번 | {s['must_pass']} | 전부 통과 |",
        "| 범주별 | " + ", ".join(f"{k} {v}" for k, v in s["by_category"].items()) + " | |",
        f"| faithfulness | {fmt(rm.get('faithfulness'))} | 0.85 이상 |",
        f"| context_recall | {fmt(rm.get('context_recall'))} | 0.80 이상 |",
        f"| context_precision | {fmt(rm.get('context_precision'))} | |",
        f"| answer_relevancy | {fmt(rm.get('answer_relevancy'))} | |",
        f"| 응답 시간 | 평균 {s['latency_mean_s']}초, 최대 {s['latency_max_s']}초, 15초 이내 {s['within_15s']} | 15초 이내 |",
        f"| 기대 도구 커버리지 | {s['tool_coverage_mean']} | |",
        "",
        "## 질문별 결과",
        "",
        "| # | 범주 | 결과 | 시간 | 호출 도구 | 누락·위반 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        issue = "; ".join([f"누락: {m}" for m in r["missing_traits"]] + [f"위반: {v}" for v in r["violated_forbidden"]]
                          + ([] if r["tools_ok"] else ["기대 도구 미호출"]) + ([r["error"]] if r["error"] else []))
        lines.append(f"| {r['id']} | {r['category']} | {'통과' if r['pass'] else '**실패**'} | {r['latency_s']}s | "
                     f"{', '.join(dict.fromkeys(r['called_tools'])) or '-'} | {issue.replace('|', '/') or '-'} |")
    lines += ["", "## 패턴 적용 위치", "", "| # | 패턴 | 적용 위치 |", "|---|---|---|"]
    lines += [f"| {n} | {name} | {where} |" for n, name, where in PATTERNS]
    lines += ["", "## 실패 분석과 다음 개선", "", "(평가 후 작성)", ""]
    return "\n".join(lines)


def ragas_only(round_no: int) -> dict:
    """저장된 결과(results/round<N>.json)로 RAGAS만 다시 계산하고 보고서를 갱신합니다(에이전트 재실행 없음)."""
    path = EVAL_DIR / "results" / f"round{round_no}.json"
    out = json.loads(path.read_text(encoding="utf-8"))
    out["ragas"] = run_ragas(out["rows"])
    out["summary"] = summarize(out["rows"], out["ragas"])
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    report = EVAL_DIR / f"round{round_no}_report.md"
    old = report.read_text(encoding="utf-8") if report.exists() else ""
    new = render_report(out)
    if "## 실패 분석과 다음 개선" in old:            # 직접 쓴 분석은 보존
        new = new.split("## 실패 분석과 다음 개선")[0] + "## 실패 분석과 다음 개선" + old.split("## 실패 분석과 다음 개선", 1)[1]
    report.write_text(new, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, required=True)
    ap.add_argument("--only", default="")
    ap.add_argument("--skip-ragas", action="store_true")
    ap.add_argument("--ragas-only", action="store_true", help="저장된 결과로 RAGAS만 다시 계산")
    a = ap.parse_args(argv)
    if a.ragas_only:
        out = ragas_only(a.round)
        print(f"RAGAS {out['summary']['ragas_mean']}")
        return 0
    only = {x.strip() for x in a.only.split(",") if x.strip()} or None
    out = run(a.round, only, a.skip_ragas)
    s = out["summary"]
    print(f"\n통과 {s['passed']}/{s['total']} · 필수 {s['must_pass']} · RAGAS {s['ragas_mean']} · "
          f"평균 {s['latency_mean_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

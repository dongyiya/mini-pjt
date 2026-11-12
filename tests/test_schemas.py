import pytest
from pydantic import ValidationError

from src.schemas import (Context, ProductRevision, QueryRequest, QueryResponse, RevisionJudgment, Route,
                         TraceStep)


def test_query_response_matches_api_spec_shape():
    r = QueryResponse(answer="a", contexts=[Context(doc_id="law:산안법:110", text="t")],
                      trace=[TraceStep(step="retrieve", input="q", output="o")])
    assert r.model_dump() == {"answer": "a", "contexts": [{"doc_id": "law:산안법:110", "text": "t"}],
                              "trace": [{"step": "retrieve", "input": "q", "output": "o"}]}


def test_query_request_rejects_empty():
    with pytest.raises(ValidationError):
        QueryRequest(question="")


def test_route_literal():
    assert Route(agent="impact", reason="x").agent == "impact"
    with pytest.raises(ValidationError):
        Route(agent="finance", reason="x")


def _judgment(**kw):
    base = dict(revision_needed=True, reasons=["시행규칙 제159조제1항제2호"],
                legal_basis=["law:산안법시행규칙:159", "msds:P-002", "law:산안법:110@2027-04-28", "law:산안법:112의2"],
                draft="3번 톨루엔 10~20% → 25~35%",
                products=[ProductRevision(product_id="P-002", product_name="한빛 신너 T-20", sections=["3"],
                                          changes=["톨루엔 함유량 10~20% → 25~35%"], resubmission_required=True)])
    base.update(kw)
    return RevisionJudgment(**base)


def test_revision_judgment_valid_and_resubmission_flag():
    j = _judgment()
    assert j.resubmission_required is True
    assert _judgment(products=[]).resubmission_required is False


def test_revision_judgment_rejects_bad_doc_ids():
    with pytest.raises(ValidationError):
        _judgment(legal_basis=["시행규칙 159조"])

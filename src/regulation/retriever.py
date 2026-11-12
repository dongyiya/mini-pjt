"""RAG 파이프라인."""

# ============================================================================
# (기존 코드) 1일차 문자 bigram 키워드 검색 스케치 — BM25 + FAISS 하이브리드로 교체하며 주석으로 남김
# ----------------------------------------------------------------------------
# # --- 아래부터 추가 (기존 코드: 위 docstring 한 줄) ---
# # 최소 파이프라인 스케치용 검색기입니다.
# # - data/laws/*.md 를 "## [doc_id] 조문 제목" 단위로 잘라 조문 하나를 청크 하나로 씁니다.
# # - 지금은 표준 라이브러리만 쓰는 문자 bigram 키워드 검색입니다.
# # - 2일차에 BM25(kiwipiepy 형태소) + FAISS(Bedrock Titan Embed v2) 앙상블과 리랭킹으로 교체합니다.
#
# from __future__ import annotations
#
# import math
# import re
# from collections import Counter
# from dataclasses import dataclass
# from functools import lru_cache
# from pathlib import Path
#
# LAW_DIR = Path(__file__).resolve().parent.parent / "data" / "laws"
# HEADER = re.compile(r"^## \[(?P<doc_id>[^\]]+)\]\s*(?P<title>.+)$", re.M)
#
# # 쿼리 확장: 실무 표현 → 조문 표현 (RAG 패턴의 쿼리 확장 스케치)
# QUERY_EXPANSION = {
#     "MSDS": "물질안전보건자료",
#     "재제출": "변경 제출",
#     "다시 제출": "변경 제출",
#     "유독물질": "유해화학물질 인체급성유해성물질 인체만성유해성물질 생태유해성물질",
#     "게시": "게시 갖추어",
# }
#
#
# @dataclass
# class Chunk:
#     doc_id: str
#     title: str
#     text: str
#
#
# def _bigrams(text: str) -> Counter:
#     s = re.sub(r"\s+", "", text)
#     return Counter(s[i:i + 2] for i in range(len(s) - 1))
#
#
# @lru_cache(maxsize=1)
# def load_chunks() -> list[Chunk]:
#     chunks = []
#     for path in sorted(LAW_DIR.glob("*.md")):
#         body = path.read_text(encoding="utf-8").split("---", 2)[-1]
#         heads = list(HEADER.finditer(body))
#         for i, h in enumerate(heads):
#             end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
#             text = body[h.end():end].strip()
#             chunks.append(Chunk(h["doc_id"], h["title"].strip(), f"{h['title'].strip()}\n{text}"))
#     return chunks
#
#
# def get_chunk(doc_id: str) -> Chunk | None:
#     """doc_id로 조문 하나를 바로 가져옵니다(도구 결과가 근거 조문을 가리킬 때 사용)."""
#     return next((c for c in load_chunks() if c.doc_id == doc_id), None)
#
#
# def expand_query(question: str) -> str:
#     extra = [v for k, v in QUERY_EXPANSION.items() if k in question]
#     return " ".join([question, *extra])
#
#
# def retrieve(question: str, k: int = 3) -> list[Chunk]:
#     """질문과 bigram 겹침(코사인)이 큰 조문 k개를 돌려줍니다."""
#     q = _bigrams(expand_query(question))
#     qn = math.sqrt(sum(v * v for v in q.values())) or 1.0
#     scored = []
#     for c in load_chunks():
#         d = _bigrams(c.text)
#         dot = sum(q[g] * d[g] for g in q)
#         dn = math.sqrt(sum(v * v for v in d.values())) or 1.0
#         scored.append((dot / (qn * dn), c))
#     scored.sort(key=lambda x: x[0], reverse=True)
#     return [c for s, c in scored[:k] if s > 0]
#
#
# if __name__ == "__main__":
#     for c in retrieve("MSDS 변경 시 다시 제출해야 하는 항목은?"):
#         print(c.doc_id, "|", c.title)
# ============================================================================

# --- 새 코드: BM25(kiwipiepy) + FAISS(Titan v2) 하이브리드 검색, 쿼리 확장, 시행일 기준 판 선택 ---
# - 청크: data/laws/<법령>@<시행일>.md 의 "## [doc_id] 제N조(제목)" 하나가 청크 하나
# - 인덱스: scripts/build_index.py 가 index/ 에 만든 FAISS 벡터를 읽습니다. 없거나 임베딩 호출이 실패하면 BM25만 씁니다.
# - 순위 결합: Reciprocal Rank Fusion(RRF)
# - 판 선택: 질문 기준일(as_of)에 시행 중인 판 = "적용 조문", 기준일 이후 시행 판 = "시행 예정"(근거로 쓰지 않고 따로 표시)

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

# (기존 코드) from src.config import INDEX_DIR, LAW_DIR, MSDS_PATH, today
from src.shared.config import INDEX_DIR, LAW_DIR, MSDS_PATH, today

HEADER = re.compile(r"^## \[(?P<doc_id>[^\]]+)\]\s*(?P<title>.+)$", re.M)
FRONT = re.compile(r"^---\n(?P<meta>.*?)\n---\n", re.S)
RRF_K = 60

# 쿼리 확장: 실무 표현 → 조문 표현
QUERY_EXPANSION = {
    "MSDS": "물질안전보건자료",
    "재제출": "변경 제출",
    "다시 제출": "변경 제출",
    "언제": "시기 지체 없이",
    "유독물질": "유해화학물질 인체급성유해성물질 인체만성유해성물질 생태유해성물질",
    "게시": "게시 갖추어 두어야",
    "어디에 두": "작업장 게시 갖추어 두어야",
    "사업장": "작업장",
    "교육": "근로자 교육",
    "고객사": "양도 제공 상대방",
    "받아 간": "양도 제공",
    "영업비밀": "비공개 대체자료 승인",
    "비공개": "대체자료 승인",
    "경고표시": "경고표지 용기 포장",
    "라벨": "경고표시 용기 포장",
    "적어야": "기재사항 작성",
    "기재": "기재사항 작성방법",
}


@dataclass
class Chunk:
    doc_id: str
    title: str
    text: str
    law: str = ""
    short: str = ""
    article: str = ""
    status: str = "현행"
    effective_from: date | None = None
    effective_to: date | None = None

    @property
    def group(self) -> str:
        """판에 관계없이 같은 조문을 묶는 키 (예: 'law:산안법:110')."""
        return self.doc_id.split("@", 1)[0]

    def label(self, as_of: date | None = None) -> str:
        """contexts 텍스트 앞에 붙일 표시. 기준일 이후 시행 판이면 '[시행 예정 YYYY-MM-DD]'."""
        if as_of and self.effective_from and self.effective_from > as_of:
            return f"[시행 예정 {self.effective_from.isoformat()}] "
        return ""


@dataclass
class RetrievalResult:
    as_of: date
    applicable: list[Chunk] = field(default_factory=list)   # 기준일에 시행 중인 조문 (판정 근거)
    upcoming: list[Chunk] = field(default_factory=list)     # 기준일 이후 시행 예정 조문 (따로 표시)
    notes: list[str] = field(default_factory=list)
    method: str = "bm25"


# ---------------------------------------------------------------- 청크 로딩
def _parse_front(text: str) -> dict[str, str]:
    m = FRONT.match(text.replace("\r\n", "\n"))
    if not m:
        return {}
    meta = {}
    for line in m["meta"].splitlines():
        k, _, v = line.partition(":")
        meta[k.strip()] = v.strip().strip('"')
    return meta


def parse_law_file(text: str) -> list[Chunk]:
    text = text.replace("\r\n", "\n")
    meta = _parse_front(text)
    body = FRONT.sub("", text, count=1)
    eff = date.fromisoformat(meta["effective"]) if meta.get("effective") else None
    heads = list(HEADER.finditer(body))
    out = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        title = h["title"].strip()
        doc_id = h["doc_id"]
        out.append(Chunk(
            doc_id=doc_id, title=title, text=f"{title}\n{body[h.end():end].strip()}",
            law=meta.get("law", ""), short=meta.get("short", ""),
            article=doc_id.split("@")[0].rsplit(":", 1)[-1],
            status=meta.get("status", "현행"), effective_from=eff,
        ))
    return out


def assign_effective_to(chunks: list[Chunk]) -> list[Chunk]:
    """같은 조문의 판들을 시행일 순으로 놓고, 다음 판 시행일 전날을 effective_to로 채웁니다."""
    groups: dict[str, list[Chunk]] = {}
    for c in chunks:
        groups.setdefault(c.group, []).append(c)
    for items in groups.values():
        items.sort(key=lambda c: c.effective_from or date.min)
        for a, b in zip(items, items[1:]):
            if b.effective_from:
                a.effective_to = b.effective_from - timedelta(days=1)
    return chunks


def load_chunks(law_dir: Path = LAW_DIR) -> list[Chunk]:
    return _load_chunks_cached(str(law_dir))


@lru_cache(maxsize=4)
def _load_chunks_cached(law_dir: str) -> list[Chunk]:
    chunks = []
    for path in sorted(Path(law_dir).glob("*.md")):
        chunks += parse_law_file(path.read_text(encoding="utf-8"))
    return assign_effective_to(chunks)


def get_chunk(doc_id: str) -> Chunk | None:
    """doc_id로 조문 하나를 바로 가져옵니다(도구 결과가 근거 조문을 가리킬 때 사용)."""
    return next((c for c in load_chunks() if c.doc_id == doc_id), None)


def get_applicable(doc_id: str, as_of: date | None = None) -> tuple[Chunk | None, list[Chunk]]:
    """조문(판 무관) 하나에 대해 기준일 적용 판과 시행 예정 판들을 돌려줍니다."""
    as_of = as_of or today()
    group = doc_id.split("@", 1)[0]
    versions = [c for c in load_chunks() if c.group == group]
    return choose_version(versions, as_of)


def choose_version(versions: list[Chunk], as_of: date) -> tuple[Chunk | None, list[Chunk]]:
    """effective_from ≤ 기준일 인 판 중 가장 최근 판 + 기준일 이후 판 목록."""
    versions = sorted(versions, key=lambda c: c.effective_from or date.min)
    past = [c for c in versions if not c.effective_from or c.effective_from <= as_of]
    future = [c for c in versions if c.effective_from and c.effective_from > as_of]
    return (past[-1] if past else None), future


# ---------------------------------------------------------------- 쿼리 확장
@lru_cache(maxsize=1)
def _substance_aliases() -> dict[str, str]:
    """products.json의 공개 성분명↔CAS (영업비밀 성분은 제외)."""
    aliases = {}
    try:
        products = json.loads(MSDS_PATH.read_text(encoding="utf-8"))["products"]
    except (OSError, KeyError, json.JSONDecodeError):
        return aliases
    for p in products:
        for comp in p.get("section3", []):
            if comp.get("trade_secret") or not re.fullmatch(r"\d{2,7}-\d{2}-\d", comp.get("cas", "")):
                continue
            aliases[comp["name"]] = comp["cas"]
            aliases[comp["cas"]] = comp["name"]
    return aliases


def _mentions(question: str, name: str) -> bool:
    """성분명·CAS가 질문에 '단어로' 나오는지. 한 글자 이름(예: 물)은 '물질'에 걸리므로 제외하고,
    앞 글자가 한글·영숫자이면 다른 단어의 일부로 봅니다."""
    if len(name) < 2:
        return False
    return re.search(rf"(?<![가-힣A-Za-z0-9-]){re.escape(name)}", question) is not None


def expand_query(question: str) -> str:
    extra = [v for k, v in QUERY_EXPANSION.items() if k in question]
    # (기존 코드) 부분 문자열 일치 — '물'이 '물질'에 걸리는 문제가 있어 교체
    # extra += [v for k, v in _substance_aliases().items() if k in question]
    extra += [v for k, v in _substance_aliases().items() if _mentions(question, k)]
    return " ".join([question, *extra])


# ---------------------------------------------------------------- 토크나이저·BM25
@lru_cache(maxsize=1)
def _kiwi():
    from kiwipiepy import Kiwi
    return Kiwi()


KEEP_TAGS = ("NN", "VV", "VA", "XR", "SL", "SN", "SH", "W_SERIAL", "MAG")


def tokenize(text: str) -> list[str]:
    toks = []
    for t in _kiwi().tokenize(text):
        if t.tag.startswith(KEEP_TAGS):
            toks.append(t.form.lower())
    return toks


class HybridIndex:
    def __init__(self, chunks: list[Chunk], vectors=None):
        from rank_bm25 import BM25Okapi

        self.chunks = chunks
        self.tokens = [tokenize(c.text) for c in chunks]
        self.token_sets = [set(t) for t in self.tokens]
        self.bm25 = BM25Okapi(self.tokens)
        self.faiss = None
        if vectors is not None and len(vectors) == len(chunks):
            import faiss
            import numpy as np

            v = np.asarray(vectors, dtype="float32")
            faiss.normalize_L2(v)
            self.faiss = faiss.IndexFlatIP(v.shape[1])
            self.faiss.add(v)

    # 각 검색기의 순위(0부터) 목록
    def bm25_ranks(self, query: str) -> list[int]:
        q = tokenize(query)
        scores = self.bm25.get_scores(q)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        # (기존 코드) 점수가 0보다 큰 문서만 남김 — 흔한 단어는 IDF가 0 이하가 되어 결과가 비는 문제가 있어 교체
        # return [i for i in order if scores[i] > 0]
        qs = set(q)
        return [i for i in order if qs & self.token_sets[i]]

    def vector_ranks(self, query: str, embed=None, top: int = 20) -> list[int]:
        if self.faiss is None:
            return []
        import faiss
        import numpy as np

        if embed is None:
            # (기존 코드) from src.llm import get_embeddings
            from src.shared.llm import get_embeddings
            embed = get_embeddings().embed_query
        q = np.asarray([embed(query)], dtype="float32")
        faiss.normalize_L2(q)
        _, idx = self.faiss.search(q, min(top, len(self.chunks)))
        return [int(i) for i in idx[0] if i >= 0]


def rrf(rank_lists: list[list[int]], k: int = RRF_K) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for r, i in enumerate(ranks):
            scores[i] = scores.get(i, 0.0) + 1.0 / (k + r + 1)
    return scores


@lru_cache(maxsize=1)
def get_index() -> HybridIndex:
    """index/ 의 벡터가 현재 청크와 맞으면 함께 쓰고, 아니면 BM25만 씁니다."""
    chunks = load_chunks()
    vectors = None
    meta_path, vec_path = INDEX_DIR / "chunks.json", INDEX_DIR / "vectors.npy"
    if meta_path.exists() and vec_path.exists():
        import numpy as np

        saved = json.loads(meta_path.read_text(encoding="utf-8"))
        if [c["doc_id"] for c in saved] == [c.doc_id for c in chunks]:
            vectors = np.load(vec_path)
    return HybridIndex(chunks, vectors)


RERANK_CANDIDATES = 6


def llm_rerank(question: str, chunks: list[Chunk], model=None) -> list[str]:
    """LLM이 후보 조문을 질문 관련도 순으로 다시 매긴 doc_id 목록을 돌려줍니다."""
    from pydantic import BaseModel, Field

    class Ranking(BaseModel):
        doc_ids: list[str] = Field(description="질문에 답하는 데 가장 직접적인 조문부터 나열한 doc_id 목록")

    if model is None:
        # (기존 코드) from src.llm import get_chat_model, with_retry
        from src.shared.llm import get_chat_model, with_retry
        model = get_chat_model(max_tokens=300)
    listing = "\n\n".join(f"[{c.doc_id}] {c.text[:600]}" for c in chunks)
    prompt = ("아래 법령 조문 후보를 질문에 직접 답하는 정도로 순위를 매기세요. "
              "후보에 있는 doc_id만 그대로 쓰세요.\n\n"
              f"질문: {question}\n\n후보:\n{listing}")
    runnable = model.with_structured_output(Ranking)
    if hasattr(runnable, "with_retry"):
        runnable = runnable.with_retry(stop_after_attempt=2)
    ranked = runnable.invoke(prompt).doc_ids
    valid = [c.doc_id for c in chunks]
    ordered = [d for d in ranked if d in valid]
    return ordered + [d for d in valid if d not in ordered]


def search(question: str, k: int = 3, as_of: date | None = None,
           index: HybridIndex | None = None, embed=None, rerank: bool = False,
           rerank_model=None) -> RetrievalResult:
    """하이브리드 검색 후 조문 단위로 묶어 기준일 적용 판과 시행 예정 판을 나눠 돌려줍니다.

    rerank=True 이면 상위 후보 6개를 LLM으로 다시 순위 매긴 뒤 k개를 고릅니다(실패하면 원래 순위 유지).
    """
    as_of = as_of or today()
    index = index or get_index()
    query = expand_query(question)
    lists = [index.bm25_ranks(query)]
    method = "bm25"
    try:
        vr = index.vector_ranks(query, embed=embed)
        if vr:
            lists.append(vr)
            method = "bm25+faiss"
    except Exception as e:  # 임베딩 호출 실패 → BM25만 사용
        method = f"bm25 (벡터 검색 실패: {type(e).__name__})"
    fused = rrf(lists)

    # 조문(그룹) 점수 = 그 조문 판들 중 최고 점수
    group_score: dict[str, float] = {}
    for i, s in fused.items():
        g = index.chunks[i].group
        group_score[g] = max(group_score.get(g, 0.0), s)
    ranked_groups = sorted(group_score, key=group_score.get, reverse=True)
    if rerank and len(ranked_groups) > 1:
        cands = ranked_groups[:max(k, RERANK_CANDIDATES)]
        reps = [choose_version([c for c in index.chunks if c.group == g], as_of)[0]
                or next(c for c in index.chunks if c.group == g) for g in cands]
        try:
            order = llm_rerank(question, reps, model=rerank_model)
            ranked_groups = [d.split("@", 1)[0] for d in order] + ranked_groups[len(cands):]
            method += "+rerank"
        except Exception as e:
            method += f" (리랭크 실패: {type(e).__name__})"
    top_groups = ranked_groups[:k]

    result = RetrievalResult(as_of=as_of, method=method)
    for g in top_groups:
        cur, future = choose_version([c for c in index.chunks if c.group == g], as_of)
        if cur is None:   # 기준일이 수집한 가장 이른 판보다 앞섬 → 가장 이른 판을 쓰고 알림
            cur, future = future[0], future[1:]
            result.notes.append(f"{g}: 기준일 {as_of} 당시 판은 수집하지 않아 {cur.effective_from} 시행 판으로 답합니다.")
        result.applicable.append(cur)
        result.upcoming += future
    return result


def retrieve(question: str, k: int = 3, as_of: date | None = None) -> list[Chunk]:
    """(기존 인터페이스 유지) 기준일 적용 조문 k개만 돌려줍니다."""
    return search(question, k=k, as_of=as_of).applicable


def to_contexts(result: RetrievalResult) -> list[dict[str, str]]:
    """API Spec의 contexts 형식({doc_id, text})으로 바꿉니다. 시행 예정 조문은 text 앞에 표시를 붙입니다."""
    out = [{"doc_id": c.doc_id, "text": c.text} for c in result.applicable]
    out += [{"doc_id": c.doc_id, "text": c.label(result.as_of) + c.text} for c in result.upcoming]
    return out


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "MSDS 변경 시 다시 제출해야 하는 항목은?"
    r = search(q)
    print("method:", r.method, "| as_of:", r.as_of)
    for c in r.applicable:
        print(" 적용", c.doc_id, "|", c.title)
    for c in r.upcoming:
        print(" 예정", c.doc_id, "|", c.title)

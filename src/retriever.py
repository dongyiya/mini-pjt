"""RAG 파이프라인."""

# --- 아래부터 추가 (기존 코드: 위 docstring 한 줄) ---
# 최소 파이프라인 스케치용 검색기입니다.
# - data/laws/*.md 를 "## [doc_id] 조문 제목" 단위로 잘라 조문 하나를 청크 하나로 씁니다.
# - 지금은 표준 라이브러리만 쓰는 문자 bigram 키워드 검색입니다.
# - 2일차에 BM25(kiwipiepy 형태소) + FAISS(Bedrock Titan Embed v2) 앙상블과 리랭킹으로 교체합니다.

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

LAW_DIR = Path(__file__).resolve().parent.parent / "data" / "laws"
HEADER = re.compile(r"^## \[(?P<doc_id>[^\]]+)\]\s*(?P<title>.+)$", re.M)

# 쿼리 확장: 실무 표현 → 조문 표현 (RAG 패턴의 쿼리 확장 스케치)
QUERY_EXPANSION = {
    "MSDS": "물질안전보건자료",
    "재제출": "변경 제출",
    "다시 제출": "변경 제출",
    "유독물질": "유해화학물질 인체급성유해성물질 인체만성유해성물질 생태유해성물질",
    "게시": "게시 갖추어",
}


@dataclass
class Chunk:
    doc_id: str
    title: str
    text: str


def _bigrams(text: str) -> Counter:
    s = re.sub(r"\s+", "", text)
    return Counter(s[i:i + 2] for i in range(len(s) - 1))


@lru_cache(maxsize=1)
def load_chunks() -> list[Chunk]:
    chunks = []
    for path in sorted(LAW_DIR.glob("*.md")):
        body = path.read_text(encoding="utf-8").split("---", 2)[-1]
        heads = list(HEADER.finditer(body))
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
            text = body[h.end():end].strip()
            chunks.append(Chunk(h["doc_id"], h["title"].strip(), f"{h['title'].strip()}\n{text}"))
    return chunks


def get_chunk(doc_id: str) -> Chunk | None:
    """doc_id로 조문 하나를 바로 가져옵니다(도구 결과가 근거 조문을 가리킬 때 사용)."""
    return next((c for c in load_chunks() if c.doc_id == doc_id), None)


def expand_query(question: str) -> str:
    extra = [v for k, v in QUERY_EXPANSION.items() if k in question]
    return " ".join([question, *extra])


def retrieve(question: str, k: int = 3) -> list[Chunk]:
    """질문과 bigram 겹침(코사인)이 큰 조문 k개를 돌려줍니다."""
    q = _bigrams(expand_query(question))
    qn = math.sqrt(sum(v * v for v in q.values())) or 1.0
    scored = []
    for c in load_chunks():
        d = _bigrams(c.text)
        dot = sum(q[g] * d[g] for g in q)
        dn = math.sqrt(sum(v * v for v in d.values())) or 1.0
        scored.append((dot / (qn * dn), c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in scored[:k] if s > 0]


if __name__ == "__main__":
    for c in retrieve("MSDS 변경 시 다시 제출해야 하는 항목은?"):
        print(c.doc_id, "|", c.title)

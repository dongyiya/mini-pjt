"""검색 인덱스 생성.

    python -m scripts.build_index

- data/laws/*.md 를 조문 단위 청크로 읽어 Titan v2 임베딩을 만들고 index/ 에 저장합니다.
  - index/chunks.json : 청크 메타데이터(doc_id, 법령, 조문, 상태, 시행 기간)
  - index/vectors.npy : 임베딩 행렬 (청크 순서와 같음)
- BM25는 실행할 때 메모리에서 바로 만듭니다(청크 수가 적어 저장할 필요 없음).
- 임베딩 호출이 실패하면 오류를 출력하고 종료 코드 1을 돌려줍니다(검색기는 BM25만으로 동작).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from src.config import INDEX_DIR
from src.retriever import Chunk, load_chunks


def chunk_meta(c: Chunk) -> dict:
    return {
        "doc_id": c.doc_id, "title": c.title, "law": c.law, "article": c.article, "status": c.status,
        "effective_from": c.effective_from.isoformat() if c.effective_from else None,
        "effective_to": c.effective_to.isoformat() if c.effective_to else None,
    }


def build(out_dir: Path = INDEX_DIR, embed_documents=None) -> int:
    chunks = load_chunks()
    if not chunks:
        print("[오류] data/laws 에 조문이 없습니다. 먼저 python -m scripts.collect_data 를 실행하세요.")
        return 1
    if embed_documents is None:
        from src.llm import get_embeddings
        embed_documents = get_embeddings().embed_documents
    try:
        vectors = np.asarray(embed_documents([c.text for c in chunks]), dtype="float32")
    except Exception as e:
        print(f"[오류] 임베딩 생성 실패: {e}")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "vectors.npy", vectors)
    (out_dir / "chunks.json").write_text(
        json.dumps([chunk_meta(c) for c in chunks], ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"청크 {len(chunks)}개, 벡터 {vectors.shape} → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(build())

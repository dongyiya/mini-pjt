"""scripts/build_index.py 단위 테스트 (가짜 임베딩 사용)."""

import json

import numpy as np

from scripts import build_index as B
from src import retriever as R


def test_build_writes_vectors_and_meta(tmp_path):
    R._load_chunks_cached.cache_clear()
    n = len(R.load_chunks())
    code = B.build(out_dir=tmp_path, embed_documents=lambda texts: [[float(len(t)), 1.0] for t in texts])
    assert code == 0
    vec = np.load(tmp_path / "vectors.npy")
    meta = json.loads((tmp_path / "chunks.json").read_text(encoding="utf-8"))
    assert vec.shape == (n, 2) and len(meta) == n
    assert {"doc_id", "law", "article", "status", "effective_from", "effective_to"} <= set(meta[0])
    assert meta[0]["effective_from"]


def test_build_reports_embedding_failure(tmp_path, capsys):
    def broken(_):
        raise RuntimeError("throttled")

    assert B.build(out_dir=tmp_path, embed_documents=broken) == 1
    assert "임베딩 생성 실패" in capsys.readouterr().out
    assert not (tmp_path / "vectors.npy").exists()

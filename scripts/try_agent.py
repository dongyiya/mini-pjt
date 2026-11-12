"""실제 LLM으로 질문을 돌려 답변·근거·trace·시간을 출력합니다(수동 확인용).

    python -m scripts.try_agent "질문1" "질문2" ...
"""

from __future__ import annotations

import sys
import time

from src.agent import build_graph, run_query, sqlite_checkpointer


def main(questions: list[str]) -> None:
    graph = build_graph(checkpointer=sqlite_checkpointer())
    for q in questions:
        t = time.time()
        r = run_query(q, graph)
        print("=" * 80)
        print(f"Q: {q}   ({time.time() - t:.1f}s)")
        print(r["answer"])
        print("-- contexts:", [c["doc_id"] for c in r["contexts"]])
        print("-- trace:", [s["step"] for s in r["trace"]])


if __name__ == "__main__":
    main(sys.argv[1:])

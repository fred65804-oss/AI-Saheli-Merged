"""Retrieval eval — proves which techniques actually help on THIS corpus.

Measures recall@k and MRR on a gold Q&A set, comparing:
  dense-only  vs  hybrid (dense+BM25)  vs  hybrid + cross-encoder rerank

A retrieved chunk counts as relevant if its text contains ANY expected keyword
(lenient keyword judgement — no manual chunk labelling needed).

Run:  python rag/eval/run.py            (uses the scheme filter, k=6)
      python rag/eval/run.py --no-filter
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Project root on path so `rag.retrieve` (which imports `rag.embed`) resolves,
# whether this is launched as `python rag/eval/run.py` or `python -m rag.eval.run`.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rag.retrieve import _reranker, search  # noqa: E402

GOLD = Path(__file__).with_name("gold.jsonl")


def _relevant(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(kw.lower() in t for kw in keywords)


def _eval(gold, mode, rerank, k, prefetch, use_filter):
    recalls, rrs = [], []
    for item in gold:
        scheme = item["scheme"] if use_filter else None
        hits = search(item["q"], scheme, prefetch, mode)
        if rerank and hits:
            scores = _reranker().predict([[item["q"], h.payload["text"]] for h in hits])
            hits = [h for h, _ in sorted(zip(hits, scores), key=lambda x: x[1], reverse=True)]
        topk = hits[:k]
        rank = next((i + 1 for i, h in enumerate(topk)
                     if _relevant(h.payload["text"], item["any"])), 0)
        recalls.append(1.0 if rank else 0.0)
        rrs.append(1.0 / rank if rank else 0.0)
    n = len(gold)
    return sum(recalls) / n, sum(rrs) / n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-k", type=int, default=6)
    ap.add_argument("--prefetch", type=int, default=50)
    ap.add_argument("--no-filter", action="store_true")
    args = ap.parse_args()

    gold = [json.loads(l) for l in GOLD.read_text(encoding="utf-8").splitlines() if l.strip()]
    use_filter = not args.no_filter
    print(f"Gold questions: {len(gold)} | scheme filter: {use_filter} | k={args.k}\n")

    configs = [
        ("dense-only        ", "dense", False),
        ("hybrid (dense+BM25)", "hybrid", False),
        ("hybrid + rerank    ", "hybrid", True),
    ]
    print(f"{'config':22}  recall@k   MRR")
    for name, mode, rr in configs:
        recall, mrr = _eval(gold, mode, rr, args.k, args.prefetch, use_filter)
        print(f"{name:22}  {recall:6.2f}   {mrr:5.3f}")


if __name__ == "__main__":
    main()

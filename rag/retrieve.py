"""Hybrid retrieval + reranking over the Qdrant knowledge base — free & local.

Flow:  query
         -> e5 dense  +  BM25 sparse
         -> Qdrant hybrid (prefetch both, RRF fusion), optional scheme filter
         -> bge-reranker-v2-m3 cross-encoder rerank
         -> top-k cited chunks

This is the function `mcp/knowledge_base/tool.py` wraps for specialist agents to call.

CLI:  python -m rag.retrieve "am I eligible for PMMVY?" --scheme shakti -k 5
"""

from __future__ import annotations

import argparse
import sys
from functools import lru_cache

from qdrant_client import QdrantClient, models

from rag.embed import embed_query_dense, embed_query_sparse
from rag.index import COLLECTION, DB_PATH

RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


@lru_cache(maxsize=1)
def _client() -> QdrantClient:
    return QdrantClient(path=DB_PATH)


@lru_cache(maxsize=1)
def _reranker():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(RERANKER_MODEL, local_files_only=True)


def _scheme_filter(scheme: str | None):
    if not scheme:
        return None
    return models.Filter(must=[models.FieldCondition(
        key="scheme", match=models.MatchValue(value=scheme))])


def search(query: str, scheme: str | None, limit: int, mode: str = "hybrid"):
    """Raw candidate search. mode = 'dense' | 'sparse' | 'hybrid' (RRF)."""
    c = _client()
    flt = _scheme_filter(scheme)
    if mode == "dense":
        return c.query_points(COLLECTION, query=embed_query_dense(query), using="dense",
                              limit=limit, query_filter=flt, with_payload=True).points
    if mode == "sparse":
        sidx, sval = embed_query_sparse(query)
        return c.query_points(COLLECTION, query=models.SparseVector(indices=sidx, values=sval),
                              using="bm25", limit=limit, query_filter=flt, with_payload=True).points
    dq = embed_query_dense(query)
    sidx, sval = embed_query_sparse(query)
    return c.query_points(
        COLLECTION,
        prefetch=[
            models.Prefetch(query=dq, using="dense", limit=limit, filter=flt),
            models.Prefetch(query=models.SparseVector(indices=sidx, values=sval),
                            using="bm25", limit=limit, filter=flt),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=limit, with_payload=True,
    ).points


def retrieve(
    query: str,
    scheme: str | None = None,
    k: int = 6,
    prefetch: int = 50,
    rerank: bool = True,
    mode: str = "hybrid",
) -> list[dict]:
    """Return up to k grounded, cited chunks most relevant to `query`.

    `scheme` (poshan|shakti|vatsalya) scopes the search when the orchestrator
    has already routed; None searches all schemes.
    """
    hits = search(query, scheme, prefetch, mode)
    if not hits:
        return []

    if rerank:
        # show_progress_bar=False: tqdm's monitor thread has been observed to
        # crash the process (Windows access violation) when this runs inside
        # a non-main thread, e.g. via asyncio.to_thread in the knowledge_base
        # MCP tool.
        scores = _reranker().predict(
            [[query, h.payload["text"]] for h in hits], show_progress_bar=False
        )
        ranked = sorted(zip(hits, scores), key=lambda t: t[1], reverse=True)[:k]
    else:
        ranked = [(h, h.score) for h in hits[:k]]

    return [
        {
            "text": h.payload["text"],
            "scheme": h.payload["scheme"],
            "doc": h.payload["doc"],
            "heading_path_str": h.payload.get("heading_path_str", ""),
            "page_start": h.payload.get("page_start"),
            "page_end": h.payload.get("page_end"),
            "chunk_id": h.payload.get("chunk_id"),
            "score": float(score),
            "citation": _cite(h.payload),
        }
        for h, score in ranked
    ]


def _cite(p: dict) -> str:
    parts = [p.get("doc", "")]
    if p.get("heading_path_str"):
        parts.append(p["heading_path_str"].split(" > ")[-1])
    pg = p.get("page_start")
    if pg:
        parts.append(f"p.{pg}")
    return " — ".join(x for x in parts if x)


def _safe_print(text: str) -> None:
    """Print, degrading unencodable characters instead of crashing on Windows'
    default cp1252 console (e.g. the rupee sign in scheme text)."""
    try:
        print(text)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "ascii"
        print(text.encode(enc, errors="replace").decode(enc))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--scheme", default=None)
    ap.add_argument("-k", type=int, default=6)
    ap.add_argument("--no-rerank", action="store_true")
    args = ap.parse_args()

    for i, r in enumerate(retrieve(args.query, args.scheme, args.k, rerank=not args.no_rerank), 1):
        _safe_print(f"\n[{i}] score={r['score']:.3f} | {r['citation']}")
        _safe_print(f"    {r['text'][:280]}")

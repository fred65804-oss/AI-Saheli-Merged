# mcp/knowledge_base/tool.py
"""
The knowledge_base MCP tool — the callable surface specialist agents use to get
grounded, cited scheme content. Wraps ``rag.retrieve.retrieve`` (hybrid Qdrant
search + cross-encoder rerank).

Runs synchronously on the calling coroutine's thread rather than via
``asyncio.to_thread``: the embedding/reranker torch models are CPU-bound, but
running their forward pass on a secondary thread has been observed to hang or
segfault the process (Windows-specific PyTorch/OpenMP instability — the crash
happens mid-inference, not just during model load, so warming the model on
the main thread first does not help). For this single-worker demo backend,
briefly blocking the event loop during a KB query is the safe tradeoff.

Usage (from a specialist's ``handle``):

    from mcp.knowledge_base.schemas import KBQueryRequest
    from mcp.knowledge_base.tool import query_knowledge_base

    resp = await query_knowledge_base(KBQueryRequest(query=packet.user_message, scheme="poshan"))
    for chunk in resp.chunks:
        ...  # chunk.text, chunk.citation
"""

from __future__ import annotations

import time

from mcp.knowledge_base.schemas import KBChunk, KBQueryRequest, KBQueryResponse
from rag.retrieve import retrieve


async def query_knowledge_base(request: KBQueryRequest) -> KBQueryResponse:
    start = time.perf_counter()
    scheme = request.scheme.value if request.scheme else None
    results = retrieve(request.query, scheme, request.k)
    latency_ms = (time.perf_counter() - start) * 1000
    return KBQueryResponse(
        chunks=[KBChunk(**r) for r in results],
        latency_ms=latency_ms,
    )

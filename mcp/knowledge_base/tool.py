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

import logging
import time

from apps.backend.config import get_settings
from apps.backend.config import get_settings
from mcp.knowledge_base.schemas import KBChunk, KBQueryRequest, KBQueryResponse
from rag.retrieve import retrieve

log = logging.getLogger(__name__)


async def query_knowledge_base(request: KBQueryRequest) -> KBQueryResponse:
    start = time.perf_counter()
    if not get_settings().kb_local_models_enabled:
        return KBQueryResponse(chunks=[], latency_ms=0.0)

    scheme = request.scheme.value if request.scheme else None
    # Rerank policy comes from Settings: OFF by default because the
    # cross-encoder blocks the event loop for ~2s per candidate on CPU
    # (see the kb_rerank comment in apps/backend/config.py for the numbers).
    s = get_settings()
    try:
        results = retrieve(
        request.query,
        scheme,
        request.k,
        prefetch=s.kb_rerank_candidates if s.kb_rerank else max(request.k * 4, 24),
        rerank=s.kb_rerank,
    )
    except Exception as exc:
        # Grounding enriches an answer but is not required for the safety,
        # routing, eligibility, or helpline paths. Missing local ML assets must
        # degrade to no passages instead of failing the whole citizen request.
        log.warning("Knowledge-base retrieval unavailable; continuing without passages: %s", exc)
        results = []
    latency_ms = (time.perf_counter() - start) * 1000
    return KBQueryResponse(
        chunks=[KBChunk(**r) for r in results],
        latency_ms=latency_ms,
    )

"""Embedding layer for the AI Saheli knowledge base — free & local.

Dense : intfloat/multilingual-e5-base (768-d, multilingual for Hindi+English).
        e5 REQUIRES prefixes — "query: " for queries, "passage: " for documents.
Sparse: BM25 (fastembed "Qdrant/bm25") — lexical signal for exact govt terms
        (scheme names, section numbers, amounts). Enables true hybrid search.

Models are loaded lazily and cached so importing this module is cheap.
"""

from __future__ import annotations

from functools import lru_cache

DENSE_MODEL = "intfloat/multilingual-e5-base"
DENSE_DIM = 768
SPARSE_MODEL = "Qdrant/bm25"


@lru_cache(maxsize=1)
def _dense():
    from sentence_transformers import SentenceTransformer

    # Request handlers must never attempt a model download. A blocked or
    # unavailable Hugging Face connection otherwise freezes FastAPI's single
    # event-loop thread and turns an optional grounding lookup into a /chat 500.
    # Models can still be downloaded explicitly during environment setup.
    return SentenceTransformer(DENSE_MODEL, local_files_only=True)


@lru_cache(maxsize=1)
def _sparse():
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(SPARSE_MODEL, local_files_only=True)


# --------------------------------------------------------------------------- #
# Dense
# --------------------------------------------------------------------------- #
def embed_passages(texts: list[str], batch_size: int = 32):
    """Encode documents. Returns a list of 768-d float lists (normalized)."""
    model = _dense()
    prefixed = [f"passage: {t}" for t in texts]
    vecs = model.encode(
        prefixed, batch_size=batch_size, normalize_embeddings=True,
        show_progress_bar=True,
    )
    return [v.tolist() for v in vecs]


def embed_query_dense(text: str) -> list[float]:
    model = _dense()
    v = model.encode(f"query: {text}", normalize_embeddings=True)
    return v.tolist()


# --------------------------------------------------------------------------- #
# Sparse (BM25)
# --------------------------------------------------------------------------- #
def embed_passages_sparse(texts: list[str]):
    """Yield (indices, values) BM25 sparse vectors for documents."""
    for emb in _sparse().embed(texts):
        yield emb.indices.tolist(), emb.values.tolist()


def embed_query_sparse(text: str):
    emb = next(iter(_sparse().query_embed(text)))
    return emb.indices.tolist(), emb.values.tolist()

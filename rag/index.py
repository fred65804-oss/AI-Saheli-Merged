"""Build the Qdrant knowledge base from the scheme chunk JSONs.

Local persistent Qdrant (on-disk, no Docker). One collection `saheli_kb` with
named vectors: `dense` (e5, cosine) + `bm25` (sparse, IDF). Payload carries
citation metadata and a `scheme` keyword index for routed filtering.

Idempotent: point IDs are a UUID5 of chunk_id, so re-running upserts in place.

Run:  python -m rag.index            # ingest everything
      python -m rag.index --reset    # drop & rebuild the collection
"""

from __future__ import annotations

import argparse
import glob
import json
import shutil
import uuid
from pathlib import Path

from qdrant_client import QdrantClient, models

from rag.embed import DENSE_DIM, embed_passages, embed_passages_sparse

_ROOT = Path(__file__).parent
DB_PATH = str(_ROOT / "qdrant_db")
COLLECTION = "saheli_kb"
CHUNKS_GLOB = str(_ROOT / "chunks" / "*" / "*.chunks.json")
_NS = uuid.UUID("00000000-0000-0000-0000-00005a4e4c49")  # stable namespace


def client() -> QdrantClient:
    return QdrantClient(path=DB_PATH)


def ensure_collection(c: QdrantClient, reset: bool) -> None:
    if reset and c.collection_exists(COLLECTION):
        # NOTE: on local (on-disk) Qdrant, delete_collection alone does not
        # reliably purge segment files — points from removed chunks survive as
        # orphans and a rebuild ends up with MORE points than it upserted. For
        # a true reset, wipe the storage directory (see reset_storage(), used
        # by the --reset CLI path before the client is ever opened).
        c.delete_collection(COLLECTION)
    if not c.collection_exists(COLLECTION):
        c.create_collection(
            COLLECTION,
            vectors_config={
                "dense": models.VectorParams(size=DENSE_DIM, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={
                "bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)
            },
        )
        # index for fast scheme-scoped filtering
        c.create_payload_index(COLLECTION, "scheme", models.PayloadSchemaType.KEYWORD)


def load_chunks() -> list[dict]:
    chunks: list[dict] = []
    for f in sorted(glob.glob(CHUNKS_GLOB)):
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        chunks.extend(doc["chunks"])
    return chunks


def ingest(reset: bool = False, batch: int = 128) -> None:
    c = client()
    ensure_collection(c, reset)

    chunks = load_chunks()
    print(f"Loaded {len(chunks)} chunks. Embedding + upserting…")

    # Embed in one pass (dense uses batching internally; sparse is a generator).
    texts = [ch["contextualized_text"] for ch in chunks]
    dense = embed_passages(texts)
    sparse = embed_passages_sparse(texts)

    points: list[models.PointStruct] = []
    total = 0
    for ch, dvec, (sidx, sval) in zip(chunks, dense, sparse):
        points.append(
            models.PointStruct(
                id=str(uuid.uuid5(_NS, ch["chunk_id"])),
                vector={
                    "dense": dvec,
                    "bm25": models.SparseVector(indices=sidx, values=sval),
                },
                payload={
                    "chunk_id": ch["chunk_id"],
                    "scheme": ch["scheme"],
                    "doc": ch["doc"],
                    "heading_path_str": ch.get("heading_path_str", ""),
                    "page_start": ch.get("page_start"),
                    "page_end": ch.get("page_end"),
                    "text": ch["text"],
                },
            )
        )
        if len(points) >= batch:
            c.upsert(COLLECTION, points)
            total += len(points)
            points = []
    if points:
        c.upsert(COLLECTION, points)
        total += len(points)

    info = c.get_collection(COLLECTION)
    print(f"Done. Upserted {total} points. Collection now has {info.points_count} points.")


def reset_storage() -> None:
    """Filesystem-level wipe of the local Qdrant store — the only reliable way
    to guarantee no orphaned points from a previous corpus survive a rebuild."""
    p = Path(DB_PATH)
    if p.exists():
        shutil.rmtree(p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe storage & rebuild from scratch")
    args = ap.parse_args()
    if args.reset:
        reset_storage()  # wipe BEFORE opening the client, so nothing lingers
    ingest(reset=False)

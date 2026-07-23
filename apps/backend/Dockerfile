# Built from the repo ROOT (see docker-compose.yml `context: .`) because the
# backend imports the top-level agents/, mcp/, rag/, language/ packages, not
# just apps/backend/.
FROM python:3.14-slim

WORKDIR /app

# ffmpeg: faster-whisper's audio decode path. libgomp1: torch/ctranslate2
# OpenMP runtime. curl: container healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only what the backend actually imports at runtime — not rag/data (raw
# ingestion PDFs, ~53MB), rag/chunks, rag/eval, tests/, pdf_chunker/, eval/.
COPY agents/ agents/
COPY mcp/ mcp/
COPY language/ language/
COPY rag/__init__.py rag/embed.py rag/index.py rag/retrieve.py rag/
COPY rag/qdrant_db/ rag/qdrant_db/
COPY apps/__init__.py apps/__init__.py
COPY apps/backend/ apps/backend/
COPY scripts/create_admin.py scripts/create_admin.py

# Bake ML model weights into the image at build time (needs internet during
# `docker build`, not at container runtime) — avoids a 30-90s cold first
# request and lets the container run with no outbound network at all.
# WHISPER_MODEL_SIZE mirrors language/free_provider.py's default ("small").
# The bge-reranker-v2-m3 cross-encoder is deliberately NOT baked here: it's
# off by default (kb_rerank=false, ~2s/candidate on CPU — see config.py) so
# baking it would just add image size for a disabled feature. If you flip
# kb_rerank=true, add a matching RUN line to bake it too.
# rag/embed.py loads with local_files_only=True by design (a request handler
# must never trigger a download) — so baking has to populate that same HF
# cache directly, not go through embed_query_dense()/embed_query_sparse(),
# which would just hit the same local_files_only guard and fail here too.
ARG WHISPER_MODEL_SIZE=small
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL_SIZE}', device='cpu', compute_type='int8')" \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')" \
    && python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding('Qdrant/bm25')"

# Live application state — never baked into the image. Named volumes in
# docker-compose.yml mount over these so data survives every redeploy.
RUN mkdir -p data logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "apps.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

"""Test-suite determinism guard.

Blank every LLM key BEFORE any project module builds ``Settings`` (pydantic
env vars override .env file values), so the whole suite — orchestrator, real
specialists, API app — resolves to ``FakeLLM`` and deterministic fallbacks
even when the developer's .env holds a live key. No test ever spends money
or flakes on a network call.
"""

import os

os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["AZURE_OPENAI_API_KEY"] = ""
os.environ["AZURE_OPENAI_ENDPOINT"] = ""
os.environ["AZURE_OPENAI_DEPLOYMENT"] = ""
os.environ["LLM_PROVIDER"] = "auto"

# Auth tests get their own SQLite file, never the dev DB at data/auth.db —
# same reasoning as above: must be set before apps.backend.auth.db builds
# its engine at import time.
os.environ["AUTH_DATABASE_URL"] = "sqlite:///./data/test_auth.db"

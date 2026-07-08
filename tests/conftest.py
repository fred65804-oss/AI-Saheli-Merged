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

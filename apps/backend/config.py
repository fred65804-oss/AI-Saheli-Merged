"""Central, env-driven configuration for AI Saheli.

Single source of truth for tunables. Everything reads from here so behaviour
(model choice, thresholds, timeouts) changes via .env, not code edits.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Per-provider default models — used only when LLM_MODEL / LLM_FAST_MODEL are
# not set in the environment. Override via .env, never by editing code.
PROVIDER_DEFAULT_MODELS: dict[str, dict[str, str]] = {
    "anthropic": {
        "model": "claude-sonnet-4-6",
        "fast_model": "claude-haiku-4-5-20251001",
    },
    "openai": {
        "model": "gpt-4.1",
        "fast_model": "gpt-4.1-mini",
    },
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- LLM ---
    # "auto" picks the first provider with credentials (azure, anthropic, openai).
    # Set explicitly ("azure" | "anthropic" | "openai") to pin one.
    llm_provider: str = "auto"
    # Empty = use the resolved provider's default from PROVIDER_DEFAULT_MODELS.
    # (For Azure, the "model" is the DEPLOYMENT name — see azure_* fields below.)
    llm_model: str = ""
    # Smaller/faster model for the high-frequency safety + router calls.
    llm_fast_model: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # --- Azure OpenAI ---
    # Azure uses a resource endpoint + a DEPLOYMENT name (what you named the
    # model when you deployed it in the Azure portal) + an api-version — not a
    # bare model name like public OpenAI.
    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""            # https://<resource>.openai.azure.com/
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str = ""          # main model deployment name
    azure_openai_fast_deployment: str = ""     # optional; falls back to the main one

    # --- Orchestrator behaviour ---
    router_confidence_threshold: float = 0.6
    # Wall-clock budget for the specialist handoff: KB retrieval (up to
    # kb_citation_timeout_seconds) + LLM synthesis (up to
    # llm_synthesis_timeout_seconds). Sized so a slow KB *plus* a slow LLM
    # still fits with slack, so the inner LLM timeout is the one that
    # actually fires and the deterministic fallback path runs. If the
    # outer wait_for fires first it cancels the LLM call as CancelledError
    # (not a clean TimeoutError) and the citizen sees the ugly "having
    # trouble fetching" message instead of the grounded fallback.
    specialist_timeout_seconds: float = 60.0
    # If True, run the L2 LLM safety classifier on every turn (safest, costlier).
    # If False, run it only when L1 lexicon fires or intent is safety-adjacent.
    safety_always_llm_check: bool = False
    # Best-effort KB retrieval budget inside a specialist (seconds). The KB is
    # an enrichment, never a dependency — a cold index must not eat the whole
    # specialist time budget. Bounded below the specialist handoff timeout
    # (20s) so a slow retrieval degrades to "no passages" rather than a hang.
    # (Was 4s, which is shorter than a warm rerank of 50 candidates on CPU and
    # silently dropped grounding on real queries.)
    kb_citation_timeout_seconds: float = 15.0
    # How many KB passages a specialist retrieves for answer synthesis.
    kb_synthesis_k: int = 6
    # Inner LLM budget for grounded answer synthesis. Distinct from the outer
    # specialist wait_for so a stalled endpoint degrades to the deterministic
    # fallback (composed from verified tool facts + citation hint) rather
    # than surfacing "having trouble fetching" to the citizen. Must be < the
    # specialist timeout minus a KB retrieval budget.
    llm_synthesis_timeout_seconds: float = 20.0

    # --- Audit trace ---
    trace_sink_path: str = "logs/interactions.jsonl"

    @property
    def _azure_ready(self) -> bool:
        return bool(
            self.azure_openai_api_key.strip()
            and self.azure_openai_endpoint.strip()
            and self.azure_openai_deployment.strip()
        )

    @property
    def resolved_provider(self) -> str:
        """The provider in effect ("azure" | "anthropic" | "openai" | "none")."""
        if self.llm_provider != "auto":
            return self.llm_provider
        if self._azure_ready:
            return "azure"
        if self.anthropic_api_key.strip():
            return "anthropic"
        if self.openai_api_key.strip():
            return "openai"
        return "none"

    @property
    def resolved_model(self) -> str:
        # For Azure, the "model" the app reports/uses IS the deployment name.
        if self.resolved_provider == "azure":
            return self.azure_openai_deployment
        if self.llm_model.strip():
            return self.llm_model
        return PROVIDER_DEFAULT_MODELS.get(self.resolved_provider, {}).get("model", "")

    @property
    def resolved_fast_model(self) -> str:
        if self.resolved_provider == "azure":
            return self.azure_openai_fast_deployment.strip() or self.azure_openai_deployment
        if self.llm_fast_model.strip():
            return self.llm_fast_model
        return PROVIDER_DEFAULT_MODELS.get(self.resolved_provider, {}).get(
            "fast_model", ""
        ) or self.resolved_model

    @property
    def has_llm_key(self) -> bool:
        """True when a real LLM call is possible (else tests/CLI use FakeLLM)."""
        provider = self.resolved_provider
        if provider == "azure":
            return self._azure_ready
        if provider == "anthropic":
            return bool(self.anthropic_api_key.strip())
        if provider == "openai":
            return bool(self.openai_api_key.strip())
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()

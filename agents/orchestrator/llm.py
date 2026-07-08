"""LLM layer — provider-agnostic, injectable, testable.

Everything that calls a model goes through the ``StructuredLLM`` protocol:
  - ``parse(...)``    → forces structured (Pydantic) output. Used by the router
                        and the L2 safety classifier so we never parse free text.
  - ``complete(...)`` → plain text. Used to phrase warm questions and to
                        synthesize grounded specialist answers.

Three implementations:
  - ``AnthropicLLM`` wraps ``langchain-anthropic``.
  - ``OpenAILLM`` wraps ``langchain-openai``.
  - ``FakeLLM`` returns scripted objects so routing / safety / slot logic is
    unit-tested deterministically with NO API key.

Provider + model come from Settings (env-driven, see ``config.py``); nothing
model-specific is hardcoded at call sites. The model is injected (never
imported at call sites), which is what makes the whole orchestrator testable
offline.
"""

from __future__ import annotations

from typing import Callable, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from apps.backend.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class StructuredLLM(Protocol):
    """The only LLM surface the orchestrator depends on."""

    async def parse(self, system: str, user: str, schema: type[T]) -> T:
        """Return an instance of ``schema`` populated by the model."""
        ...

    async def complete(self, system: str, user: str) -> str:
        """Return a plain-text completion."""
        ...


# --------------------------------------------------------------------------- #
# Real provider
# --------------------------------------------------------------------------- #
class _LangChainLLM:
    """Shared parse/complete plumbing for any LangChain chat model.

    Subclasses implement ``_build_model(fast)`` returning a configured chat
    model; this base class caches the result per instance. Caching matters
    beyond efficiency: the OpenAI SDK does a one-time OS/platform probe
    (``get_platform()``, on a background thread) the first time a freshly
    constructed client makes a request, and on some Windows machines that
    probe is slow enough to occasionally exceed a specialist's timeout as
    ``asyncio.exceptions.CancelledError`` (observed in production — every
    per-call reconstruction re-triggered the probe, not just the first ever
    call). Building the client once and reusing it eliminates the failure
    mode entirely, on top of avoiding needless HTTP connection-pool churn.

    ``fast=True`` selects the smaller model for high-frequency calls (router,
    safety); model names resolve from Settings, never from code.
    """

    _s: Settings

    def __init__(self) -> None:
        self._model_cache: dict = {}

    def _build_model(self, fast: bool):  # pragma: no cover - abstract
        raise NotImplementedError

    def _model(self, fast: bool):
        if fast not in self._model_cache:
            self._model_cache[fast] = self._build_model(fast)
        return self._model_cache[fast]

    def _model_name(self, fast: bool) -> str:
        return self._s.resolved_fast_model if fast else self._s.resolved_model

    async def parse(self, system: str, user: str, schema: type[T], *, fast: bool = True) -> T:
        from langchain_core.messages import HumanMessage, SystemMessage

        # method="function_calling" — the default "json_schema" mode on
        # langchain-openai>=0.3 requires OpenAI's strict Structured Outputs
        # schema (no unions with null, no default values on top-level fields,
        # etc.) which Azure gpt-4o-mini rejects with a 400 for our router /
        # slot-picker schemas. Function calling is universally supported
        # across Anthropic, OpenAI and Azure and has no such restriction.
        structured = self._model(fast).with_structured_output(
            schema, method="function_calling"
        )
        result = await structured.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        return result  # type: ignore[return-value]

    async def complete(self, system: str, user: str, *, fast: bool = True) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        result = await self._model(fast).ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        return result.content if isinstance(result.content, str) else str(result.content)


class AnthropicLLM(_LangChainLLM):
    """Anthropic-backed StructuredLLM via langchain-anthropic."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self._s = settings or get_settings()
        # Imported lazily so the package imports without langchain installed
        # (e.g. in a pure-unit-test environment using FakeLLM).
        from langchain_anthropic import ChatAnthropic

        self._ChatAnthropic = ChatAnthropic

    def _build_model(self, fast: bool):
        return self._ChatAnthropic(
            model=self._model_name(fast),
            api_key=self._s.anthropic_api_key,
            temperature=0,
            max_tokens=1024,
            timeout=30,
        )


class OpenAILLM(_LangChainLLM):
    """OpenAI-backed StructuredLLM.

    ``parse`` (structured output) uses langchain-openai because we need its
    with_structured_output helper. ``complete`` uses the **sync** OpenAI SDK
    wrapped in ``asyncio.to_thread``: langchain-openai's async path goes
    through httpx.AsyncClient, which on this Windows box intermittently
    stalls at the TLS transport layer for long-context requests (the
    connection pool awaits a response that never arrives and only surfaces
    on outer cancellation). The sync client uses httpx.Client, which does
    not exhibit the hang.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self._s = settings or get_settings()
        from langchain_openai import ChatOpenAI
        from openai import OpenAI

        self._ChatOpenAI = ChatOpenAI
        self._sync_clients: dict[bool, OpenAI] = {}
        self._OpenAI = OpenAI

    def _build_model(self, fast: bool):
        return self._ChatOpenAI(
            model=self._model_name(fast),
            api_key=self._s.openai_api_key,
            temperature=0,
            max_tokens=1024,
            timeout=30,
        )

    def _sync_client(self, fast: bool):
        if fast not in self._sync_clients:
            self._sync_clients[fast] = self._OpenAI(
                api_key=self._s.openai_api_key, timeout=30, max_retries=1
            )
        return self._sync_clients[fast]

    async def complete(self, system: str, user: str, *, fast: bool = True) -> str:
        import asyncio

        def _call() -> str:
            resp = self._sync_client(fast).chat.completions.create(
                model=self._model_name(fast),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=1024,
            )
            return (resp.choices[0].message.content or "").strip()

        return await asyncio.to_thread(_call)


class AzureOpenAILLM(_LangChainLLM):
    """Azure OpenAI-backed StructuredLLM.

    See ``OpenAILLM`` for why ``complete`` runs on the sync SDK via
    ``asyncio.to_thread``. Structured output still goes through langchain
    because that request pattern (fast model, short prompt) does not
    trigger the async-transport stall we're working around."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self._s = settings or get_settings()
        from langchain_openai import AzureChatOpenAI
        from openai import AzureOpenAI

        self._AzureChatOpenAI = AzureChatOpenAI
        self._sync_clients: dict[bool, AzureOpenAI] = {}
        self._AzureOpenAI = AzureOpenAI

    def _build_model(self, fast: bool):
        return self._AzureChatOpenAI(
            azure_deployment=self._model_name(fast),
            azure_endpoint=self._s.azure_openai_endpoint,
            api_key=self._s.azure_openai_api_key,
            api_version=self._s.azure_openai_api_version,
            temperature=0,
            max_tokens=1024,
            timeout=30,
        )

    def _sync_client(self, fast: bool):
        if fast not in self._sync_clients:
            self._sync_clients[fast] = self._AzureOpenAI(
                azure_endpoint=self._s.azure_openai_endpoint,
                api_key=self._s.azure_openai_api_key,
                api_version=self._s.azure_openai_api_version,
                timeout=30,
                max_retries=1,
            )
        return self._sync_clients[fast]

    async def complete(self, system: str, user: str, *, fast: bool = True) -> str:
        import asyncio

        def _call() -> str:
            resp = self._sync_client(fast).chat.completions.create(
                model=self._model_name(fast),  # deployment name on Azure
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=1024,
            )
            return (resp.choices[0].message.content or "").strip()

        return await asyncio.to_thread(_call)


# --------------------------------------------------------------------------- #
# Test double
# --------------------------------------------------------------------------- #
ParseResponder = Callable[[str, str, type[BaseModel]], BaseModel]
CompleteResponder = Callable[[str, str], str]


class FakeLLM:
    """Scripted StructuredLLM for deterministic tests / offline CLI.

    Pass a ``parse_responder`` (system, user, schema) -> BaseModel and/or a
    ``complete_responder`` (system, user) -> str. Sensible defaults are provided
    so a bare ``FakeLLM()`` still returns valid objects.
    """

    def __init__(
        self,
        parse_responder: ParseResponder | None = None,
        complete_responder: CompleteResponder | None = None,
    ) -> None:
        self._parse = parse_responder
        self._complete = complete_responder

    async def parse(self, system: str, user: str, schema: type[T], *, fast: bool = True) -> T:
        if self._parse is not None:
            obj = self._parse(system, user, schema)
            if not isinstance(obj, schema):
                raise TypeError(
                    f"FakeLLM responder returned {type(obj).__name__}, expected {schema.__name__}"
                )
            return obj
        # Default: construct with model defaults if possible.
        return schema()  # type: ignore[call-arg]

    async def complete(self, system: str, user: str, *, fast: bool = True) -> str:
        if self._complete is not None:
            return self._complete(system, user)
        # Empty by default so callers fall back to their canonical phrasing
        # (warm slot/clarify prompts) instead of echoing raw instructions.
        return ""


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
_llm_singleton: StructuredLLM | None = None


def get_llm(settings: Settings | None = None) -> StructuredLLM:
    """Return the process-wide LLM singleton, building it once.

    Provider resolution is env-driven (``LLM_PROVIDER=auto`` picks the first
    provider with a key). This keeps the CLI and the API working (with
    degraded, lexicon-only safety and default routing) even without a
    configured key, and lets tests inject their own FakeLLM directly
    (bypassing this factory entirely via each agent's ``llm=`` constructor arg).

    Memoized deliberately: the orchestrator's router/safety gate AND every
    specialist agent each call this independently, and each ``_LangChainLLM``
    instance caches its own chat-model clients (see that class's docstring).
    Without a shared singleton, every specialist would build its own client
    and independently pay the "first real request" cost of the underlying
    SDK's one-time OS/platform probe — which has been observed slow enough on
    this machine to blow a specialist's response timeout. One singleton means
    that cost is paid (and can be pre-paid via a startup warmup call) exactly
    once for the whole process.
    """
    global _llm_singleton
    if _llm_singleton is not None:
        return _llm_singleton
    s = settings or get_settings()
    if s.has_llm_key:
        provider = s.resolved_provider
        if provider == "azure":
            _llm_singleton = AzureOpenAILLM(s)
        elif provider == "anthropic":
            _llm_singleton = AnthropicLLM(s)
        elif provider == "openai":
            _llm_singleton = OpenAILLM(s)
        else:
            _llm_singleton = FakeLLM()
    else:
        _llm_singleton = FakeLLM()
    return _llm_singleton

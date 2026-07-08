"""Shared LLM-synthesis helper for real specialists.

Every real specialist follows the same shape:
  1. Retrieve grounded chunks from the KB (RAG).
  2. Call deterministic MCP tools for structured facts (eligibility / geo /
     helplines) — these are the numbers we must never invent.
  3. Ask the LLM to compose an answer that weaves the tool facts into the
     retrieved passages, in plain, warm language.
  4. Return an ``AgentResponse`` with citations drawn from BOTH the KB and
     the deterministic tool sources.

The synthesis prompt is intentionally strict:
  - answers must stay within the passages / tool facts;
  - benefit amounts, phone numbers, and eligibility rules come ONLY from
    tool_facts;
  - if the passages don't cover the question, the model must say so instead
    of inventing content.

This module never touches state, session, or LangGraph — specialists compose
these helpers however they wish.
"""

from __future__ import annotations

import asyncio
from typing import Iterable

from pydantic import BaseModel, Field

from agents.orchestrator.llm import StructuredLLM, get_llm
from agents.specialists.base import Citation
from mcp.knowledge_base.schemas import KBQueryRequest, KBQueryResponse, Scheme
from mcp.knowledge_base.tool import query_knowledge_base


# The KB is an *enrichment*: cold model load or an unreachable index must not
# blow the specialist's total time budget. Timeout is generous because the
# reranker runs on the calling thread on cold start.
_KB_TIMEOUT_S = 8.0


class SynthesisResult(BaseModel):
    """What the LLM returns for a specialist turn."""

    answer: str = Field(description="Warm, plain-language reply to the citizen.")
    used_passages: list[int] = Field(
        default_factory=list,
        description="1-indexed KB passage numbers actually reflected in the answer.",
    )


async def retrieve_kb(
    query: str, scheme: str | None, k: int = 4
) -> KBQueryResponse | None:
    """Best-effort KB retrieval. Returns None on timeout / index unavailable."""
    try:
        return await asyncio.wait_for(
            query_knowledge_base(
                KBQueryRequest(
                    query=query,
                    scheme=Scheme(scheme) if scheme else None,
                    k=k,
                )
            ),
            timeout=_KB_TIMEOUT_S,
        )
    except (Exception, asyncio.TimeoutError):
        return None


def _format_passages(chunks) -> str:
    if not chunks:
        return "(no KB passages available — rely only on tool facts and refuse to answer beyond them)"
    lines: list[str] = []
    for i, c in enumerate(chunks, 1):
        heading = c.heading_path_str or c.doc
        lines.append(f"[{i}] {heading}\n{c.text.strip()[:900]}")
    return "\n\n".join(lines)


def _format_facts(tool_facts: dict) -> str:
    if not tool_facts:
        return "(none)"
    lines: list[str] = []
    for label, value in tool_facts.items():
        if value is None or value == "":
            continue
        lines.append(f"- {label}: {value}")
    return "\n".join(lines) if lines else "(none)"


SYNTHESIS_SYSTEM = """You are a specialist agent for India's Ministry of Women & Child Development.
You answer a citizen's question grounded ONLY in the passages and tool facts you are given.

Rules — non-negotiable:
1. Never invent benefit amounts, eligibility rules, phone numbers, or scheme names. If a fact isn't in the passages or tool_facts, DO NOT state it.
2. If the tool_facts contradict the passages (e.g. tool says amount = ₹5,000), TRUST tool_facts — they are the authoritative deterministic sources.
3. Keep the reply short (3-6 sentences), warm, and plain — the citizen may have low literacy. No jargon, no markdown headings.
4. Do NOT invite the citizen to share personal identifiers (Aadhaar number, phone, etc.).
5. If the question falls outside what the passages / tool facts cover, say so briefly and suggest a next step (Anganwadi, helpline, DCPU as appropriate to the scheme).
6. Reply in ENGLISH. The orchestrator will translate.

Output must fit the SynthesisResult schema."""


async def synthesize(
    *,
    llm: StructuredLLM,
    user_message: str,
    scheme_name: str,
    kb_chunks: Iterable,
    tool_facts: dict,
    extra_instructions: str = "",
) -> SynthesisResult:
    """Ask the LLM to compose a grounded answer from KB + tool facts.

    Falls back to a safe canned message if the LLM call fails, so the demo
    never 500s on a synthesis hiccup.
    """
    passages_block = _format_passages(list(kb_chunks))
    facts_block = _format_facts(tool_facts)

    user_prompt = f"""Scheme: {scheme_name}
Citizen message: {user_message}

KB passages (grounded):
{passages_block}

Tool facts (authoritative):
{facts_block}

{extra_instructions}

Compose the reply now."""

    fallback = SynthesisResult(
        answer=(
            "I can share what I have on this scheme, but I couldn't reach "
            "the full guidance just now. Please contact your nearest "
            "Anganwadi Centre or the relevant helpline for authoritative help."
        ),
        used_passages=[],
    )
    try:
        # Specialists use the sonnet-tier model (fast=False); the shared
        # protocol tolerates the kwarg for both AnthropicLLM and FakeLLM.
        result = await llm.parse(  # type: ignore[call-arg]
            SYNTHESIS_SYSTEM, user_prompt, SynthesisResult, fast=False
        )
    except Exception:
        return fallback
    # FakeLLM (no key configured) returns schema defaults — surface the safe
    # canned message instead of an empty answer.
    if not result.answer.strip():
        return fallback
    return result


def kb_citations(response: KBQueryResponse | None, limit: int = 3) -> list[Citation]:
    """Convert a KB response into the specialist Citation shape."""
    if not response:
        return []
    out: list[Citation] = []
    for c in response.chunks[:limit]:
        out.append(Citation(source_doc=c.doc, section=c.heading_path_str or None))
    return out


def get_specialist_llm() -> StructuredLLM:
    """Sonnet-tier LLM for specialist answer synthesis (not the fast router model).

    Uses the shared factory so a missing API key transparently falls back to
    FakeLLM — in that case the synthesis returns SynthesisResult() defaults
    and the specialist emits the canned fallback answer. This keeps the demo
    boot-safe even without a key.
    """
    return get_llm()

"""Shared grounded response builders for scheme-overview questions."""

from __future__ import annotations

from agents.orchestrator.llm import StructuredLLM
"""
from agents.specialists._grounding import (
    chunks_to_citations,
    retrieve_passages,
    synthesize_answer,
)
"""
from agents.specialists.base import AgentResponse, Citation, ContextPacket
from agents.specialists.overviews import overview_for, top_level_overviews


def _dedupe_citations(citations: list[Citation]) -> list[Citation]:
    seen: set[tuple[str, str, str | None]] = set()
    result: list[Citation] = []
    for citation in citations:
        key = (citation.source_doc, citation.source_url, citation.section)
        if key not in seen:
            seen.add(key)
            result.append(citation)
    return result


async def answer_scheme_overview(
    llm: StructuredLLM, packet: ContextPacket
) -> AgentResponse:
    overview = overview_for(packet.intent, packet.user_message)
    
    answer = (
        f"{overview.summary} "
        "Would you like eligibility, application, or service details?"
    )


    return AgentResponse(
        answer=answer,
        citations= [
            Citation(
                source_doc = overview.source_doc,
                source_url = overview.source_url
            )
        ],
        tool_calls=["overview_registry"],
        confidence=0.8,
    )


async def answer_broad_overview(
    llm: StructuredLLM, packet: ContextPacket
) -> AgentResponse:
    overviews = top_level_overviews()
    
    answer = (
        "I can help with three main Ministry programmes. "
        + " ".join(
            f"{item.title}: {item.summary}"
            for item in overviews
        )
        + " Which programme would you like to explore?"
    )

    citations = [
        Citation(source_doc=item.source_doc, source_url=item.source_url)
        for item in overviews
    ]
    

    return AgentResponse(
        answer=answer,
        citations=_dedupe_citations(citations),
        tool_calls=["overview_registry"],
        confidence=0.78,
    )

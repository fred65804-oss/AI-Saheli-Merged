from __future__ import annotations

import re
from typing import Literal

from agents.guardrails.lexicon import normalize

RequestType = Literal["overview", "eligibility", "service", "guidance"]

_OVERVIEW_PATTERNS = (
    r"\bwhat is\b",
    r"\bwhat are\b",
    r"\btell me about\b",
    r"\bexplain\b",
    r"\boverview\b",
    r"\bwhat schemes\b",
    r"\bwhich schemes\b",
    r"\bkaun si yojana\b",
    r"\bkya hai\b",
    r"\bkya hota hai\b",
    r"\bke baare mein batao",
    r"\bke bare me batao",
    r"\bke baare mein bataao",
    r"\bke baare me bataao",
    r"^\s*(?:schemes?|yojana)\s*[?.!]*$"
)

_ELIGIBILITY_PATTERNS = (
    r"\bam i eligible\b",
    r"\bcan i get\b",
    r"\bdo i qualify\b",
    r"\beligibility\b",
    r"\blabh mil sakta\b",
    r"\bpatra\b"
)

_SERVICE_PATTERNS = (
    r"\bhow (?:do|can) i apply\b",
    r"\bapplication process\b",
    r"\bregister\b",
    r"\bnearest\b",
    r"\bwhere (?:is|can)\b",
    r"\bcontact\b",
    r"\breport\b"
)

def _matches(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)

def classify_request_type(message: str) -> RequestType | None:
    """
        Return a deterministic type for explicit wording.
        None means the router LLM may classify less obvious wording
    """

    text = normalize(message)

    # Broad discovery will win over "can I get", because the user has not selected any scheme for personlized eligibility check

    if re.search(r"\b(?:what|which) schemes\b", text):
        return "overview"

    if _matches(_ELIGIBILITY_PATTERNS, text):
        return "eligibility"

    if _matches(_SERVICE_PATTERNS, text):
        return "service"

    if _matches(_OVERVIEW_PATTERNS, text):
        return "overview"

    return None

def is_broad_scheme_discovery(message: str) -> bool:
    text = normalize(message)

    # Accept a direct response to the clarification prompt
    if re.fullmatch(r"(?:schemes?|yojana)[?.!]*", text):
        return True 
    
    return bool(
        re.search(
            r"\b(?:what|which|available|government|ministry).{0,30}"
            r"(?:schemes?|yojana)\b",
            text
        )
    )

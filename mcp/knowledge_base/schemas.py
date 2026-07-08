# mcp/knowledge_base/schemas.py
"""
Pydantic schemas for the knowledge_base MCP tool.
These types are the ONLY contract between the tool and its callers
(specialist agents). Change them here first, everywhere else follows.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Scheme(str, Enum):
    POSHAN = "poshan"
    VATSALYA = "vatsalya"
    SHAKTI = "shakti"


class KBQueryRequest(BaseModel):
    query: str = Field(min_length=1)
    scheme: Optional[Scheme] = Field(
        default=None, description="scope search to one scheme; None searches all"
    )
    k: int = Field(default=6, ge=1, le=20)


class KBChunk(BaseModel):
    text: str
    scheme: str
    doc: str
    heading_path_str: str = ""
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    chunk_id: Optional[str] = None
    score: float
    citation: str


class KBQueryResponse(BaseModel):
    chunks: list[KBChunk] = Field(default_factory=list)
    latency_ms: float

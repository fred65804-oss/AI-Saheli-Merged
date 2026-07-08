# mcp/geo_locator/schemas.py
"""
Pydantic schemas for the geo_locator MCP tool.
These types are the ONLY contract between the tool and its callers.
Change them here first, everywhere else follows.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ServiceType(str, Enum):
    AWC = "AWC"    # Anganwadi Centre — Poshan (nutrition, THR, growth monitoring)
    OSC = "OSC"    # One Stop Centre — Shakti (women in distress)
    DCPU = "DCPU"  # District Child Protection Unit — Vatsalya
    CWC = "CWC"    # Child Welfare Committee — Vatsalya


class Facility(BaseModel):
    id: str
    name: str
    type: ServiceType
    district: str
    state: str
    address: str
    phone: Optional[str] = None
    hours: Optional[str] = None
    source: str = Field(description="grounding source / provenance of the record")


class LookupRequest(BaseModel):
    service_type: ServiceType
    district: str = Field(min_length=1)
    state: Optional[str] = Field(
        default=None, description="enables a state-level fallback when the district has no data"
    )
    limit: int = Field(default=3, ge=1, le=20)


class LookupResponse(BaseModel):
    facilities: list[Facility] = Field(default_factory=list)
    district_matched: Optional[str] = Field(
        default=None, description="the district actually served, or None on a graceful miss"
    )
    count: int = 0
    note: Optional[str] = Field(
        default=None,
        description="human-readable explanation on fallback or no-data (graceful degradation)",
    )
    latency_ms: float = 0.0

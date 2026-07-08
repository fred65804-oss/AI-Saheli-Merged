# mcp/helpline_directory/schemas.py
"""
Pydantic schemas for the helpline_directory MCP tool.
These types are the ONLY contract between the tool and its callers.
Change them here first, everywhere else follows.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class Category(str, Enum):
    CHILD_PROTECTION = "child_protection"
    CHILD_DISTRESS = "child_distress"
    MISSING_CHILD = "missing_child"
    WOMEN_SAFETY = "women_safety"
    DOMESTIC_VIOLENCE = "domestic_violence"
    HARASSMENT = "harassment"
    EMERGENCY = "emergency"
    MEDICAL_EMERGENCY  = "medical_emergency"
    MEDICAL_RED_FLAG   = "medical_red_flag"
    NUTRITION_MEDICAL  = "nutrition_medical"
    LEGAL_AID          = "legal_aid"
    SCHEME_INFO_WOMEN  = "scheme_info_women"

class Scheme(str, Enum):
    POSHAN   = "poshan"
    VATSALYA = "vatsalya"
    SHAKTI   = "shakti"

class Language(str, Enum):
    EN = "en"; HI = "hi"; BN = "bn"; TA = "ta"; TE = "te"
    MR = "mr"; GU = "gu"; KN = "kn"; ML = "ml"; OR = "or"; PA = "pa"

class HelplineEntry(BaseModel):
    id: str
    name: str  # human display name, e.g. "Women Helpline" — shown to citizens
    number: Optional[str]
    categories: list[Category]
    when_to_call: str
    hours: Optional[str]
    languages: list[Language]
    scheme: Optional[Scheme]
    priority: int = Field(ge = 0, le = 9)
    source_url: str
    escalation_note: Optional[str]

class LookupRequest(BaseModel):
    category: Category    
    lang: Language = Language.EN
    scheme: Optional[Scheme] = None # optional scheme hint for tie-breaking

class LookupResponse(BaseModel):
    primary: HelplineEntry
    secondary: list[HelplineEntry] = []
    escalation_note: Optional[str] = None # concatenation for agent convenience
    latency_ms: float













"""Canonicalization for scheme names commonly distorted by speech recognition."""

from __future__ import annotations
import re

# Matches observed Whisper output :
# PMMVY, PM MVY, PMVY, PN MVY
_PMMVY_PATTERN = re.compile(r"\bp\s*[mn]\s*m?\s*v\s*y\b", re.IGNORECASE)
_VATSALYA_PATTERN = re.compile(r"\bvatsal(?:ya|aya)\b", re.IGNORECASE)


def canonicalize_scheme_terms(text: str) -> str:
    text = _PMMVY_PATTERN.sub("PMMVY", text)
    text = _VATSALYA_PATTERN.sub("Vatsalya", text)
    return text

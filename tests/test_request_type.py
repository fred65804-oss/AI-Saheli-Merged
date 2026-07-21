"""Deterministic request-type classification tests."""

import pytest

from agents.orchestrator.request_type import classify_request_type
from language.scheme_terms import canonicalize_scheme_terms


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("What is Mission Shakti?", "overview"),
        ("Tell me about PMMVY", "overview"),
        ("What schemes are available?", "overview"),
        ("Am I eligible for PMMVY?", "eligibility"),
        ("Can I get the maternity benefit?", "eligibility"),
        ("How do I apply for PMMVY?", "service"),
        ("Where is the nearest Anganwadi?", "service"),
        ("What should I eat during pregnancy?", None),
    ],
)
def test_request_type_classification(message, expected):
    assert classify_request_type(message) == expected


@pytest.mark.parametrize("variant", ["PMMVY", "PMVY", "PM MVY", "PN MVY"])
def test_pmmvy_asr_variants_are_canonicalized(variant):
    assert canonicalize_scheme_terms(f"Tell me about {variant}") == (
        "Tell me about PMMVY"
    )

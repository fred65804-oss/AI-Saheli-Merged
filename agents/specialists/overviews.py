"""Vetted, source-backed summaries for overview and discovery questions."""

from __future__ import annotations

from dataclasses import dataclass

from agents.guardrails.lexicon import normalize


@dataclass(frozen=True)
class SchemeOverview:
    key: str
    intent: str
    title: str
    aliases: tuple[str, ...]
    summary: str
    retrieval_query: str
    source_doc: str
    source_url: str


_MISSION_SHAKTI_URL = (
    "https://missionshakti.wcd.gov.in/public/documents/whatsnew/"
    "Mission_Shakti_Guidelines.pdf"
)


OVERVIEWS: tuple[SchemeOverview, ...] = (
    SchemeOverview(
        key="poshan",
        intent="poshan",
        title="Saksham Anganwadi and Poshan 2.0",
        aliases=("poshan", "poshan 2.0", "anganwadi"),
        summary=(
            "Saksham Anganwadi and Poshan 2.0 is the Ministry's nutrition "
            "programme supporting children, pregnant women, lactating mothers, "
            "and eligible adolescent girls through Anganwadi services."
        ),
        retrieval_query="Overview, objectives and services under Poshan 2.0",
        source_doc="Saksham Anganwadi & Poshan 2.0 Operational Guidelines, MoWCD",
        source_url="https://poshantracker.in/",
    ),
    SchemeOverview(
        key="vatsalya",
        intent="vatsalya",
        title="Mission Vatsalya",
        aliases=("mission vatsalya", "vatsalya", "child protection"),
        summary=(
            "Mission Vatsalya is the Ministry's child-protection framework. It "
            "supports children in need of care and protection through family-based "
            "care, sponsorship, foster care, adoption support, Child Welfare "
            "Committees, and District Child Protection Units."
        ),
        retrieval_query="Mission Vatsalya overview objectives services",
        source_doc="Mission Vatsalya Guidelines, MoWCD",
        source_url="https://wcd.nic.in/schemes/mission-vatsalya",
    ),
    SchemeOverview(
        key="shakti",
        intent="shakti",
        title="Mission Shakti",
        aliases=("mission shakti", "mahila shakti"),
        summary=(
            "Mission Shakti is the Ministry's umbrella programme for women's "
            "safety, security, and empowerment. It includes One Stop Centres, "
            "Women Helpline 181, PMMVY, Sakhi Niwas, Nari Adalat, and related "
            "empowerment initiatives."
        ),
        retrieval_query="Mission Shakti overview Sambal Samarthya services",
        source_doc="Mission Shakti Guidelines, MoWCD",
        source_url=_MISSION_SHAKTI_URL,
    ),
    SchemeOverview(
        key="pmmvy",
        intent="shakti",
        title="Pradhan Mantri Matru Vandana Yojana (PMMVY)",
        aliases=("pmmvy", "pmvy", "pm mvy", "pn mvy", "matru vandana"),
        summary=(
            "PMMVY is a maternity-benefit component of Mission Shakti. It "
            "provides cash incentives to eligible pregnant women and lactating "
            "mothers, subject to the scheme's child-order and socioeconomic rules."
        ),
        retrieval_query="PMMVY overview purpose maternity benefit",
        source_doc="Mission Shakti Guidelines (Samarthya — PMMVY 2.0), MoWCD",
        source_url=_MISSION_SHAKTI_URL,
    ),
    SchemeOverview(
        key="one_stop_centre",
        intent="shakti",
        title="One Stop Centre",
        aliases=("one stop centre", "one stop center", "osc"),
        summary=(
            "One Stop Centres provide coordinated support for women affected by "
            "violence, including access to medical, legal, police, counselling, "
            "and temporary-shelter services."
        ),
        retrieval_query="Mission Shakti One Stop Centre services overview",
        source_doc="Mission Shakti Guidelines, MoWCD",
        source_url=_MISSION_SHAKTI_URL,
    ),
    SchemeOverview(
        key="foster_care",
        intent="vatsalya",
        title="Foster Care under Mission Vatsalya",
        aliases=("foster care", "fostering"),
        summary=(
            "Foster care is a family-based care arrangement for a child who cannot "
            "temporarily remain with their biological family. It is arranged "
            "through the child-protection system under Mission Vatsalya."
        ),
        retrieval_query="Mission Vatsalya foster care overview",
        source_doc="Model Foster Care Guidelines 2024, MoWCD",
        source_url="https://wcd.nic.in/schemes/mission-vatsalya",
    ),
    SchemeOverview(
        key="adoption",
        intent="vatsalya",
        title="Adoption through CARA",
        aliases=("adoption", "adopt", "cara", "god lena"),
        summary=(
            "Adoption in India is administered through the Central Adoption "
            "Resource Authority and recognised adoption agencies under the "
            "applicable adoption regulations."
        ),
        retrieval_query="CARA adoption process overview",
        source_doc="Central Adoption Resource Authority (CARA)",
        source_url="https://cara.wcd.gov.in/",
    ),
)


def overview_for(intent: str, message: str) -> SchemeOverview:
    text = normalize(message)
    matches: list[tuple[int, SchemeOverview]] = []
    for overview in OVERVIEWS:
        if overview.intent != intent:
            continue
        matched_aliases = [
            alias for alias in overview.aliases if normalize(alias) in text
        ]
        if matched_aliases:
            matches.append((max(len(alias) for alias in matched_aliases), overview))

    if matches:
        return max(matches, key=lambda item: item[0])[1]

    return next(
        overview
        for overview in OVERVIEWS
        if overview.intent == intent and overview.key == intent
    )


def top_level_overviews() -> list[SchemeOverview]:
    keys = {"poshan", "vatsalya", "shakti"}
    return [overview for overview in OVERVIEWS if overview.key in keys]

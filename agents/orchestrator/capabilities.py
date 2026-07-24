"""Concrete agent capability cards — the canonical scheme definitions.

These instances drive routing and dynamic questioning. Each mock (and later,
each real) specialist is assigned the matching card. The router builds its
prompt by introspecting the cards of *registered* agents — it never hardcodes
scheme names — so a new scheme is added here + registered, nothing else.

Scheme facts sourced from `.claude/project/schemes.md`.
"""

from __future__ import annotations

from agents.specialists.base import AgentCapabilityCard, SlotSpec

# --------------------------------------------------------------------------- #
# Poshan 2.0 — maternal & child nutrition
# --------------------------------------------------------------------------- #
POSHAN_CARD = AgentCapabilityCard(
    scheme="poshan",
    display_name="Poshan (Nutrition)",
    description=(
        "Maternal and child nutrition, the first 1,000 days, supplementary "
        "nutrition / Take-Home-Ration (THR), child growth milestones, "
        "immunization schedules, and the nearest Anganwadi Centre."
    ),
    example_utterances=[
        "What should I eat during pregnancy?",
        "Pregnancy mein kya khana chahiye?",
        "My 14-month-old is not gaining weight",
        "When should my baby get vaccinated?",
        "Where is the nearest Anganwadi?",
        "Take home ration kaise milega?",
    ],
    keywords=[
        "nutrition", "eat", "diet", "khana", "poshan", "pregnan", "garbh",
        "weight", "growth", "milestone", "vaccin", "tika", "immuni",
        "anganwadi", "thr", "ration", "anemia", "khoon",
        # developmental milestones (growth-monitoring queries rarely say "growth")
        "walk", "crawl", "sit up", "sitting up", "standing", "talk", "speak",
        "development", "developmental delay", "months old", "not gaining",
        # Devanagari
        "गर्भ", "खाना", "पोषण", "टीका", "वजन", "आंगनवाड़ी", "दूध", "चलना", "बोलना",
    ],
    required_slots=[
        SlotSpec(
            name="beneficiary_type",
            type="enum",
            required=True,
            priority=10,
            ask_prompt="Is this guidance for a pregnant woman, a new mother, or a child?",
            enum_values=["pregnant_woman", "lactating_mother", "child"],
        ),
    ],
    optional_slots=[
        SlotSpec(
            name="pregnancy_stage",
            type="enum",
            required=False,
            priority=20,
            ask_prompt="Which month or trimester of pregnancy are you in?",
            enum_values=["1st_trimester", "2nd_trimester", "3rd_trimester", "postpartum"],
        ),
        SlotSpec(
            name="child_age_months",
            type="int",
            required=False,
            priority=20,
            ask_prompt="How old is the child, in months?",
        ),
        SlotSpec(
            name="district",
            type="string",
            required=False,
            priority=30,
            ask_prompt="Which district are you in, so I can find the nearest centre?",
        ),
    ],
    safety_critical=False,
)

# --------------------------------------------------------------------------- #
# Mission Vatsalya — child protection (safety-critical)
# --------------------------------------------------------------------------- #
VATSALYA_CARD = AgentCapabilityCard(
    scheme="vatsalya",
    display_name="Vatsalya (Child Protection)",
    description=(
        "Child protection and welfare: how to report a child in need of care, "
        "adoption via CARA, foster care and sponsorship, missing-child support, "
        "and routing to DCPU / CWC. Safety-critical."
    ),
    example_utterances=[
        "How do I adopt a child?",
        "I want to report a child who needs help",
        "What is the foster care process?",
        "How can I sponsor a child's care?",
        "Bachche ko god kaise le?",
    ],
    keywords=[
        "mission vatsalya", "vatsalya", "adopt", "god lena", "foster", "sponsor", "cara", "child protection",
        "care and protection", "report a child", "child in need", "child who needs",
        "cwc", "dcpu", "child welfare", "orphan", "anath", "balgrah",
        "child care institution", "गोद", "अनाथ", "बाल कल्याण",
    ],
    required_slots=[],
    optional_slots=[
        SlotSpec(
            name="district",
            type="string",
            required=False,
            priority=30,
            ask_prompt="Which district are you in, so I can point you to the right office?",
        ),
    ],
    safety_critical=True,
)

# --------------------------------------------------------------------------- #
# Mission Shakti — women safety & empowerment (safety-critical)
# --------------------------------------------------------------------------- #
SHAKTI_CARD = AgentCapabilityCard(
    scheme="shakti",
    display_name="Shakti (Women Empowerment)",
    description=(
        "Women's safety and empowerment: One Stop Centres, Women Helpline 181, "
        "PMMVY maternity benefit eligibility and instalments, legal-rights "
        "awareness, Sakhi Niwas, Nari Adalat, and Beti Bachao Beti Padhao. "
        "Safety-critical."
    ),
    example_utterances=[
        "Am I eligible for PMMVY?",
        "Kya mujhe PMMVY ka labh mil sakta hai?",
        "What is a One Stop Centre?",
        "Tell me about Mahila Shakti schemes",
        "How do I apply for maternity benefit?",
        "What are my rights against dowry?",
    ],
    keywords=[
        "pmmvy", "matru vandana", "maternity benefit", "one stop", "osc", "sakhi",
        "181", "mission shakti", "mahila", "nari adalat", "sakhi niwas",
        "beti bachao", "empower", "dowry", "dahej", "rights", "adhikar",
        "women's safety", "women safety", "womens safety", "women's empowerment", "women empowerment",
    ],
    required_slots=[],
    optional_slots=[
        SlotSpec(
            name="child_order",
            type="enum",
            required=False,
            priority=20,
            ask_prompt="Is this for your first child or a later child?",
            enum_values=["first", "second", "later"],
        ),
        SlotSpec(
            name="income_band",
            type="enum",
            required=False,
            priority=20,
            ask_prompt="Is the household BPL / NFSA eligible, or above that?",
            enum_values=["bpl", "below_threshold", "above_threshold"],
        ),
        SlotSpec(
            name="district",
            type="string",
            required=False,
            priority=30,
            ask_prompt="Which district are you in?",
        ),
    ],
    safety_critical=True,
)

# --------------------------------------------------------------------------- #
# General / fallback — scheme discovery & navigation
# --------------------------------------------------------------------------- #
GENERAL_CARD = AgentCapabilityCard(
    scheme="general",
    display_name="General Assistance",
    description=(
        "Scheme discovery and navigation when the citizen's need spans schemes "
        "or is not yet clear: 'what am I eligible for', 'how do I apply', general "
        "MWCD guidance."
    ),
    example_utterances=[
        "What government schemes can I get?",
        "Mujhe kaun si yojana mil sakti hai?",
        "How do I contact the women and child department?",
    ],
    keywords=["scheme", "yojana", "eligible", "apply", "help", "madad", "government"],
    required_slots=[],
    optional_slots=[],
    safety_critical=False,
    fallback=True,
)


# Canonical lookup. Registry assigns these to specialist instances; the router
# reads cards FROM the registry, so this dict is just the source of definitions.
ALL_CARDS: dict[str, AgentCapabilityCard] = {
    POSHAN_CARD.scheme: POSHAN_CARD,
    VATSALYA_CARD.scheme: VATSALYA_CARD,
    SHAKTI_CARD.scheme: SHAKTI_CARD,
    GENERAL_CARD.scheme: GENERAL_CARD,
}

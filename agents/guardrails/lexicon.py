"""L1 safety lexicon — fast, high-recall distress detection.

This is the FIRST line of the safety gate. It is intentionally high-recall:
a false positive (escalating a non-distress message) is a minor annoyance,
a false negative (missing a woman/child in danger) is the one failure we
cannot ship. L2 (the LLM classifier in safety.py) adds precision and catches
indirect disclosure this layer cannot.

Coverage spans three scripts citizens actually type in:
  - English
  - Romanized Hindi / Hinglish ("mujhe maar rahe hain")
  - Devanagari Hindi ("मुझे मार रहे हैं")

Matching is substring-based on a normalized (lowercased) string, so word
fragments inside larger words match too (acceptable for high recall).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DistressCategory(str, Enum):
    """Routes to the correct helpline set."""

    WOMEN_VIOLENCE = "women_violence"   # → 181 + 112 + One Stop Centre
    CHILD_DANGER = "child_danger"       # → 1098 + 112 + DCPU/CWC
    GENERIC_EMERGENCY = "generic"       # → 112 (+ both helplines)


# --- Trigger phrases per category ---
# Keep phrases SHORT and high-signal; substring matching does the rest.

_WOMEN_VIOLENCE: list[str] = [
    # English
    "beating me", "hitting me", "he hits", "husband hits", "husband beats",
    "domestic violence", "violence towards", "is violent", "violent towards",
    "abusive", "abuses me", "rape", "molest", "threaten me", "threatens me",
    "harass me", "harassing me", "harassment", "stalking me", "threatening me",
    "marital", "in-laws beat", "burn me", "kill me",
    "i am not safe", "i'm not safe", "scared of my husband", "afraid of my husband",
    # Romanized Hindi / Hinglish — include common verb conjugations of maarna/peetna
    "maar rahe", "maar raha", "maar rahi", "maar rah", "mar raha", "mar rahi",
    "maarte hain", "maarta hai", "maarti hai", "mujhe maar", "mujhe mar", "maara",
    "peet rahe", "peet raha", "peet rahi", "peetta", "peet-ta", "pitai",
    "ghar me violence", "ghar mein violence", "par violence", "violence hota",
    "pati maar", "pati peet", "pati mujhe",
    "dhamki", "dhamka", "pareshan kar", "ched", "chhed",
    "balatkar", "darr lagta", "dar lagta", "mujhe bachao", "bachao mujhe",
    "koi bachao", "madad chahiye", "sasural", "jaan se maar",
    # Devanagari
    "मार रहे", "मार रहा", "मार रही", "मुझे मार", "मारता", "मारती", "पीट",
    "हिंसा", "धमकी", "बलात्कार", "परेशान", "छेड़", "मुझे बचाओ", "डर लगता",
    "जान से",
]

_CHILD_DANGER: list[str] = [
    # English
    "missing child", "child is missing", "lost child", "kidnap", "abduct",
    "child labour", "child labor", "bonded labour", "child abuse", "child is being",
    "trafficking", "child trafficking", "selling child", "runaway child",
    "child in danger", "beating the child", "child is beaten",
    # Romanized Hindi / Hinglish
    "bachcha gum", "baccha gum", "bachcha kho", "baccha kho", "bachche ko maar",
    "bacche ko maar", "bal majdoori", "bal mazdoori", "bachcha bik", "bachcha utha",
    "apहरण", "bachche ka shoshan",
    # Devanagari
    "बच्चा गुम", "बच्चा खो", "अपहरण", "बाल मजदूरी", "बाल श्रम",
    "बच्चे को मार", "तस्करी", "बच्चे का शोषण",
]

_GENERIC_EMERGENCY: list[str] = [
    # English
    "emergency", "help me", "save me", "i want to die", "suicide",
    "kill myself", "end my life", "in danger", "please help",
    # Romanized Hindi / Hinglish
    "aatmhatya", "atmahatya", "marna chahti", "marna chahta", "jaan dena",
    "khatre me", "khatre mein", "bachao mujhe",
    # Devanagari
    "आत्महत्या", "मरना चाहती", "मरना चाहता", "खतरे", "बचाओ", "मदद करो",
]


_CATEGORY_PHRASES: dict[DistressCategory, list[str]] = {
    DistressCategory.WOMEN_VIOLENCE: _WOMEN_VIOLENCE,
    DistressCategory.CHILD_DANGER: _CHILD_DANGER,
    DistressCategory.GENERIC_EMERGENCY: _GENERIC_EMERGENCY,
}


@dataclass(frozen=True)
class LexiconHit:
    category: DistressCategory
    matched_phrase: str


def normalize(text: str) -> str:
    """Lowercase + collapse whitespace. Devanagari is unaffected by lower()."""
    return " ".join(text.lower().split())


def scan(text: str) -> LexiconHit | None:
    """Return the first distress match, or None.

    Order matters: women-violence and child-danger are checked before the
    generic bucket so we surface the most specific helpline set.
    """
    norm = normalize(text)
    for category in (
        DistressCategory.WOMEN_VIOLENCE,
        DistressCategory.CHILD_DANGER,
        DistressCategory.GENERIC_EMERGENCY,
    ):
        for phrase in _CATEGORY_PHRASES[category]:
            if normalize(phrase) in norm:
                return LexiconHit(category=category, matched_phrase=phrase)
    return None

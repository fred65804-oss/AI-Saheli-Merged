# mcp/helpline_directory/loader.py
"""
Loads helplines.yaml at process start, validates every row against the
Pydantic schema, and exposes a simple in-memory lookup.

Fail fast: if the YAML is malformed the server refuses to boot. This is
correct — a silently-degraded helpline table is worse than a down service.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .schemas import Category, HelplineEntry, Language, Scheme

# helplines.yaml lives next to this file, under data/.
DEFAULT_YAML_PATH = Path(__file__).parent / "data" / "helplines.yaml"


class HelplineStore:
    def __init__(self, yaml_path: Path):
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        self.version = raw["version"]
        self.updated = raw["updated"]
        # Parse each row through Pydantic — invalid rows raise on boot, not on request.
        self.entries: list[HelplineEntry] = [HelplineEntry(**row) for row in raw["helplines"]]
        self._validate_invariants()

    def _validate_invariants(self) -> None:
        # Every category we might be asked about must have at least one matching entry.
        # This is what stops us from shipping a distress category with no answer.
        covered = {cat for e in self.entries for cat in e.categories}
        required = set(Category)
        missing = required - covered
        if missing:
            raise ValueError(f"helplines.yaml missing coverage for: {missing}")

    def lookup(
        self,
        category: Category,
        lang: Language = Language.EN,
        scheme: Scheme | None = None,
    ) -> tuple[HelplineEntry, list[HelplineEntry], str | None]:
        """Return (primary, secondary, escalation_note) for a category.

        Selection rules:
          - keep only entries serving ``category``;
          - when a ``scheme`` hint is given, the scheme-specific line leads
            (e.g. women_safety + shakti → 181, not the generic 112) — a
            category/scheme match outranks raw priority;
          - within the same scheme-match bucket, rank by priority (0 = highest —
            so with no scheme hint, 112 leads on any life-safety category),
            then a language match, then id for determinism;
          - primary = top-ranked; secondary = the rest, in rank order.

        ``lang`` is a soft tie-breaker only — we never drop an entry for
        language, because a life-safety number in the "wrong" language still
        saves a life.
        """
        matches = [e for e in self.entries if category in e.categories]
        if not matches:
            # Guarded against by _validate_invariants at boot, but stay explicit.
            raise KeyError(f"no helpline entry serves category {category!r}")

        def rank(e: HelplineEntry) -> tuple:
            scheme_miss = 0 if (scheme is not None and e.scheme == scheme) else 1
            lang_miss = 0 if lang in e.languages else 1
            return (scheme_miss, e.priority, lang_miss, e.id)

        ranked = sorted(matches, key=rank)
        primary, secondary = ranked[0], ranked[1:]

        # Concatenate escalation notes (primary first) for agent convenience.
        notes = [e.escalation_note for e in ranked if e.escalation_note]
        escalation_note = " ".join(notes) if notes else None

        return primary, secondary, escalation_note


# --------------------------------------------------------------------------- #
# Process-wide singleton — loaded (and validated) once, reused across requests.
# --------------------------------------------------------------------------- #
_STORE: HelplineStore | None = None


def get_store() -> HelplineStore:
    global _STORE
    if _STORE is None:
        _STORE = HelplineStore(DEFAULT_YAML_PATH)
    return _STORE

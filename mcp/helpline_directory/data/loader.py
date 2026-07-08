# mcp/helpline_directory/loader.py
"""
Loads helplines.yaml at process start, validates every row against the
Pydantic schema, and exposes a simple in-memory lookup.

Fail fast: if the YAML is malformed the server refuses to boot. This is
correct — a silently-degraded helpline table is worse than a down service.
"""

from pathlib import Path
import yaml
from schemas import HelplineEntry, Category, Language, Scheme

class HelplineStore:
    def __init__(self, yaml_path: Path):
        raw = yaml.safe_load(yaml_path.read_text(encoding = "utf-8"))
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

    def lookup(self, category: Category, scheme: Scheme | None = None) -> tuple[HelplineEntry, list[HelplineEntry]]:
        candidates = [e for e in self.entries if category in e.categories]

        # If a scheme hint was given, prefer entries tagged to that scheme,
        # but do NOT drop scheme-null entries (e.g. 112) — those are cross-cutting
        def sort_key(e: HelplineEntry) -> tuple[int, int]:
            scheme_match_bonus = 0 if (scheme and e.scheme == scheme) else 1
            return (e.priority, scheme_match_bonus)

        candidates.sort(key = sort_key)

        if not candidates:
            # Invariant check should prevent this, but defensive fallback:
            raise LookupError(f"No category found for category=>{category}")

        return candidates[0], candidates[1:]

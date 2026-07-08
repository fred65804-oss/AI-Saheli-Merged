# mcp/geo_locator/loader.py
"""
Loads facilities.json at process start, validates every record against the
Pydantic schema, and exposes an in-memory lookup with a state-level fallback.

Same fail-fast philosophy as the helpline store: a malformed dataset refuses to
boot rather than silently serving a citizen a wrong or empty facility list.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import Facility, ServiceType

DEFAULT_JSON_PATH = Path(__file__).parent / "data" / "facilities.json"

# Shown when we have no data for a district — graceful degradation, not a crash.
_NO_DATA_NOTE = (
    "No demo data for this district. In production, geo_locator resolves this "
    "live via the Poshan Tracker (AWC), Mission Shakti Sakhi OSC directory (OSC), "
    "and the Mission Vatsalya / CPMS directory (DCPU, CWC)."
)


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


class FacilityStore:
    def __init__(self, json_path: Path):
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        self.meta: dict = raw.get("_meta", {})
        # Parse each record through Pydantic — invalid rows raise on boot, not on request.
        self.facilities: list[Facility] = [Facility(**row) for row in raw["facilities"]]

    def find(
        self,
        service_type: ServiceType,
        district: str,
        state: str | None = None,
        limit: int = 3,
    ) -> tuple[list[Facility], str | None, str | None]:
        """Return (facilities, district_matched, note).

        Resolution order:
          1. exact district match (case/space-insensitive) for the service type;
          2. if none and ``state`` is given, fall back to any facility of that
             type in the same state (note explains the widening);
          3. if still none, return an empty list with a graceful no-data note.
        """
        of_type = [f for f in self.facilities if f.type == service_type]

        d = _norm(district)
        exact = [f for f in of_type if _norm(f.district) == d]
        if exact:
            return exact[:limit], exact[0].district, None

        if state is not None:
            st = _norm(state)
            in_state = [f for f in of_type if _norm(f.state) == st]
            if in_state:
                note = (
                    f"No {service_type.value} on record in '{district}'. "
                    f"Showing nearest available in {in_state[0].state}."
                )
                return in_state[:limit], in_state[0].state, note

        return [], None, _NO_DATA_NOTE


# --------------------------------------------------------------------------- #
# Process-wide singleton — loaded (and validated) once, reused across requests.
# --------------------------------------------------------------------------- #
_STORE: FacilityStore | None = None


def get_store() -> FacilityStore:
    global _STORE
    if _STORE is None:
        _STORE = FacilityStore(DEFAULT_JSON_PATH)
    return _STORE

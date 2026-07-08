"""Terminal REPL over the orchestrator graph — for live demos and manual checks.

Usage:
    python scripts/chat_cli.py

Type messages as a citizen. State persists for the session. Ctrl-C to exit.
Works offline (keyword routing + lexicon safety) or, with ANTHROPIC_API_KEY set,
with full LLM routing and warm phrasing.
"""

from __future__ import annotations

import asyncio
import sys
import uuid

# Ensure the project root is importable when run as a script.
sys.path.insert(0, ".")

from agents.orchestrator.graph import default_orchestrator, run_turn  # noqa: E402
from apps.backend.config import get_settings  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # show emoji / Devanagari on Windows
except Exception:
    pass


BANNER = """
============================================================
  AI Saheli — Orchestrator (demo CLI)
  Schemes: Poshan · Vatsalya · Mission Shakti
  LLM: {llm}
  Type your message. Ctrl-C to quit.
============================================================
"""


async def main() -> None:
    settings = get_settings()
    graph = default_orchestrator()
    session_id = uuid.uuid4().hex
    print(
        BANNER.format(
            llm="LIVE (" + settings.resolved_provider + ":" + settings.resolved_model + ")"
            if settings.has_llm_key
            else "OFFLINE (keyword + lexicon only)"
        )
    )
    while True:
        try:
            msg = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nTake care. 🙏")
            return
        if not msg:
            continue
        state = await run_turn(graph, session_id=session_id, message=msg)
        tags = []
        if state.get("intent"):
            tags.append(f"intent={state['intent']}")
        if state.get("escalation"):
            tags.append("ESCALATION")
        if state.get("awaiting_input"):
            tags.append("awaiting-info")
        cites = state.get("citations") or []
        if cites:
            tags.append(f"{len(cites)} source(s)")
        meta = f"  [{' · '.join(tags)}]" if tags else ""
        print(f"Saheli: {state.get('response', '')}{meta}\n")


if __name__ == "__main__":
    asyncio.run(main())

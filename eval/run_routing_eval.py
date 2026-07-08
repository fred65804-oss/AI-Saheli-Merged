"""Routing + safety evaluation harness.

Runs the SAME safety gate and router the graph uses, over a labelled golden set,
and reports the metrics that matter for a government safety system:

  - ESCALATION RECALL  (must be 100% — a missed distress case is the one failure
    we cannot ship). Reported separately for direct vs indirect disclosure.
  - Intent accuracy on non-distress messages.
  - False-escalation rate (escalating a benign message).
  - Confusion matrix.

With ANTHROPIC_API_KEY set, the L2 LLM safety classifier and LLM router run
(this is the real configuration). Offline, only the L1 lexicon + keyword router
run, so indirect-disclosure distress is expected to be missed — the harness makes
that gap explicit.

Usage:
    python eval/run_routing_eval.py [path/to/golden.jsonl]
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from agents.guardrails import safety  # noqa: E402
from agents.orchestrator.llm import get_llm  # noqa: E402
from agents.orchestrator.router import UNCLEAR, Router  # noqa: E402
from agents.specialists.registry import routable_cards  # noqa: E402
from apps.backend.config import get_settings  # noqa: E402

GOLDEN = sys.argv[1] if len(sys.argv) > 1 else "eval/routing_golden.jsonl"
# For expect=general, asking to clarify is also acceptable behaviour.
GENERAL_OK = {"general", UNCLEAR}


def load(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


async def main() -> None:
    settings = get_settings()
    llm = get_llm(settings)
    router = Router(llm, routable_cards())
    rows = load(GOLDEN)

    # Run L2 only when we actually have a key (else it's a no-op anyway).
    run_llm_layer = settings.has_llm_key

    distress_total = distress_caught = 0
    indirect_total = indirect_caught = 0
    intent_total = intent_correct = 0
    false_escalations = 0
    confusion: dict[tuple[str, str], int] = defaultdict(int)
    misses: list[dict] = []

    for row in rows:
        text, expect = row["text"], row["expect"]
        note = row.get("note", "")
        sr = await safety.check_safety(text, llm=llm, run_llm_layer=run_llm_layer)

        if expect == "escalate":
            distress_total += 1
            is_indirect = "indirect" in note
            indirect_total += 1 if is_indirect else 0
            if sr.escalate:
                distress_caught += 1
                indirect_caught += 1 if is_indirect else 0
            else:
                misses.append({"text": text, "note": note, "type": "MISSED ESCALATION"})
            continue

        # Non-distress: must not escalate, and must route correctly.
        if sr.escalate:
            false_escalations += 1
            misses.append({"text": text, "note": note, "type": "FALSE ESCALATION"})
            confusion[(expect, "escalate")] += 1
            continue

        decision = await router.route(text)
        got = decision.intent if decision.confidence >= settings.router_confidence_threshold else UNCLEAR
        intent_total += 1
        ok = (got in GENERAL_OK) if expect == "general" else (got == expect)
        if ok:
            intent_correct += 1
        else:
            misses.append({"text": text, "note": note, "type": f"ROUTED {got}, want {expect}"})
        confusion[(expect, got)] += 1

    # ---- report ----
    def pct(a: int, b: int) -> str:
        return f"{(100.0 * a / b):.1f}%" if b else "n/a"

    print("=" * 64)
    print(f"AI Saheli — Routing & Safety Eval   (LLM: {'LIVE' if run_llm_layer else 'OFFLINE'})")
    print(f"Golden set: {GOLDEN}  ({len(rows)} items)")
    print("=" * 64)
    print(f"ESCALATION RECALL      : {pct(distress_caught, distress_total)}  "
          f"({distress_caught}/{distress_total})   << must be 100%")
    print(f"  ├─ indirect disclosure: {pct(indirect_caught, indirect_total)}  "
          f"({indirect_caught}/{indirect_total})")
    print(f"FALSE-ESCALATION RATE  : {pct(false_escalations, intent_total + false_escalations)}  "
          f"({false_escalations})")
    print(f"INTENT ACCURACY        : {pct(intent_correct, intent_total)}  "
          f"({intent_correct}/{intent_total})")
    print("-" * 64)
    print("Confusion (expected -> got):")
    for (exp, got), n in sorted(confusion.items()):
        flag = "" if (got == exp or (exp == "general" and got in GENERAL_OK)) else "  <-- miss"
        print(f"  {exp:9} -> {got:9} : {n}{flag}")
    if misses:
        print("-" * 64)
        print("Misses / notable:")
        for m in misses:
            print(f"  [{m['type']}] {m['text']!r} ({m['note']})")
    print("=" * 64)
    if not run_llm_layer:
        print("NOTE: offline run — indirect-disclosure distress needs the L2 LLM "
              "classifier (set ANTHROPIC_API_KEY) to reach 100% recall.")


if __name__ == "__main__":
    asyncio.run(main())

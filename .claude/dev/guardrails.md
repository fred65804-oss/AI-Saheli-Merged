# Guardrails & Safety Design — AI Saheli

## Core Safety Philosophy
This is a government-facing AI serving vulnerable citizens. Safety failures are reputational and humanitarian risks. Every safeguard is non-negotiable.

---

## Guardrail Layers (Defense in Depth)

### Layer 1 — System Prompt Rules (Per Agent)
Baked into every agent's system prompt:
- "You are an information assistant. You do not provide medical, legal, or financial advice."
- "Always cite the official government source for every factual claim."
- "If the citizen appears to be in distress or danger, immediately provide the relevant helpline and stop."
- "If you are unsure, say so and refer to the nearest authority."

### Layer 2 — Escalation Classifier (Pre-Agent)
A fast, dedicated classifier (LLM + keyword patterns) runs on EVERY inbound message before routing to a specialist.

```python
ESCALATION_TRIGGERS = {
    "vatsalya": [
        "abuse", "assault", "trafficking", "missing child", "kidnap",
        "bonded labour", "child labour", "in danger", "help me", "scared"
        # + Hindi/regional equivalents
    ],
    "shakti": [
        "violence", "beating", "threat", "husband hitting", "harassment",
        "in danger", "help", "afraid", "sexual assault", "stalking"
        # + Hindi/regional equivalents
    ]
}
```

If triggered: skip all agents → return `EscalationResponse` with helpline + nearest facility.

### Layer 3 — Grounding Validator (Post-Agent)
After agent generates a response:
1. Extract factual claims (benefit amounts, eligibility conditions, process steps)
2. Check each claim is supported by a retrieved passage (source ID exists in context)
3. If any claim is unsupported → remove it → replace with: "For accurate details, please contact [authority]"
4. Log `grounding_fail=true` if triggered

### Layer 4 — Scope Guard (Post-Agent)
Block specific output patterns:
- Medical diagnosis: "you have [condition]" → blocked
- Legal advice: "you should file a case" → blocked → "You may want to consult NALSA (15100)"
- Financial advice: "invest in" → blocked
- Personalised clinical recommendations: blocked → refer to ANM/doctor

### Layer 5 — PII Guard (Inbound + Outbound)
- Detect PII in inbound (Aadhaar numbers, phone numbers, names) → strip from logs
- Detect PII in outbound (should not happen; if agent generates, strip or block)
- Demo personas only — never accept or store real personal data

---

## Escalation Response Templates

### Child Distress (Vatsalya)
```
"I can see this situation requires immediate support.

📞 CHILDLINE 1098 (free, 24×7, for children in need)
📞 Emergency: 112

[If geo available]: Your nearest Child Welfare Committee is at [facility_name], [address], [phone].

Please contact them immediately. They are trained to help."
```

### Women Safety (Shakti)
```
"I can see you need urgent support.

📞 Women Helpline 181 (free, 24×7)
📞 Emergency: 112

[If geo available]: Your nearest One Stop Centre / Sakhi Centre is at [facility_name], [address], [phone].

You are not alone. These services are confidential and free."
```

---

## What the AI Will NEVER Do

| Prohibited | Why | Alternative |
|---|---|---|
| Collect abuse details | Re-traumatization risk | Surface helpline, let trained counsellors handle |
| Diagnose medical conditions | Liability, harm | Give information, refer to ANM/doctor |
| Provide legal advice | Requires qualified lawyer | Refer to NALSA 15100 |
| Promise specific benefit amounts without verification | Rules change | Cite source + recommend verification at office |
| Act as a counsellor for trauma | Out of scope | Refer to iCall / trained services |
| Store real PII | Privacy, regulatory | Synthetic personas only in demo |
| Make promises about government action | Can't be fulfilled | Provide process information |

---

## Responsible AI Framing for Demo
The guardrails are not just safety measures — they are **features to demonstrate** to Ministry leadership:
- Show an escalation trigger firing in real-time
- Show the grounding citation appearing in the response
- Show the scope guard blocking inappropriate advice
- Show `escalation=true` in the analytics log

This **demonstrates responsible AI** which is exactly what a government deployment requires and what will win leadership confidence.

---

## Audit Trail
Every interaction logs:
- `escalation: bool` + `escalation_reason: str`
- `grounding_fail: bool`
- `scope_block: bool`
- `tool_calls: list` (full audit of what the agent accessed)
- `model_used: str`
- `latency_ms: int`

This gives the Ministry a complete audit trail of AI behavior — critical for governance.

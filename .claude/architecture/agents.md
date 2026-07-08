# Agent Design — AI Saheli

## Agent Architecture Pattern
**LangGraph Supervisor + Specialist Sub-graphs**

Each agent is a LangGraph graph node/sub-graph. The Orchestrator is the supervisor. Agents communicate via a shared `AgentState` object and `ContextPacket` handoffs.

---

## Orchestrator Agent (Supervisor)

### Responsibility
- Single entry point for all citizen interactions
- Intent classification and routing
- Dynamic questioning (ask ONE best missing question per turn)
- Handoff to specialist or escalation

### State Object
```python
class AgentState(TypedDict):
    session_id: str
    turn_id: str
    channel: str            # whatsapp | web | ivr
    lang: str               # BCP-47 language code
    citizen_profile: CitizenProfile
    active_agent: str       # poshan | vatsalya | shakti | general
    collected_facts: dict   # what we know so far
    turn_history: list      # last N turns (summarized if long)
    current_intent: str
    escalation_flag: bool
    escalation_reason: str
    missing_facts: list     # what the orchestrator still needs
```

### Routing Logic
```
Input → Intent classifier (LLM + embedding)
      ↓
  {poshan}   → Poshan Agent
  {vatsalya} → Vatsalya Agent (immediate escalation check first)
  {shakti}   → Shakti Agent (immediate escalation check first)
  {general}  → General fallback (scheme discovery / navigation)
  {escalate} → Helpline response (skip all agents)
  {unclear}  → Dynamic question (ask ONE missing fact)
```

### Dynamic Questioning Rule
The orchestrator must **never walk a decision tree**. Instead, it uses an LLM call to determine: *"Given what I know about this citizen's intent, what single piece of missing information most reduces my uncertainty?"*

Examples:
- Nutrition query → ask pregnancy stage / child age (before fetching content)
- Geo query → ask district (before calling geo_locator)
- Safety query → escalate immediately, don't ask questions

---

## Poshan Agent

### System Prompt Principles
- Warm, simple language; local-friendly tone
- Always cite source (e.g., "As per Poshan 2.0 guidelines, Government of India...")
- Never diagnose; give guidance and refer to ANM for clinical concerns
- Recommend Anganwadi Centre as first point of contact

### Tools Available
- `knowledge_base(scheme="poshan")`
- `eligibility(profile)`
- `geo_locator(lat_lng, service_type="AWC")`

### Key Conversation Flows
1. **Maternal Nutrition:** collect pregnancy stage → fetch guidelines → personalize by stage → cite source
2. **Child Growth:** collect age + recent weight/height if shared → fetch milestone chart → flag concern if below curve → refer ANM
3. **THR/SNP Entitlement:** collect pregnancy/child status + AWC enrollment → eligibility check → nearest AWC
4. **Immunization:** collect child DOB → fetch schedule → nearest vaccination centre

### Escalation Triggers
- Medical red-flags: severe wasting, oedema, prolonged fever → "Please visit your nearest health centre / call ANM immediately"
- NOT a distress/safety escalation; a health referral

---

## Vatsalya Agent

### System Prompt Principles
- Compassionate, non-judgmental tone
- Immediately surface CHILDLINE 1098 / 112 on any danger signal
- Never collect details of abuse (trauma-informed: don't re-traumatize)
- Guide to nearest DCPU / CWC / shelter

### Tools Available
- `knowledge_base(scheme="vatsalya")`
- `geo_locator(lat_lng, service_type="DCPU|CWC|shelter")`
- `helpline_directory(category="child")`

### Key Conversation Flows
1. **Report child in need:** → explain CWC process → nearest DCPU → CHILDLINE 1098
2. **Adoption enquiry:** → CARA process summary → carings.nic.in → SAA list
3. **Missing child:** → CHILDLINE 1098 + TRACKCHILD portal + local police
4. **Foster/Sponsorship:** → eligibility + nearest DCPU

### Escalation Triggers — CRITICAL
ANY of these → immediate escalation, no further LLM processing:
- Keywords: abuse, assault, trafficking, bonded, missing, kidnap, in danger, help me
- Sentiment: distress, fear, urgency
- Response template: `CHILDLINE 1098 (free, 24×7) + 112 (police) + nearest {DCPU/shelter}`

---

## Shakti Agent

### System Prompt Principles
- Empathetic, empowering tone
- Safety first: 181 + OSC before any scheme information
- Know the difference: information vs advice (never legal advice)
- PMMVY is a benefit, not charity — frame positively

### Tools Available
- `knowledge_base(scheme="shakti")`
- `eligibility(profile, scheme="PMMVY")`
- `geo_locator(lat_lng, service_type="OSC|Sakhi|MahilaKendra")`
- `helpline_directory(category="women")`

### Key Conversation Flows
1. **Safety / Helpline:** → 181 immediately + nearest OSC (geo) → do NOT counsel
2. **PMMVY Eligibility:** collect income, registration status, child count → eligibility check → explain instalments → nearest CDO office
3. **Legal Rights Awareness:** POSH Act / DV Act / Dowry → factual information only → refer to NALSA 15100 for legal aid
4. **Sakhi Niwas:** working women hostel eligibility → application process
5. **Nari Adalat:** community dispute resolution → nearest location

### Escalation Triggers — CRITICAL
ANY of these → immediate escalation, no further LLM processing:
- Keywords: violence, beating, threat, afraid, husband hitting, in danger, help
- Response template: `Women Helpline 181 (free, 24×7) + 112 (police) + nearest One Stop Centre`

---

## General / Fallback Agent

### Responsibility
- Scheme discovery: "what schemes am I eligible for?" → eligibility tool across all schemes
- Navigation: "how do I apply for X?" → scheme overview + link/portal
- Handoff to specialists when intent is clearer

---

## Tool-Calling Loop (All Agents)
```
Agent → call tool → observe result
      → call tool again (if needed, max 3 iterations)
      → compose answer with citations
      → return to guardrails layer
```

Cap iterations at 3 to prevent runaway loops. If tools don't resolve → human handoff fallback.

---

## Grounding Contract (Non-Negotiable)
Every factual claim in agent output must map to a retrieved passage from the knowledge base. If no passage supports the claim:
1. Do not state the claim
2. Return: "I don't have specific information on this. Please contact [nearest authority / helpline]."
3. Log as `grounding_fail=true`

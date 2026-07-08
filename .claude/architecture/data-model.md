# Data Model — AI Saheli

## Demo Constraint
**Synthetic personas only. Zero real PII stored or processed in the demo.**

---

## Core Schemas

### CitizenProfile (Redis session + Postgres durable)
```python
class CitizenProfile(BaseModel):
    id: str                          # synthetic UUID
    lang: str                        # BCP-47 (hi, ta, te, bn, mr...)
    channel: str                     # whatsapp | web
    district: str | None             # for geo queries
    lat: float | None
    lng: float | None
    role: Literal["woman", "mother", "pregnant", "parent", "caregiver"]
    pregnancy_stage: str | None      # "1st trimester" | "2nd" | "3rd" | "postpartum"
    child_age_months: int | None
    income_band: str | None          # "BPL" | "below_1.5L" | "1.5L_to_3L" | "above_3L"
    sc_st: bool | None
    # All fields optional — collected dynamically via questioning
```

### Session (Redis, TTL 24h)
```python
class Session(BaseModel):
    session_id: str
    citizen_id: str
    channel: str
    active_agent: str
    turn_count: int
    collected_facts: dict            # facts gathered this session
    last_intent: str
    escalation_flag: bool
    created_at: datetime
    updated_at: datetime
```

### MessageLog (Postgres — feeds analytics)
```python
class MessageLog(BaseModel):
    id: UUID
    session_id: str
    ts: datetime
    channel: str
    lang: str
    direction: Literal["inbound", "outbound"]
    raw_text: str | None             # DO NOT store if real PII detected
    intent: str
    scheme: str | None               # poshan | vatsalya | shakti | general
    agent_used: str | None
    tool_calls: list[str]            # tool names called this turn
    latency_ms: int                  # total pipeline latency
    asr_latency_ms: int | None
    nmt_latency_ms: int | None
    llm_latency_ms: int | None
    tts_latency_ms: int | None
    escalation: bool
    escalation_reason: str | None
    grounding_fail: bool
    feedback_rating: int | None      # thumbs up/down from user
```

### KBChunk (Qdrant)
```python
class KBChunk(BaseModel):
    id: str
    scheme: str                      # poshan | vatsalya | shakti
    text: str                        # 300–500 tokens
    embedding: list[float]           # 768-dim (multilingual-e5-large)
    source_url: str                  # official govt URL
    source_doc: str                  # document name
    section: str                     # heading hierarchy
    language: str                    # en | hi | (source lang of doc)
    last_updated: date
```

### SchemeRule (Postgres — eligibility engine)
```python
class SchemeRule(BaseModel):
    id: UUID
    scheme: str
    benefit_name: str
    benefit_amount: str | None       # e.g., "₹5,000 in 3 instalments"
    eligibility_conditions: dict     # JSON predicate (income, role, child_count, etc.)
    documents_required: list[str]
    application_channel: str         # CDO office | online portal | AWC
    source_url: str
    valid_from: date
    valid_until: date | None
```

### GeoFacility (Postgres — for demo mock dataset)
```python
class GeoFacility(BaseModel):
    id: UUID
    facility_type: str              # AWC | OSC | DCPU | CWC | PHC | hospital
    name: str
    district: str
    state: str
    lat: float
    lng: float
    address: str
    phone: str | None
    scheme: str | None              # which scheme this supports
```

---

## Demo Synthetic Personas

```python
DEMO_PERSONAS = [
    {
        "name": "Sunita Devi",
        "lang": "hi",
        "district": "Varanasi",
        "role": "pregnant",
        "pregnancy_stage": "2nd trimester",
        "income_band": "BPL",
        "sc_st": True,
        "journey": "poshan_maternal_nutrition"
    },
    {
        "name": "Kavitha",
        "lang": "ta",
        "district": "Madurai",
        "role": "mother",
        "child_age_months": 14,
        "income_band": "below_1.5L",
        "journey": "poshan_child_growth"
    },
    {
        "name": "Meena",
        "lang": "hi",
        "district": "Delhi",
        "role": "woman",
        "income_band": "BPL",
        "journey": "shakti_safety"
    },
    {
        "name": "Rajesh Kumar",
        "lang": "hi",
        "district": "Lucknow",
        "role": "parent",
        "child_age_months": 84,  # 7 years
        "journey": "vatsalya_child_welfare"
    }
]
```

---

## Analytics Queries (Dashboard)

```sql
-- Top intents by day
SELECT intent, scheme, COUNT(*) as count, DATE(ts) as day
FROM message_log
WHERE direction = 'inbound'
GROUP BY intent, scheme, day
ORDER BY count DESC;

-- Escalation rate by scheme
SELECT scheme,
    COUNT(*) FILTER (WHERE escalation=true) as escalations,
    COUNT(*) as total,
    ROUND(100.0 * COUNT(*) FILTER (WHERE escalation=true) / COUNT(*), 1) as pct
FROM message_log
WHERE direction = 'outbound'
GROUP BY scheme;

-- Average latency by channel
SELECT channel, AVG(latency_ms) as avg_ms, PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) as p95_ms
FROM message_log
GROUP BY channel;

-- Language distribution
SELECT lang, COUNT(*) as sessions
FROM message_log
GROUP BY lang ORDER BY sessions DESC;

-- District-wise demand heatmap data
SELECT district, scheme, COUNT(*) as queries
FROM message_log ml
JOIN citizen_profile cp ON ml.session_id = cp.id
GROUP BY district, scheme;
```

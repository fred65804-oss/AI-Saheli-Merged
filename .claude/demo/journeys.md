# Demo Journeys & Personas — AI Saheli

## Demo Philosophy
The 4 journeys are **scripted but live** — the system runs in real-time, not pre-recorded. The script guides what the demo operator types/speaks; the AI's actual responses must be grounded and correct.

---

## Synthetic Personas

### Sunita Devi
- **Language:** Hindi
- **Location:** Varanasi, Uttar Pradesh
- **Profile:** 28 years old, 6 months pregnant (2nd trimester), BPL household, SC
- **Channel:** WhatsApp (voice)
- **Journeys:** Maternal nutrition (J1), PMMVY eligibility (J4)

### Kavitha
- **Language:** Tamil (with some English)
- **Location:** Madurai, Tamil Nadu
- **Profile:** 26 years old, mother of a 14-month-old boy
- **Channel:** Web chat (text)
- **Journey:** Child growth milestone concern (J2)

### Meena
- **Language:** Hindi
- **Location:** Delhi
- **Profile:** 32 years old, married, seeking safety support
- **Channel:** WhatsApp (text, then voice option)
- **Journey:** Women safety escalation (J3)

### Rajesh Kumar
- **Language:** Hindi
- **Location:** Lucknow, Uttar Pradesh
- **Profile:** 38 years old, father of a 7-year-old child, concerned about child welfare
- **Channel:** Web chat
- **Journey:** Child protection information (optional J5)

---

## Journey 1 — Maternal Nutrition (Voice, Hindi, WhatsApp)
**Persona:** Sunita Devi | **Agent:** Poshan | **Duration:** ~2 min

### What to Demonstrate
- Voice input in Hindi on WhatsApp
- Bhashini ASR + NMT working
- Dynamic questioning (AI asks for pregnancy stage)
- Grounded, cited nutrition guidance
- Nearest Anganwadi Centre found by geo

### Script
```
[Demo operator speaks/types in WhatsApp as Sunita]

Turn 1 (voice note, Hindi):
"Mujhe pregnancy mein kya khana chahiye?"
[EN: "What should I eat during pregnancy?"]

Expected AI response (Hindi, voice):
"Namaste! Aapko apni pregnancy ke baare mein aur jankari de sakti hoon.
Aap ki pregnancy ka kaunsa mahina chal raha hai?"
[EN: "Hello! I can give you more specific guidance. Which month of pregnancy are you in?"]

Turn 2 (Sunita):
"Chhatha mahina chal raha hai" [6th month]

Expected AI response (Hindi):
- Iron-rich foods (chana, spinach, jaggery) for 2nd trimester
- Protein sources (dal, eggs, milk)
- POSHAN 2.0 supplementary nutrition entitlement (THR)
- "Yeh jaankari Poshan 2.0, Bharat Sarkar ke nirdeshon par aadharit hai"
  [Cites Poshan 2.0 guidelines]
- Nearest Anganwadi: "Aapke nikalte: Anganwadi Kendra No. 23, Sigra, Varanasi — 200 meter door"

[Show on screen: source citation card, AWC location on map]
```

---

## Journey 2 — Child Growth Milestone Concern
**Persona:** Kavitha | **Agent:** Poshan | **Duration:** ~2 min

### What to Demonstrate
- Text input in Tamil/English
- Child age-aware response
- Milestone guidance from official sources
- Appropriate referral (not diagnosis)
- Empathetic, reassuring tone

### Script
```
[Demo operator types in web chat as Kavitha]

Turn 1:
"My child is 14 months old and he is not walking yet. Is this normal?"

Expected AI response:
- Typical walking range: 9–15 months (most by 12–14 months)
- 14 months is within normal range; not a concern yet
- Signs to watch for (not walking by 18 months → see doctor)
- Cite: IAP/WHO child development guidelines
- Tip: encourage standing with support, play activities
- "If concerned, you can visit your nearest Anganwadi Centre or Auxiliary Nurse Midwife (ANM) for a growth check"
- Nearest AWC: Madurai district list

[Show: milestone card, AWC location]
```

---

## Journey 3 — Women Safety Escalation (HIGH IMPACT)
**Persona:** Meena | **Agent:** Shakti → Escalation | **Duration:** ~45 sec

### What to Demonstrate
- Safety-first routing (no delay)
- Escalation classifier firing in real-time
- Helpline + OSC shown immediately
- `escalation=true` appearing on the Ministry dashboard live
- NO autonomous counselling — AI knows its limits

### Script
```
[Demo operator types in WhatsApp as Meena]

Turn 1:
"Mujhe help chahiye. Mere pati mujhe maar rahe hain."
[EN: "I need help. My husband is beating me."]

Expected AI response (IMMEDIATE — within 1 second, no LLM thinking time):
"Main aapki madad karna chahti hoon.

📞 Mahila Helpline: 181 (muft, 24 ghante, 7 din)
📞 Police Emergency: 112

Aapke nikalte One Stop Centre (Sakhi Centre):
[OSC Name], [Address], [Phone]

Ye seva bilkul muft aur gupt hai. Aap akele nahi hain."

[On dashboard: escalation=true appears in real-time feed with scheme=shakti]
[Presenter: "Notice — the AI did not counsel. It immediately connected her to trained support.
This is responsible AI design for government deployment."]
```

---

## Journey 4 — PMMVY Eligibility + Ministry Dashboard Flip
**Persona:** Sunita Devi | **Agent:** Shakti | **Duration:** ~2 min + dashboard

### What to Demonstrate
- Scheme discovery and eligibility checking
- Correct benefit amounts with citations
- Application process guidance
- Flip to Ministry analytics view

### Script
```
[Demo operator continues as Sunita or starts fresh]

Turn 1:
"Kya mujhe PMMVY ka labh mil sakta hai? Main pehle bacche ki maa banne waali hoon."
[EN: "Can I get PMMVY benefit? I'm going to be a first-time mother."]

Expected AI response:
- Eligibility check: first child ✅, BPL household ✅
- Confirm: "Haan Sunita ji, aap PMMVY ke liye eligible hain"
- Benefit: ₹5,000 teen kiston mein (1st: ₹1,000 — registration; 2nd: ₹2,000 — ANC check; 3rd: ₹2,000 — after birth + vaccination)
- Cite: "PMMVY Operational Guidelines, Ministry of Women & Child Development"
- How to apply: nearest CDO office / AWC / wcd.gov.in
- Documents: Aadhaar, bank passbook, MCP card

Turn 2 (optional):
"Mujhe CDO office kahan milega?"
AI: Nearest CDO/CDPO office in Varanasi [address, phone]

[Presenter flips screen to Ministry Dashboard]
"Now, let me show you what the Ministry sees in real time..."
[Dashboard shows: 4 journeys logged, scheme distribution chart, Varanasi + Madurai + Delhi hotspots on map, 1 escalation (Meena), language breakdown, latency metrics]
```

---

## Demo Setup Checklist

### Before the Demo
- [ ] All 4 synthetic personas loaded in Postgres
- [ ] Qdrant populated with scheme knowledge (verified 20 test queries pass)
- [ ] WhatsApp demo number active and webhook responding
- [ ] Mock geo dataset includes Varanasi AWC, Madurai AWC, Delhi OSC, Lucknow DCPU
- [ ] Dashboard seeded with ~50 synthetic historical interactions for realistic charts
- [ ] Full dry-run completed twice without errors
- [ ] Backup video recording ready in case of live demo failure
- [ ] All environment variables set correctly in demo environment
- [ ] Latency tested: voice round-trip < 5 seconds on demo network

### During the Demo
- Journey order: J1 (WOW factor: voice) → J2 (child concern: empathy) → J3 (safety: impact) → J4 + Dashboard (policy: data)
- Have a laptop connected to projector AND a phone showing WhatsApp simultaneously
- Dashboard open on a second screen or tab, ready to flip

### Talking Points Per Journey
- J1: "Any woman with a ₹200 phone and WhatsApp can access expert nutrition guidance"
- J2: "The AI knows development milestones and knows when to refer — it's a first filter, not a replacement for ANMs"
- J3: "The AI never counsels in distress situations. It immediately connects to trained human support — this is by design"
- J4: "The Ministry now has a real-time intelligence layer on top of 14 lakh Anganwadis"

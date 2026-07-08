# Scheme Reference — Poshan, Vatsalya, Mission Shakti

## 1. Poshan 2.0 (& Saksham Anganwadi)
**Full Name:** Pradhan Mantri Poshan Shakti Nirman (Poshan 2.0)  
**Ministry:** MoWCD  
**Focus:** Nutrition security for women & children (first 1,000 days critical)

### Key Components
- **Supplementary Nutrition:** Take-Home-Ration (THR) for children 6m–3yr, pregnant/lactating women, adolescent girls
- **Early Childhood Care & Education (ECCE):** pre-school at Anganwadi Centres
- **ICDS Services:** 6 core services through ~14 lakh Anganwadis
- **Poshan Tracker:** digital monitoring platform for nutrition data
- **Anemia Mukt Bharat:** reducing anemia in women & children
- **SAAN (Scheme for Adolescent Girls):** nutrition & life skills for 14–18yr girls

### AI Agent Scope (Poshan Agent)
- Nutrition guidance based on pregnancy stage, child age, district
- "First 1,000 days" — when to escalate weight faltering to ANM
- THR/SNP entitlements and how to collect
- Nearest Anganwadi Centre (by geo)
- Immunization schedule (BCG, OPV, DPT, Measles, etc.)
- ECCE enrollment for children 3–6yr
- Poshan Mah / Poshan Pakhwada awareness

### Safety Rule
Provide nutrition *guidance* based on official guidelines. Flag medical red-flags (severe wasting, high fever, prolonged vomiting) to ANM/health centre. Never diagnose.

---

## 2. Mission Vatsalya (Child Protection)
**Full Name:** Mission Vatsalya — Child Protection and Child Welfare  
**Ministry:** MoWCD  
**Focus:** Safe and secure childhood for every child in India

### Key Components
- **Child Care Institutions (CCIs):** homes for children in need of care & protection
- **Specialized Adoption Agencies (SAAs):** legal adoption facilitation via CARA
- **Foster Care:** alternative family-based care
- **Sponsorship Programme:** financial support for families keeping children
- **Open Shelters:** for street/working children
- **Child Protection Committees:** village, block, district level
- **CHILDLINE 1098:** 24×7 free helpline for children in distress
- **DCPU / CWC / JJB:** district & judicial bodies for child welfare

### AI Agent Scope (Vatsalya Agent)
- How to report a child in need of care and protection
- Adoption process steps via CARA (carings.nic.in)
- Foster care and sponsorship eligibility
- Missing child support — TRACKCHILD / KHOYA PAYA portal
- Nearest DCPU / CWC / open shelter (by geo)
- CHILDLINE 1098 information

### Safety Rule — CRITICAL
**Immediately surface CHILDLINE 1098 + 112 + nearest authority** on ANY indication of:
- Abuse, exploitation, trafficking, bonded labour
- Child in immediate danger
- Runaway or missing child report

**NEVER:** collect abuse testimony, counsel on trauma, or take autonomous action. Always `escalation=true`.

---

## 3. Mission Shakti (Women Safety & Empowerment)
**Full Name:** Mission Shakti — Integrated Women Empowerment Programme  
**Ministry:** MoWCD  
**Focus:** Safety, security, and empowerment of women

### Sub-components
#### SAMBAL (Safety & Security)
- **One Stop Centres (OSC) / Sakhi:** integrated support for violence survivors (medical, legal, police, shelter, counselling) — 733+ OSCs nationally
- **Women Helpline 181:** 24×7 emergency helpline, links to OSC
- **Beti Bachao Beti Padhao (BBBP):** girl child welfare & education
- **Nari Adalat:** community-level alternative dispute resolution

#### SAMARTHYA (Empowerment)
- **PMMVY (Pradhan Mantri Matru Vandana Yojana):** maternity benefit — ₹5,000 (1st child) in instalments for wage-compensated pregnancies
- **PM Ujjwala Yojana:** LPG connection linkage
- **Mahila Shakti Kendra:** rural women empowerment hubs
- **Sakhi Niwas:** working women hostels
- **Beti Bachao:** awareness for son-preference districts

### AI Agent Scope (Shakti Agent)
- Mission Shakti scheme eligibility & benefit amounts
- PMMVY application process, instalment schedule, eligibility (BPL, NFSA, SC/ST)
- Nearest One Stop Centre / Sakhi Centre (by geo)
- 181 helpline — when to call, what to expect
- Legal rights awareness (POSH Act, Domestic Violence Act, Dowry Prohibition)
- Nari Adalat process
- Sakhi Niwas eligibility
- BBBP scheme information

### Safety Rule — CRITICAL
**Immediately surface 181 + 112 + nearest OSC** on ANY indication of:
- Domestic violence, sexual harassment, stalking, trafficking
- Woman in immediate danger
- Emergency situation

**NEVER:** counsel on trauma, advise legal strategy, or delay surfacing helpline. Always `escalation=true`.

---

## Key Helplines Reference (Static, Must Always Be Correct)
| Helpline | Number | For |
|---|---|---|
| Women Helpline | 181 | Violence, distress, empowerment |
| CHILDLINE | 1098 | Children in distress |
| Emergency | 112 | Immediate danger, police |
| NALSA (Legal Aid) | 15100 | Free legal services |
| iCall (Mental Health) | 9152987821 | Psychological support |

## Key Portals Reference
| Portal | URL | For |
|---|---|---|
| CARA (Adoption) | cara.wcd.nic.in | Child adoption |
| TRACKCHILD | trackthemissingchild.gov.in | Missing children |
| Poshan Tracker | poshantracker.in | Nutrition monitoring |
| PMMVY | pmmvy.wcd.gov.in | Maternity benefit |
| Mission Shakti | missionshakti.wcd.gov.in | Women empowerment |

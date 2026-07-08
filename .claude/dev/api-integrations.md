# API Integrations — AI Saheli

## 1. Bhashini / VoicERA (Language Layer)

### Registration
- Developer portal: bhashini.gov.in (register for API key)
- Free for PoC/non-commercial
- API key + User ID required

### ULCA Pipeline — Two-Step Flow

**Step 1: Get Pipeline Config**
```http
POST https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline
Content-Type: application/json
userID: {BHASHINI_USER_ID}
ulcaApiKey: {BHASHINI_API_KEY}

{
  "pipelineTasks": [
    {"taskType": "asr", "config": {"language": {"sourceLanguage": "hi"}}},
    {"taskType": "translation", "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "en"}}}
  ],
  "pipelineRequestConfig": {"pipelineId": "64392f96daac500b55c543cd"}
}
```

**Step 2: Run Inference**
```http
POST {callbackUrl from Step 1}
Authorization: {inferenceApiKey from Step 1}

{
  "pipelineTasks": [{
    "taskType": "asr",
    "config": {"language": {"sourceLanguage": "hi"}, "serviceId": "{serviceId}"},
    "audio": [{"audioContent": "{base64_wav}"}]
  }],
  "inputData": {"audio": [{"audioContent": "{base64_wav}"}]}
}
```

### Supported Languages (Key Ones)
| Code | Language | ASR | NMT | TTS |
|---|---|---|---|---|
| hi | Hindi | ✅ | ✅ | ✅ |
| ta | Tamil | ✅ | ✅ | ✅ |
| te | Telugu | ✅ | ✅ | ✅ |
| bn | Bengali | ✅ | ✅ | ✅ |
| mr | Marathi | ✅ | ✅ | ✅ |
| gu | Gujarati | ✅ | ✅ | ✅ |
| kn | Kannada | ✅ | ✅ | ✅ |
| ml | Malayalam | ✅ | ✅ | ✅ |

### VoicERA (2026 — Evaluate)
MeitY's new open-source end-to-end voice AI stack deployed on Bhashini infrastructure. Announced at India AI Impact Summit 2026. May offer lower latency and on-premise deployment option. Evaluate as upgrade to Bhashini ULCA.

---

## 2. WhatsApp Cloud API (Meta)

### Setup
1. Meta Developer account → Create App → WhatsApp product
2. Phone number → Verify → Get `Phone Number ID` + `Access Token`
3. Webhook setup: register `https://your-domain/whatsapp-webhook` with verify token

### Inbound Message Webhook
```http
POST /whatsapp-webhook
# WhatsApp sends this payload:
{
  "object": "whatsapp_business_account",
  "entry": [{
    "changes": [{
      "value": {
        "messages": [{
          "from": "919XXXXXXXXX",
          "type": "text|audio|image",
          "text": {"body": "..."},
          "audio": {"id": "...", "mime_type": "audio/ogg"}
        }]
      }
    }]
  }]
}
```

### Sending Reply
```http
POST https://graph.facebook.com/v19.0/{phone_number_id}/messages
Authorization: Bearer {access_token}
{
  "messaging_product": "whatsapp",
  "to": "919XXXXXXXXX",
  "type": "text",
  "text": {"body": "response text"}
}

# For audio reply:
{
  "messaging_product": "whatsapp",
  "to": "...",
  "type": "audio",
  "audio": {"link": "https://...audio.ogg"}  // or upload media first
}
```

### Important Notes
- WhatsApp has a **20-second reply timeout** — backend must respond within this window
- Voice notes come as OGG/Opus — must transcode to WAV for Bhashini
- Use `pydub` for transcoding: `ogg → wav` conversion
- Download voice note: `GET https://graph.facebook.com/v19.0/{media_id}` then stream to convert

---

## 3. Anthropic Claude API

```python
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Tool-calling (agent)
response = client.messages.create(
    model="claude-sonnet-4-6",  # current model
    max_tokens=1024,
    tools=[...],  # MCP tool definitions
    messages=[{"role": "user", "content": "..."}]
)

# Streaming
with client.messages.stream(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    messages=[...]
) as stream:
    for text in stream.text_stream:
        yield text
```

Model to use: **`claude-sonnet-4-6`** (current Sonnet, best balance of speed + capability for demo)

---

## 4. Geo Locator

### Option A — Google Places API (Demo with mock)
For the demo, use a **curated mock dataset** of Anganwadi Centres, OSCs, DCPUs by district.  
Avoids API cost and latency variability in a demo setting.

Mock dataset structure:
```json
[
  {
    "type": "AWC",
    "name": "Anganwadi Centre No. 45",
    "district": "Varanasi",
    "state": "UP",
    "lat": 25.3176,
    "lng": 82.9739,
    "address": "Near Shiv Mandir, Sigra",
    "phone": "0542-XXXXXXX"
  }
]
```

### Option B — Live API (Production)
- Google Maps Places API (Nearby Search)
- Or: use MWCD's own ICDS CAS / Poshan Tracker APIs for official AWC locations

---

## 5. Qdrant (Vector DB)

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

client = QdrantClient(url=os.environ["QDRANT_URL"])

# Create collection per scheme
client.create_collection(
    collection_name="poshan",
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
)

# Upsert chunk
client.upsert(collection_name="poshan", points=[
    PointStruct(id=chunk.id, vector=embedding, payload={
        "text": chunk.text,
        "source_url": chunk.source_url,
        "section": chunk.section
    })
])

# Search
results = client.search(
    collection_name="poshan",
    query_vector=query_embedding,
    limit=5,
    with_payload=True
)
```

---

## 6. Key Official Data Sources for RAG Ingestion

| Scheme | Source Documents | URL |
|---|---|---|
| Poshan 2.0 | Operational Guidelines, Poshan Tracker docs | poshantracker.in, wcd.nic.in |
| Mission Vatsalya | Guidelines for Mission Vatsalya 2021 | wcd.nic.in/act/mission-vatsalya |
| Mission Shakti | Scheme guidelines, PMMVY operational guidelines | wcd.nic.in/act/mission-shakti |
| PMMVY | PMMVY operational guidelines, benefit structure | pmmvy.wcd.gov.in |
| CARA (Adoption) | Adoption Regulations 2022 | cara.wcd.nic.in |
| OSC / Sakhi | One Stop Centre scheme guidelines | oscscheme.wcd.gov.in |

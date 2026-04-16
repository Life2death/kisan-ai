---Maharashtra Kisan AI — Claude Code Handoff Document
What This Is
This document summarizes the full planning and architecture conversation between Vikram (project owner) and Claude (architecture advisor). Use this to understand the project context, decisions made, and what needs to be built. This document should be placed in the root of the kisan-ai repo so Claude Code has full context.

1. Project Overview
Maharashtra Kisan AI is a WhatsApp chatbot that helps smallholder farmers in Maharashtra get real-time mandi (market) prices, MSP alerts, and daily price broadcasts — all via WhatsApp in Marathi and English.

Target users: Smallholder farmers in Marathwada/Vidarbha belt (soyabean, tur, cotton)
Target districts (Phase 1): Latur, Nanded, Jalna, Akola, Yavatmal
Target crops (Phase 1): Soyabean, Tur (pigeon pea), Cotton
Languages: Marathi + English (text only in Phase 1)
Revenue model: B2B2C via FPOs (Farmer Producer Organizations) — ₹5,000–15,000/month per FPO for white-labeled bot serving their 200–500 farmer members

2. What the Bot Does (Phase 1 Scope)
Core Features

Farmer onboarding — new user sends "Hi" → bot asks name, district, crops, preferred language → stored in Postgres
Price queries — farmer sends crop name or "भाव" → bot returns today's mandi price, MSP, 7-day trend, best nearby mandi
Daily broadcasts — 6:30 AM IST automated price alerts to opted-in farmers via WhatsApp template messages
DPDPA compliance — explicit consent capture, right-to-erasure ("STOP"/"DELETE MY DATA"), audit logs
Subscription management — free tier (5 queries/day), paid tier (₹49/month, unlimited). Payments stubbed in Phase 1, schema must support it.
Admin dashboard — minimal FastAPI + HTMX page showing DAU, messages sent, top crops, subscription funnel

Explicitly Out of Scope (Phase 1)

Voice notes / speech-to-text
Crop photo diagnosis / image recognition
Weather alerts
Buyer matching / marketplace
Loan advisory
SMS fallback

3. Architecture Decisions (Locked In)
Stack
ComponentChoiceWhyLanguagePython 3.11+Best ecosystem for agri-data (pandas, geopy), FastAPI maturityWeb frameworkFastAPIAsync-native, matches pywa's async supportDatabasePostgres 16ACID for farmer data, DPDPA compliance needsCache/sessionRedis 7Session state for onboarding flow, price cache, rate limitingTask queueCelery + Celery BeatDaily broadcasts, price ingestion jobsWhatsAppMeta WhatsApp Cloud API (official)Only legal option for commercial use. NOT Baileys/whatsapp-web.js (those use personal accounts, violate Meta ToS, get numbers banned)WhatsApp Python libpywa (by david-lev)Production-stable, async, FastAPI-native, templates, webhook verification. Repo: https://github.com/david-lev/pywaLLM (intent fallback)Gemini Flash or Grok 4 FastFor ambiguous messages only. 70% deterministic routing, 30% LLM fallback. Cost target: <₹0.05 per messageMarathi NLUBhashini (govt India free API)For transliteration and translation. Phase 2 for voiceHostingHetzner Mumbai CPX21₹700/month, 3GB RAM, 2 vCPU. Data residency in India (DPDPA)DeploymentDocker ComposeSingle-machine deployment for MVPMigrationsAlembicSchema versioningTestspytestUnit + integration tests
WhatsApp Infrastructure Path

Now: Meta Cloud API sandbox (5 free test numbers, instant setup)
Week 3+: Meta Business verification (needs registered business entity — LLP or Pvt Ltd)
Week 6+: Go live on verified WABA with display name "Maharashtra Kisan AI"
Budget: ~₹3,000–5,000/month for first 500 active farmers (service conversations mostly free, template messages paid)

Key Design Principles

Deterministic routing first, LLM fallback second — don't send every message to a big model. Regex/keyword matching handles 70%+ of messages. LLM is fallback only.
Adapter pattern — business logic never imports from pywa directly. A thin adapter layer (src/adapters/whatsapp.py) wraps pywa. This lets us swap implementations later.
Template responses, not LLM-generated Marathi — use pre-written Marathi templates with variable slots. Don't let the LLM freestyle Marathi.
Cache aggressively — Agmarknet data is daily; cache prices in Redis with 6-hour TTL, invalidated by ingestion job.
Fail gracefully — when data is stale or missing, tell the farmer honestly: "आज लातूर मंडीचा भाव उपलब्ध नाही" (Today's Latur mandi price is not available).

4. Project Structure
kisan-ai/
├── AGENTS.md # OpenClaw instructions (ignore for Claude Code)
├── DECISIONS.md # Architecture decision log
├── CLAUDE-CODE-HANDOFF.md # This file
├── .env.example # Required environment variables
├── .gitignore
├── docker-compose.yml # Postgres + Redis + app
├── Dockerfile
├── requirements.txt # Pinned Python dependencies
├── alembic.ini # Alembic config
├── alembic/ # Migration scripts
│ └── versions/
├── docs/
│ └── meta-setup.md # Meta Business API setup notes
├── vendor-research/
│ └── 01-whatsapp-wrapper.md # pywa evaluation
├── src/
│ ├── __init__.py
│ ├── main.py # FastAPI app entry point
│ ├── config.py # Settings from .env (pydantic-settings)
│ ├── adapters/
│ │ ├── __init__.py
│ │ ├── whatsapp.py # Thin wrapper around pywa
│ │ ├── agmarknet.py # Price data ingestion adapter
│ │ └── llm.py # Gemini/Grok intent fallback
│ ├── models/
│ │ ├── __init__.py
│ │ ├── farmer.py # Farmer, CropsOfInterest, Subscription
│ │ ├── price.py # MandiPrice
│ │ ├── conversation.py # ConversationLog
│ │ ├── broadcast.py # BroadcastLog
│ │ └── consent.py # ConsentEvent
│ ├── handlers/
│ │ ├── __init__.py
│ │ ├── onboarding.py # State machine: new → consent → name → district → crops → language → active
│ │ ├── price.py # Price query handler
│ │ ├── subscription.py # Plan tier checks, upgrade stub
│ │ └── help.py # Fallback, menu, STOP/DELETE
│ ├── router/
│ │ ├── __init__.py
│ │ └── intent.py # Regex-first, LLM-fallback intent classifier
│ ├── templates/
│ │ ├── __init__.py
│ │ ├── marathi.py # Marathi response templates
│ │ └── english.py # English response templates
│ ├── scheduler/
│ │ ├── __init__.py
│ │ ├── celery_app.py # Celery config
│ │ ├── broadcast.py # Daily 6:30 AM price broadcast task
│ │ └── ingestion.py # Daily Agmarknet price pull task
│ ├── admin/
│ │ ├── __init__.py
│ │ └── dashboard.py # FastAPI + HTMX admin views
│ └── tests/
│ ├── __init__.py
│ ├── conftest.py # Shared fixtures
│ ├── test_whatsapp.py # Adapter tests
│ ├── test_onboarding.py # Onboarding state machine tests
│ ├── test_price.py # Price handler tests
│ ├── test_intent.py # Intent classifier tests
│ └── test_ingestion.py # Agmarknet ingestion tests
5. Database Schema
Table: farmers
sqlCREATE TABLE farmers (
 id SERIAL PRIMARY KEY,
 phone VARCHAR(20) UNIQUE NOT NULL, -- E.164 format
 name VARCHAR(100),
 district VARCHAR(50),
 preferred_language VARCHAR(10) DEFAULT 'mr', -- 'mr' or 'en'
 plan_tier VARCHAR(20) DEFAULT 'free', -- 'free' or 'paid'
 subscription_status VARCHAR(20) DEFAULT 'none', -- 'none', 'active', 'expired'
 onboarding_state VARCHAR(30) DEFAULT 'new', -- state machine state
 queries_today INTEGER DEFAULT 0,
 queries_reset_at TIMESTAMP WITH TIME ZONE,
 consent_given_at TIMESTAMP WITH TIME ZONE,
 consent_version VARCHAR(10),
 created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
 updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
 deleted_at TIMESTAMP WITH TIME ZONE -- soft delete for DPDPA
);
CREATE INDEX idx_farmers_phone ON farmers(phone);
CREATE INDEX idx_farmers_district ON farmers(district);
Table: crops_of_interest
sqlCREATE TABLE crops_of_interest (
 id SERIAL PRIMARY KEY,
 farmer_id INTEGER REFERENCES farmers(id) ON DELETE CASCADE,
 crop VARCHAR(50) NOT NULL, -- 'soyabean', 'tur', 'cotton'
 added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_crops_farmer ON crops_of_interest(farmer_id);
Table: mandi_prices
sqlCREATE TABLE mandi_prices (
 id SERIAL PRIMARY KEY,
 date DATE NOT NULL,
 crop VARCHAR(50) NOT NULL,
 mandi VARCHAR(100) NOT NULL,
 district VARCHAR(50) NOT NULL,
 modal_price DECIMAL(10,2), -- most common trading price
 min_price DECIMAL(10,2),
 max_price DECIMAL(10,2),
 msp DECIMAL(10,2), -- minimum support price (may be null)
 source VARCHAR(50) DEFAULT 'agmarknet', -- data provenance
 fetched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
 is_stale BOOLEAN DEFAULT FALSE
);
CREATE INDEX idx_prices_lookup ON mandi_prices(crop, district, date);
CREATE INDEX idx_prices_date ON mandi_prices(date);
Table: conversations
sqlCREATE TABLE conversations (
 id SERIAL PRIMARY KEY,
 farmer_id INTEGER REFERENCES farmers(id),
 phone VARCHAR(20) NOT NULL,
 direction VARCHAR(10) NOT NULL, -- 'inbound' or 'outbound'
 message_type VARCHAR(20) NOT NULL, -- 'text', 'template', 'interactive'
 raw_message TEXT,
 detected_intent VARCHAR(50),
 detected_entities JSONB,
 response_sent TEXT,
 created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_conv_farmer ON conversations(farmer_id);
CREATE INDEX idx_conv_created ON conversations(created_at);
Table: broadcast_log
sqlCREATE TABLE broadcast_log (
 id SERIAL PRIMARY KEY,
 farmer_id INTEGER REFERENCES farmers(id),
 template_id VARCHAR(100) NOT NULL,
 status VARCHAR(20) DEFAULT 'pending', -- 'pending', 'sent', 'delivered', 'failed'
 cost_paise INTEGER DEFAULT 0,
 error_message TEXT,
 sent_at TIMESTAMP WITH TIME ZONE,
 created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_broadcast_farmer ON broadcast_log(farmer_id);
CREATE INDEX idx_broadcast_status ON broadcast_log(status);
Table: consent_events
sqlCREATE TABLE consent_events (
 id SERIAL PRIMARY KEY,
 farmer_id INTEGER REFERENCES farmers(id),
 event_type VARCHAR(20) NOT NULL, -- 'opt_in', 'opt_out', 'erasure_request', 'erasure_complete'
 consent_version VARCHAR(10),
 message_id VARCHAR(100), -- WhatsApp message ID for audit trail
 ip_address VARCHAR(50), -- if available
 created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX idx_consent_farmer ON consent_events(farmer_id);
Redis Key Schema
session:{phone} → JSON onboarding state TTL: 24h
price:{crop}:{district}:{date} → JSON price data TTL: 6h (invalidated by ingestion)
rate:{phone}:{date} → integer query count TTL: 24h
broadcast:lock → mutex for broadcast job TTL: 30min
6. Onboarding State Machine
new → awaiting_consent → awaiting_name → awaiting_district → awaiting_crops → awaiting_language → active
 ↓
Any state: "STOP" → opted_out
Any state: "DELETE" → erasure_requested → (data deleted) → erased
States live in Redis during onboarding (TTL 24h). On completion ("active"), the full profile is written to Postgres and the Redis key is deleted. If a user abandons onboarding (TTL expires), Redis key is cleaned up automatically.
Onboarding Messages
Consent (Marathi):

नमस्कार! महाराष्ट्र किसान AI मध्ये आपले स्वागत आहे. 🌾
आम्ही तुमचा फोन नंबर, नाव, जिल्हा आणि पीक माहिती साठवतो — फक्त बाजारभाव कळवण्यासाठी.
"हो" पाठवा सहमती देण्यासाठी. "नाही" पाठवा नाकारण्यासाठी.
कधीही "STOP" पाठवून सेवा थांबवा.

Consent (English):

Welcome to Maharashtra Kisan AI! 🌾
We store your phone number, name, district, and crop info — only to send you market prices.
Send "YES" to agree. Send "NO" to decline.
Send "STOP" anytime to opt out.

7. Intent Classification Strategy
Regex/Keyword Rules (70%+ of messages)
pythonINTENT_RULES = {
 "price_query": {
 "patterns": [
 r"(price|भाव|दर|rate|bhav|dar)",
 r"(soyabean|सोयाबीन|soybean|tur|तूर|toor|cotton|कापूस|kapus|kapas)",
 ],
 "entities": {
 "crop": {"सोयाबीन|soyabean|soybean": "soyabean", "तूर|tur|toor": "tur", "कापूस|cotton|kapus|kapas": "cotton"},
 "district": {"लातूर|latur": "latur", "नांदेड|nanded": "nanded", ...}
 }
 },
 "greeting": [r"^(hi|hello|नमस्कार|namaskar)$"],
 "help": [r"^(help|मदत|menu)$"],
 "stop": [r"^(stop|थांबा|बंद)$"],
 "delete": [r"^(delete|माझा डेटा हटवा)"],
 "subscribe": [r"(upgrade|subscribe|paid|premium)"],
}
LLM Fallback
When regex doesn't match, send to Gemini Flash / Grok 4 Fast with a structured prompt:
You are an intent classifier for a Marathi/English farming chatbot.
Classify this message into one of: price_query, greeting, help, stop, delete, subscribe, unknown.
Also extract entities: crop (soyabean/tur/cotton) and district (latur/nanded/jalna/akola/yavatmal).
Respond ONLY with JSON: {"intent": "...", "crop": "...", "district": "..."}
Message: "{user_message}"
Transliteration handling
Farmers often type Marathi in Latin script. Common mappings:

भाव → bhav, bhaav
कापूस → kapus, kapas, kaapus
सोयाबीन → soyabean, soybean, soybin
तूर → tur, toor, tuur
लातूर → latur, laatuur

Build these into the regex patterns, not as a separate transliteration step.
8. Data Ingestion — Agmarknet
Sources (in priority order)

Agmarknet API (data.gov.in) — primary, but flaky and often 1 day stale
State APMC portal scraping — secondary reconciliation
eNAM — tertiary fallback

Ingestion Schedule

Daily Celery task at 5:00 AM IST (before 6:30 AM broadcast)
Retry 3x with exponential backoff (5min, 15min, 45min)
If all retries fail, mark prices as stale and alert admin

Staleness Rules

Price data older than 36 hours → marked is_stale = true
If stale data is the only data available, serve it with a disclaimer: "हा भाव कालचा आहे" (This price is from yesterday)
If no data at all for a crop/district, respond: "आज भाव उपलब्ध नाही" (Price not available today)

Reconciliation
When multiple sources provide prices for the same crop/district/date:

Prefer Agmarknet (official source)
If Agmarknet is missing, use APMC portal
If both exist and differ by >10%, flag for manual review
Never silently average conflicting prices

9. DPDPA Compliance
Data Stored
DataPurposeRetentionPhone numberIdentify user, send messagesUntil opt-out + 30 daysNamePersonalize responsesUntil opt-out + 30 daysDistrictLocalize price dataUntil opt-out + 30 daysCrops of interestFilter broadcastsUntil opt-out + 30 daysLanguage preferenceResponse languageUntil opt-out + 30 daysConversation logsDebug, analytics90 days rollingConsent eventsAudit trail7 years (legal requirement)
Data NOT Stored

Exact GPS location (district-level only)
Aadhaar or ID numbers
Financial data (no payments in Phase 1)
Message content after intent extraction (raw message stored temporarily for debug, purged at 90 days)

Erasure Flow

Farmer sends "STOP" or "DELETE MY DATA"
Bot confirms: "Are you sure? Send DELETE CONFIRM"
On confirmation:

Soft-delete farmer record (set deleted_at)
Delete from crops_of_interest
Remove from broadcast lists
Log erasure event in consent_events
Send confirmation message


Hard delete after 30 days (Celery periodic task)
Consent events are NEVER deleted (legal audit trail)

10. Environment Variables (.env.example)
env# WhatsApp Cloud API
WHATSAPP_PHONE_ID=your_phone_id
WHATSAPP_TOKEN=your_access_token
WHATSAPP_APP_SECRET=your_app_secret
WHATSAPP_VERIFY_TOKEN=your_webhook_verify_token
WHATSAPP_APP_ID=your_app_id

# Database
DATABASE_URL=postgresql://kisan:password@localhost:5432/kisanai
REDIS_URL=redis://localhost:6379/0

# LLM (intent fallback)
GEMINI_API_KEY=your_gemini_key
# or
XAI_API_KEY=your_xai_key

# App
APP_ENV=development
APP_PORT=8000
LOG_LEVEL=INFO
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme

# Agmarknet
AGMARKNET_API_KEY=your_data_gov_in_key
11. Implementation Order
Build in this sequence — each module unblocks the next:
#ModuleDescriptionKey filesDependencies1WhatsApp adapterThin wrapper around pywa for send/receive/webhooksrc/adapters/whatsapp.pypywa2FastAPI webhookReceives Meta webhooks, signature verificationsrc/main.pyModule 13Docker ComposePostgres + Redis running locallydocker-compose.yml, DockerfileNone4Database models + migrationsSQLAlchemy models, Alembic migrationssrc/models/, alembic/Module 35Agmarknet ingestionDaily price scraper with retry/stalenesssrc/adapters/agmarknet.py, src/scheduler/ingestion.pyModule 46Intent classifierRegex + LLM hybridsrc/router/intent.pyNone7Onboarding handlerState machine with Redis sessionssrc/handlers/onboarding.pyModules 1, 48Price handlerQuery handler with cachesrc/handlers/price.pyModules 4, 5, 69Celery broadcast schedulerDaily 6:30 AM broadcastssrc/scheduler/broadcast.pyModules 1, 4, 510Marathi templatesResponse templates with slot fillingsrc/templates/None11Admin dashboardMinimal HTMX dashboardsrc/admin/dashboard.pyModule 412DPDPA consent + auditConsent flow, erasure, audit logssrc/handlers/help.py, src/models/consent.pyModules 4, 7
12. What Claude Code Should Do First
Immediate tasks (generate skeleton code):

requirements.txt with pinned versions: pywa, fastapi, uvicorn, sqlalchemy, alembic, asyncpg, redis, celery, pydantic-settings, httpx, pytest, pytest-asyncio
docker-compose.yml with Postgres 16 + Redis 7 + app service
Dockerfile for the FastAPI app
src/config.py using pydantic-settings to load from .env
src/main.py with FastAPI app, health check endpoint, and pywa webhook integration
src/adapters/whatsapp.py thin adapter wrapping pywa
SQLAlchemy models for all 6 tables
Alembic initial migration
src/router/intent.py with the regex rules from section 7
src/handlers/onboarding.py state machine

Quality expectations:

Type hints on all functions
Docstrings on public functions
One test file per module
No hardcoded values — everything from config
Async everywhere (FastAPI + pywa both support it)
Proper error handling — never crash on bad user input

13. What NOT to Do

Do NOT use Baileys, whatsapp-web.js, yowsup, or any personal-account WhatsApp library
Do NOT let the LLM generate Marathi responses freestyle — use templates
Do NOT store credentials in code or config files committed to git
Do NOT build payments/billing in Phase 1 — just the schema and stubs
Do NOT build voice/image/weather features — Phase 1 is text + prices only
Do NOT over-engineer. Single-machine Docker Compose is fine. No Kubernetes, no microservices, no event sourcing.

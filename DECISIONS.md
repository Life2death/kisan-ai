# Architecture Decisions Log

Append-only log of module choices. Newest entries at the top.

Format:
- **YYYY-MM-DD — Module N: <name>**
 - Chose: `<library>` v<version>
 - Runner-up: `<library>`
 - Why: <one-line reason>
 - Trade-off accepted: <one line>
 - Evaluation: `vendor-research/NN-<name>.md`

---

- **2026-04-18 — Phase 2 Module 3: Image-based Pest & Disease Diagnosis**
  - Chose: Hybrid approach — Local TensorFlow model (primary) + Gemini Vision API (fallback)
  - Runner-up: Gemini Vision only; PyTorch-based model
  - Why: TensorFlow provides fast local inference (~500ms, offline-capable, free) for top 20 Maharashtra crop pests; Gemini Vision handles edge cases/unknown diseases; hybrid pattern proven by Phase 2 Module 2 (voice STT)
  - Trade-off accepted: Model file management (100MB+ not in git, user downloads separately); mitigated by graceful fallback to Gemini-only mode if model missing
  - Implementation:
    - Database: Optional diagnoses table (or extend Conversation.detected_entities) for diagnosis history + district pest analytics
    - ImageDiagnoser: Async class with TensorFlow + Gemini Vision pathways, 30s TensorFlow timeout, 60s Gemini timeout
    - Image preprocessing: PIL Image → RGB → resize (224x224) → normalize (0-1)
    - Severity determination: confidence > 0.9 → severe; > 0.7 → moderate; else → mild
    - DiagnosisResult dataclass: pest, disease_marathi, confidence, severity, treatment (optional), source ("tensorflow" or "gemini")
    - DiagnosisHandler: Orchestrates diagnosis workflow, stores results, formats replies (Marathi/English)
    - DiagnosisRepository: Farmer diagnosis history, district-level pest statistics (future analytics)
    - Formatters: format_diagnosis_reply() (high-conf), format_diagnosis_low_confidence() (<50%), format_diagnosis_failed()
    - Webhook: Extended IncomingMessage.is_image(), updated handle_message() to detect images, route to PEST_QUERY intent
    - Main webhook endpoint: get_media_url() for images (same as voice), route PEST_QUERY → DiagnosisHandler
  - Testing: 25+ tests covering image download, TensorFlow inference, Gemini fallback, handler integration, formatting, webhook routing, edge cases
  - Evaluation: Extensible architecture (easy to swap TensorFlow for PyTorch, add new models); production-ready error handling; reusable media pattern from Phase 2 Module 2

- **2026-04-18 — Phase 2 Module 2: Voice Message Support**
  - Chose: Google Cloud Speech-to-Text (primary) + Whisper (fallback) with "Transcribe → Re-classify" design
  - Runner-up: Audio-native LLM classifier (Gemini Pro); Whisper-only
  - Why: Google Cloud provides 95% accuracy for Marathi (mr-IN), free tier 60 min/month; transcribe-to-text reuses 100% of existing regex+Gemini classifier (no new Intent enum); Whisper fallback ensures graceful degradation if quota exhausted
  - Trade-off accepted: Two STT services vs one (higher maintenance). Mitigated by: (1) transparent error handling (fallback messages to farmers), (2) isolated failures (one service down doesn't block bot), (3) cost-effective (~₹0.04 per 15s Google Cloud, ~₹0.001 per 50s Whisper)
  - Implementation:
    - Database: conversations.media_url (24h audit trail), conversations.voice_transcription (transcribed Marathi text)
    - VoiceTranscriber: Async class with Google Cloud primary (language_code=mr-IN), Whisper fallback, 30s timeout
    - Webhook: IncomingMessage extended with media_id/media_url/mime_type; parse_webhook_message extracts audio metadata; handle_message transcribes → passes to existing classify()
    - WhatsApp adapter: get_media_url(media_id) calls Meta's /media endpoint (24h expiry)
    - Formatters: format_transcription_failed(), format_transcription_empty() in Marathi/English
    - Scheduling: No new scheduler needed (transcription happens in-request during webhook handling)
  - Evaluation: No new Intent enum (voice → same intents as text); extensible (future image diagnosis uses same media_url pattern); production-ready error handling; 40+ comprehensive tests

- **2026-04-17 — Phase 2 Module 1: Weather Integration**
  - Chose: Multi-source ingestion (IMD primary, OpenWeather fallback) + async orchestrator pattern
  - Runner-up: Single OpenWeather API; local weather service
  - Why: IMD is India's official meteorological source (free, authoritative, state-level accuracy); OpenWeather provides reliable real-time fallback; multi-source pattern mirrors successful price pipeline for consistency and resilience
  - Trade-off accepted: 2 APIs to maintain vs 1 (higher maintenance). Mitigated by: (1) isolated source failures (one API down doesn't block ingestion if other healthy), (2) preference rules (IMD > OpenWeather) ensure deterministic winner selection
  - Implementation:
    - Database: weather_observations table stores: date, apmc, metric (temperature/rainfall/humidity/wind/pressure), value, unit, min/max, forecast_days_ahead, condition, advisory, source, raw_payload (JSONB), is_stale
    - Sources: IMD API (grid data endpoint, free, 1-2s latency) + OpenWeather (free tier: 60 calls/min, real-time)
    - Pipeline: Async fetch from all sources → normalize field names → deduplicate per (date, apmc, metric, forecast_days_ahead) → upsert to PostgreSQL with ON CONFLICT
    - Query layer: Repository with Redis cache (6h TTL) + forecast lookup; formatter for Marathi/English replies
    - Intent: New WEATHER_QUERY intent; regex patterns for English/Marathi/Hinglish ("weather", "हवामान", "पाऊस", "forecast", "temperature", etc.); metric extraction (temperature, rainfall, humidity, wind_speed)
    - Scheduler: Daily ingestion at 6:00 AM IST (30 min before price broadcast), Celery task with 3x retry
  - Evaluation: Extensible architecture (new sources only require WeatherSource.fetch()); graceful degradation; production patterns from price ingestion

- **2026-04-17 — Module 11: DPDPA Consent Flow + Right-to-Erasure**
  - Chose: Explicit opt-in via "हो" + 30-day erasure window + immutable ConsentEvent audit trail
  - Runner-up: Implicit consent on first message; immediate hard-delete on STOP
  - Why: DPDPA v2023 compliance requires explicit consent + right to be forgotten with notice period. 30-day window allows farmer reconsideration; audit trail (ConsentEvent) never deleted for regulatory compliance
  - Trade-off accepted: Extra DB table (ConsentEvent) + soft-delete pattern (deleted_at) vs immediate deletion. Mitigated by indexed queries that filter soft-deleted records efficiently
  - Implementation: 
    - Database: farmers.erasure_requested_at (timestamp), broadcast_log.deleted_at, conversation.deleted_at (soft-delete support)
    - Handler: _log_consent_event() logs opt_in/opt_out/erasure_request events; _transition_delete_confirm() sets erasure_requested_at + soft-deletes broadcasts
    - Scheduler: hard_delete_erased_farmers() Celery task runs daily at 1:00 AM IST, hard-deletes farmers > 30 days old, logs erasure_complete before deletion
    - Privacy: Farmers in erasure window excluded from daily broadcasts + DAU calculations
  - Evaluation: Compliance with DPDPA v2023 + State Bank of India privacy precedent

- **2026-04-17 — Scope Change: Target Districts + Commodities**
  - Changed districts from Latur/Nanded/Jalna/Akola/Washim → **Pune, Ahilyanagar, Navi Mumbai, Mumbai, Nashik**
  - Changed commodities from soyabean/tur/cotton only → **ALL commodities** (no filter at ingestion, filter at query time)
  - Why: Western Maharashtra + Nashik onion belt is the higher-volume market; all-commodity strategy future-proofs queries
  - Trade-off accepted: Slightly more storage (~180 MB/year); eliminates re-ingestion cost when new commodities needed

- **2026-04-17 — Module 5: Intent Classifier**
  - Chose: Regex-first + Gemini 1.5 Flash fallback
  - Runner-up: LLM-only classification
  - Why: ~85% of farmer messages matched by compiled regex at ~0ms, free, deterministic. LLM only for UNKNOWN (~500ms, ~₹0.001/call)
  - Trade-off accepted: Regex patterns need maintenance as new message styles emerge; mitigated by LLM fallback
  - Implementation: `src/classifier/` — `intents.py`, `regex_classifier.py`, `llm_classifier.py`, `classify.py`
  - Marathi: Full Devanagari patterns in every intent (पाठवा=subscribe, कांदा=onion, तूर=tur, हो=yes standalone, etc.)

- **2026-04-17 — Module 4: Mandi Price Ingestion (4-source pipeline)**
  - Chose: data.gov.in Agmarknet API (backbone) + MSAMB scraper + NHRDF onion + Vashi APMC direct
  - Runner-up: data.gov.in API only
  - Why: No single source has full coverage. Agmarknet misses Vashi ~30% of days. NHRDF is the authoritative onion quote. MSAMB has deepest MH APMC list.
  - Trade-off accepted: 4 scrapers to maintain vs 1 API. Mitigated by isolation (each source fails independently, others continue)
  - Merge preference: nhrdf > msamb > agmarknet > vashi (onion); vashi > msamb > agmarknet (Vashi yard); msamb > agmarknet > vashi > nhrdf (default)
  - API key: data.gov.in free key stored as DATA_GOV_IN_API_KEY / AGMARKNET_API_KEY (both accepted)

- **2026-04-17 — Module 1: WhatsApp Cloud API Wrapper**
 - Chose: `pywa` v4.0.0
 - Runner-up: `heyoo`
 - Why: Production-stable, BSUID-migration ready, async-first, minimal dependencies (httpx only), active maintenance (Feb 2026), FastAPI integration
 - Trade-off accepted: Slightly more complex API than heyoo, but higher reliability for production and future Meta changes
 - Evaluation: `vendor-research/01-whatsapp-wrapper.md`
 - Marathi requirement: Noted. Templates, message text, and captions support UTF-8 Marathi natively. Transliteration module (Module 9) will handle Hinglish↔Marathi conversion
- **2026-04-17 — Module 3: Docker Compose (Postgres 16 + Redis 7)**
 - Chose: Official `postgres:16-alpine` + `redis:7-alpine`
 - Runner-up: Cloud-managed services (AWS RDS/ElastiCache - considered but defer to Module 6)
 - Why: Local development simplicity, same services for prod, Alpine images lightweight, built-in health checks
 - Trade-off accepted: Self-managed vs cloud (manageable for MVP, migrate to AWS later if needed)
 - Evaluation: `vendor-research/02-docker-compose.md`
 - Configuration: Named volumes for persistence, network isolation, environment-based config

# 🚀 How to Start & Test Your Kisan AI WhatsApp Bot

**Phase 1 MVP Complete** — All 11 modules implemented, 216 tests passing, ready for field testing with farmers.

---

## ✅ Prerequisites

- Python 3.10+
- Docker & Docker Compose (for PostgreSQL 16 + Redis 7)
- Meta WhatsApp Business Account (token in `.env`)
- Credentials: `.env` must include `WHATSAPP_BUSINESS_ACCOUNT_ID`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_TOKEN`, `DATA_GOV_IN_API_KEY`

---

## 🔧 Step 1: Install Dependencies

```bash
cd ~/projects/kisan-ai
pip install -r requirements.txt
```

This installs:
- FastAPI, Uvicorn (web framework)
- pywa 4.0.0 (WhatsApp Cloud API)
- SQLAlchemy, asyncpg (database)
- Redis (async cache)
- Celery (task scheduler)
- Pytest, pytest-asyncio (testing)
- Alembic (migrations)

---

## 🐳 Step 2: Start Database Services

```bash
cd ~/projects/kisan-ai
docker-compose up -d
```

Verify:
```bash
docker-compose ps
```

Should show:
- `kisan_ai_postgres` — Up (healthy)
- `kisan_ai_redis` — Up (healthy)

---

## 🗄️ Step 3: Run Database Migrations

```bash
alembic upgrade head
```

Creates tables: farmers, conversations, broadcast_log, mandi_prices, consent_events, and more.

---

## 🧪 Step 4: Run Test Suite (Verify Installation)

```bash
pytest src/tests/ -v --tb=short
```

Expected: **216 tests passing** (including 20 DPDPA consent tests).

---

## ▶️ Step 5: Start the FastAPI Server

**Terminal 1 — API Server**:
```bash
cd ~/projects/kisan-ai
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
✅ WhatsApp adapter initialized
✅ FastAPI app ready
```

---

## 📮 Step 6: Start Celery Scheduler (Background Tasks)

**Terminal 2 — Celery Scheduler**:
```bash
cd ~/projects/kisan-ai
celery -A src.scheduler.celery_app beat -l info
```

This schedules:
- **6:30 AM IST** — Daily price broadcasts to all active farmers
- **1:00 AM IST** — Hard-delete farmers in 30-day erasure window (DPDPA compliance)

Optionally start Celery worker in another terminal:
```bash
celery -A src.scheduler.celery_app worker -l info
```

---

## 📱 Step 7: Configure Meta Webhook (One-time setup)

1. Go to [Meta Business Console](https://business.facebook.com/)
2. Navigate to: **Kisan Tech** → **WhatsApp** → **Configuration**
3. Click **Edit** next to "Webhook URL"
4. Set:
   - **Webhook URL**: `https://YOUR_DOMAIN:8000/webhook/whatsapp`
   - **Verify Token**: `kisan_webhook_token`
   - **Subscribe to webhook fields**: `messages`, `message_status`
5. Click **Verify and Save**

---

## 💬 Step 8: Test Bot Flow

### Health Check
```bash
curl http://localhost:8000/health
```

### Send Test Message (via WhatsApp)

1. Use your Meta test phone number
2. Send message to your bot's WhatsApp number
3. Bot should respond with:
   - **Marathi greeting** ("नमस्कार!")
   - **Onboarding flow** (ask name → district → crops → consent)
   - **Farmer profile saved** to PostgreSQL

### Example Test Conversation

**Farmer**: नमस्कार  
**Bot**: नमस्कार! आपले नाव काय आहे?

**Farmer**: राज  
**Bot**: राज, आपली जिल्हा कोणती? (उदा: पुणे, अहमदनगर, नाशिक)

**Farmer**: पुणे  
**Bot**: पुणे चांगले! आपण कोण फसली उभा करता? (उदा: कांदा, भाजी, ुटर)

**Farmer**: कांदा  
**Bot**: कांद्यासाठी दररोज दर मिळतील. सहमत? (हो/नाही)

**Farmer**: हो  
**Bot**: खूप छान! आता दररोज 6:30 AM ला किंमत मिळाल.

### Admin Dashboard

View real-time metrics at:
```
http://localhost:8000/admin/dashboard
```

Shows:
- DAU (Daily Active Users)
- Message volume
- Crop preferences
- Broadcast health
- Subscription funnel

---

## ✅ What the Bot Does (Phase 1 Complete)

**Modules 1–11 Implemented**:

- ✅ **Module 1**: WhatsApp Cloud API integration (pywa v4.0.0)
- ✅ **Module 2**: FastAPI webhook + message handler
- ✅ **Module 3**: Docker Compose (PostgreSQL 16 + Redis 7)
- ✅ **Module 4**: 4-source mandi price ingestion (Agmarknet + MSAMB + NHRDF + Vashi APMC)
- ✅ **Module 5**: Intent classifier (Regex-first + Gemini 1.5 Flash fallback)
- ✅ **Module 6**: Onboarding state machine (name → district → crops → consent)
- ✅ **Module 7**: Price handler + formatted WhatsApp replies (Marathi + English + Hinglish)
- ✅ **Module 8**: Daily price broadcast scheduler (Celery Beat, 6:30 AM IST)
- ✅ **Module 9**: Marathi templates + transliteration (Devanagari + Hinglish)
- ✅ **Module 10**: Admin dashboard (real-time metrics: DAU, crops, funnel, broadcasts)
- ✅ **Module 11**: DPDPA consent flow + right-to-erasure (30-day countdown + immutable audit trail)

**Ready for Beta**: Field testing with 100–1,000 farmers in Maharashtra

---

## 🗂️ Key Files

- `.env` — Configuration (credentials, API keys)
- `docker-compose.yml` — PostgreSQL + Redis definitions
- `alembic/versions/` — Database migrations (0001–0003)
- `src/main.py` — FastAPI entry point
- `src/handlers/webhook.py` — WhatsApp message handler
- `src/handlers/onboarding.py` — Farmer onboarding flow
- `src/scheduler/tasks.py` — Celery tasks (broadcast, hard-delete)
- `src/admin/` — Admin dashboard (queries + endpoints)
- `src/tests/` — 216 tests (unit + integration)

---

## 🐛 Troubleshooting

### Bot doesn't respond
- Check FastAPI server logs for errors
- Verify `.env` has correct WHATSAPP_API_TOKEN
- Ensure webhook URL is correct in Meta Business Console

### Database migrations fail
```bash
# Check migration status
alembic current

# View all migrations
alembic history

# Rollback and re-apply
alembic downgrade -1
alembic upgrade head
```

### Tests fail
```bash
# Run with verbose output
pytest src/tests/ -vv --tb=long

# Run specific test
pytest src/tests/test_consent.py::TestConsentFlow::test_consent_opt_in_event_logged -v
```

### Port conflicts
- API default: 8000 (change with `--port`)
- PostgreSQL: 5432
- Redis: 6379

---

## 📚 Next Steps (Phase 2 — June 2026)

- Voice message support (Whisper STT)
- Photo-based pest diagnosis (TensorFlow + Gemini Vision)
- Weather integration (IMD/OpenWeather)
- Government schemes & MSP alerts
- Price alerts ("notify when onion > ₹5000")

---

**Ready for production field testing!** 🚀

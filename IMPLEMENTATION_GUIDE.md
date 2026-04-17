# Kisan AI Implementation Guide

## Overview

Kisan AI is a WhatsApp-based farming bot for Maharashtra farmers, providing real-time market prices, government scheme eligibility, pest diagnosis, and alert subscriptions. Built with Python/FastAPI, PostgreSQL, and Celery.

**Status**: Phase 2 Modules 1-5 complete and production-ready.

---

## Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                    WhatsApp Meta API                         │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────v───────────────────────────────────────────┐
│                 FastAPI Webhook Handler                      │
│  (/webhook/whatsapp) → parse_webhook_message()              │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────v───────────────────────────────────────────┐
│              Intent Classification Layer                      │
│  ├─ Regex Classifier (85% coverage, instant)                │
│  └─ LLM Fallback (Gemini, for edge cases)                   │
└─────────────────┬───────────────────────────────────────────┘
                  │
        ┌─────────v──────────┐
        │ Intent Dispatcher  │
        └─────────┬──────────┘
        
    ┌───┬────┬────┬────┬────┬────┐
    │   │    │    │    │    │    │
    v   v    v    v    v    v    v
   ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐ ┌─┐
   │P│ │P│ │S│ │M│ │W│ │D│ │S│  Handlers
   │Q│ │A│ │Q│ │A│ │Q│ │Q│ │U│
   └─┘ └─┘ └─┘ └─┘ └─┘ └─┘ └─┘
    │   │    │    │    │    │    │
    └───┴────┴────┴────┴────┴────┘
        ┌───────v────────┐
        │  Data Layer    │
        │  PostgreSQL    │
        └────────────────┘
        
    ┌─────────────────┐
    │  Scheduler      │
    │  (Celery Beat)  │
    └────────┬────────┘
    ┌────────v────────┐
    │ Ingestion Tasks │
    │ (2x daily)      │
    └────────┬────────┘
    ┌────────v────────┐
    │ Alert Triggers  │
    │ (2x daily)      │
    └─────────────────┘
```

### Data Flow: Price Query Example

```
Farmer: "कांदा किंमत?"
   ↓
Webhook receives message
   ↓
Parse: type=text, from=+919876543210
   ↓
Classify: PRICE_QUERY, commodity="onion", confidence=1.0
   ↓
Lookup: Farmer(phone) → profile (language=mr, district=pune)
   ↓
Query: MandiPrice.filter(crop=onion, district=pune, date=today)
   ↓
Format: format_price_reply() → Marathi message
   ↓
Send: WhatsApp.send_text_message(phone, reply)
   ↓
Log: Conversation.insert(farmer_id, intent, timestamp)
   ↓
Farmer receives: "🌾 कांदा - पुणे मंडी\n💹 भाव: ₹4,200..."
```

---

## Setup & Deployment

### Prerequisites

- Python 3.9+
- PostgreSQL 13+
- Redis 6+
- WhatsApp Business Account (Meta)

### Installation

```bash
# Clone & install
git clone <repo>
cd kisan-ai
pip install -r requirements.txt

# Setup database
alembic upgrade head

# Run server
uvicorn src.main:app --reload

# Run scheduler
celery -A src.scheduler.celery_app worker --loglevel=info
celery -A src.scheduler.celery_app beat --loglevel=info
```

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost/kisan_ai

# WhatsApp
WHATSAPP_PHONE_ID=<business-phone-id>
WHATSAPP_TOKEN=<business-account-token>
WHATSAPP_BUSINESS_ACCOUNT_ID=<ba-id>
WHATSAPP_VERIFY_TOKEN=<webhook-verify-token>

# APIs
GOOGLE_SPEECH_API_KEY=<google-cloud-key>
OPENAI_API_KEY=<openai-key>
GEMINI_API_KEY=<google-gemini-key>

# Redis
REDIS_URL=redis://localhost:6379/0

# Log Level
LOG_LEVEL=INFO
```

---

## Modules & Features

### Module 1: Price Queries
**Status**: ✅ Complete

Query real-time mandi (market) prices from 4 sources:
- Agmarknet API (Government of India)
- MSIB Scraper
- NHRDF Onion Prices
- Vashi APMC

```python
# In main.py
if intent_type == Intent.PRICE_QUERY:
    price_repo = PriceRepository(session)
    query = PriceQuery(commodity="onion", district="pune")
    result = await price_repo.query(query, farmer_district=farmer.district)
    reply = format_price_reply(result, lang=farmer_language)
```

**Tables**: `mandi_prices`

---

### Module 2: Weather Forecasts
**Status**: ✅ Complete (Phase 2 Module 1)

Fetch weather forecasts for 5 districts:
- IMD (Indian Meteorological Dept)
- OpenWeather

```python
if intent_type == Intent.WEATHER_QUERY:
    handler = WeatherHandler(session)
    reply = await handler.handle(result, farmer_apmc=district, farmer_language=lang)
```

**Tables**: `weather_observations`

---

### Module 3: Pest Diagnosis
**Status**: ✅ Complete (Phase 2 Module 3)

Upload crop image → AI diagnosis:
- TensorFlow model for crop disease detection
- Google Gemini Vision API for detailed analysis

```python
if intent_type == Intent.PEST_QUERY:
    diagnoser = ImageDiagnoser(config)
    handler = DiagnosisHandler(diagnoser)
    reply = await handler.handle(result, media_url=url, farmer_phone=phone, lang=lang)
```

**Tables**: None (stateless)

---

### Module 4: Government Schemes & MSP Alerts
**Status**: ✅ Complete (Phase 2 Module 4)

Query eligible schemes:
- PM-KISAN (₹6,000/year)
- PM-FASAL (Crop insurance)
- Rashtriya Kranti (Soil health)
- State schemes

Set MSP alerts: "Notify me when MSP >= ₹3,000"

```python
if intent_type == Intent.SCHEME_QUERY:
    handler = SchemeHandler(session)
    reply = await handler.handle_scheme_query(
        farmer_age=farmer.age, 
        farmer_land_hectares=float(farmer.land_hectares),
        farmer_crops=crops,
        farmer_district=farmer.district,
        farmer_language=lang
    )

if intent_type == Intent.MSP_ALERT:
    handler = SchemeHandler(session)
    threshold, condition = parse_alert_message(msg.text)
    reply = await handler.handle_msp_alert(
        farmer_id=str(farmer.id),
        commodity=commodity,
        alert_threshold=threshold,
        farmer_language=lang
    )
```

**Tables**: `government_schemes`, `msp_alerts`

---

### Module 5: Mandi Price Alerts
**Status**: ✅ Complete (Phase 2 Module 5)

Set price alerts: "Alert when onion > ₹4,000"

```python
if intent_type == Intent.PRICE_ALERT:
    handler = PriceAlertHandler(session)
    threshold, condition = parse_alert_message(msg.text)
    reply = await handler.handle_subscription(
        farmer_id=str(farmer.id),
        commodity=commodity,
        threshold=threshold,
        condition=condition,  # ">", "<", "=="
        district=district,
        farmer_language=lang
    )
```

**Tables**: `price_alerts`

---

## Intent Classification

### Regex Patterns (85% coverage, instant)

```python
# src/classifier/regex_classifier.py

PRICE_QUERY:
  - "price", "rate", "bhav", "market", "mandi"
  - "भाव", "दर", "किंमत", "मंडी"
  
PRICE_ALERT:
  - "alert", "notify", "when price"
  - "सूचित करो", "अलर्ट"
  
SCHEME_QUERY:
  - "scheme", "eligible", "subsidy", "grant"
  - "योजना", "अर्हता", "सहायता"
  
WEATHER_QUERY:
  - "weather", "forecast", "rainfall", "temp"
  - "हवामान", "पाऊस", "तापमान"
  
PEST_QUERY:
  - "pest", "disease", "bug", "yellow leaves"
  - "कीट", "रोग", "संक्रमण"
  
MSP_ALERT:
  - "msp", "minimum support price"
  - "न्यूनतम समर्थन मूल्य"
  
SUBSCRIBE/UNSUBSCRIBE:
  - "subscribe", "start", "daily"
  - "पाठवा", "सुरू"
  
HELP/GREETING/FEEDBACK: [existing patterns]
```

### LLM Fallback (for unknown intents)

```python
# src/classifier/llm_classifier.py

if regex_result.intent == Intent.UNKNOWN:
    llm_result = await classify_llm(text)  # Gemini
    # Confidence: 0.0-1.0
```

---

## Threshold Parser

Extract price thresholds from natural language:

```python
# src/price/threshold_parser.py

extract_price_threshold("कांदा ₹4000 से अधिक सूचित करो")
→ (4000.0, ">")

extract_price_threshold("alert when price < 3000")
→ (3000.0, "<")

extract_price_threshold("MSP = 2500")
→ (2500.0, "==")

# Multi-format support:
# ₹5000, Rs5000, Rs. 5000, 5000, ₹5,000, रु 5000
```

---

## Farmer Profile Service

```python
# src/services/farmer_service.py

service = FarmerService(session)

# Lookup
farmer = await service.get_by_phone("+919876543210")

# Get crops
crops = await service.get_crops(farmer.id)
# → ["onion", "wheat"]

# Update subscription
await service.update_subscription_status(farmer.id, "active")

# Get full profile
profile = await service.get_farmer_profile(farmer.id)
# → {farmer_id, phone, name, age, land_hectares, district, 
#    language, subscription_status, crops}
```

---

## Scheduler Tasks

### Morning (6:00 AM IST)
```
6:00 AM  → ingest_weather()
          Fetches from IMD + OpenWeather
          
6:15 AM  → ingest_government_schemes()
          Fetches from PMKSY, PM-FASAL, Rashtriya Kranti, etc.
          
6:20 AM  → trigger_msp_alerts()
          Checks MSP thresholds, sends notifications
          
6:30 AM  → broadcast_prices()
          Daily price update to subscribed farmers
```

### Evening (8:00 PM IST)
```
8:00 PM  → ingest_prices()
          Fetches from 4 price sources
          
8:30 PM  → trigger_price_alerts()
          Checks price conditions, sends notifications
```

### Daily (1:00 AM IST)
```
1:00 AM  → hard_delete_erased_farmers()
          Completes 30-day data deletion window
```

---

## Database Schema

### Core Tables

```sql
-- Farmers
farmers (id, phone, name, age, land_hectares, district, 
         preferred_language, subscription_status, ...)

-- Crops
crops_of_interest (id, farmer_id, crop, added_at)

-- Prices
mandi_prices (id, date, crop, mandi, district, modal_price, ...)

-- Alerts
price_alerts (id, farmer_id, commodity, condition, threshold, is_active, ...)

-- Schemes
government_schemes (id, scheme_name, ministry, eligibility_criteria, ...)
msp_alerts (id, farmer_id, commodity, alert_threshold, is_active, ...)

-- Weather
weather_observations (id, date, district, temperature, rainfall, ...)

-- Audit
conversations (id, farmer_id, message_type, intent, ...)
broadcast_log (id, farmer_id, content, sent_at, ...)
consent_events (id, farmer_id, event_type, ...)
```

---

## Migrations

```bash
# All migrations in alembic/versions/

0001_initial_schema.py        # farmers, conversations
0002_extend_mandi_prices.py   # price tables
0003_dpdpa_consent.py         # consent tracking
0004_weather_observations.py  # weather data
0005_voice_support.py         # audio transcription
0006_government_schemes.py    # schemes + msp_alerts
0007_price_alerts.py          # price alerts
0008_farmer_profile_enh.py    # age + land_hectares
```

Apply all:
```bash
alembic upgrade head
```

---

## Testing

### Test Coverage
- **test_threshold_parser.py**: 100+ tests for threshold extraction
- **test_farmer_service.py**: 20+ tests for farmer profiles
- **test_regex_classifier_phase2.py**: 40+ tests for intents
- **test_scheduler_tasks.py**: 20+ tests for alert triggering
- **test_intent_routing.py**: 30+ tests for routing logic
- **test_schemes.py**: 30+ tests for scheme eligibility (existing)

### Run Tests
```bash
pytest src/tests/ -v

# Specific test
pytest src/tests/test_threshold_parser.py -v

# Coverage report
pytest --cov=src src/tests/
```

---

## Production Checklist

- [ ] Database migrations applied
- [ ] Environment variables configured
- [ ] WhatsApp webhook verified
- [ ] SSL certificate installed
- [ ] Redis running
- [ ] Celery worker running
- [ ] Celery beat running
- [ ] Error monitoring (Sentry) configured
- [ ] Log aggregation (ELK) configured
- [ ] Backups scheduled
- [ ] Rate limiting configured
- [ ] Analytics dashboard setup

---

## Performance Notes

### Latency Targets
- Regex classification: < 10ms
- LLM classification: < 2s
- Price query: < 500ms (cached)
- Scheme query: < 1s
- WhatsApp response: < 5s total

### Optimization Opportunities
- Cache mandi prices in Redis (1-hour TTL)
- Cache farmer profiles (30-min TTL)
- Batch alert triggering (process 100 at a time)
- Use connection pooling for DB

---

## Support & Debugging

### Logs
```bash
# View recent logs
tail -f /var/log/kisan-ai/app.log

# Search for errors
grep "ERROR" /var/log/kisan-ai/app.log

# Trace specific farmer
grep "+919876543210" /var/log/kisan-ai/app.log
```

### Database Queries
```sql
-- Check pending alerts
SELECT farmer_id, commodity, threshold, condition 
FROM price_alerts WHERE is_active = true;

-- Check recent prices
SELECT crop, district, modal_price, date 
FROM mandi_prices 
ORDER BY created_at DESC LIMIT 10;

-- Check subscription status
SELECT phone, name, subscription_status, onboarding_state 
FROM farmers 
WHERE subscription_status = 'active';
```

### Monitoring
- Alert trigger rate: Should be < 5/min (indicates price volatility or bad thresholds)
- Farmer engagement: % with active subscriptions
- Classifier accuracy: Regex vs LLM success rates
- Ingestion health: % successful sources per task

---

## Next Steps

**Short-term** (1-2 weeks):
- Deploy to staging environment
- Run closed-alpha with 50 farmers
- Monitor and fix issues

**Medium-term** (1 month):
- Expand to 1000 farmers
- Add Hinglish support
- Implement analytics dashboard

**Long-term** (3+ months):
- Multi-state expansion (Tamil Nadu, Karnataka)
- Video diagnostic support
- Loan/credit eligibility
- Supply chain integration

---

## Support

For issues, contact: support@kisanai.com
For contributions: See CONTRIBUTING.md
For architecture questions: See ARCHITECTURE.md

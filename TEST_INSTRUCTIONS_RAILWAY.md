# Testing on Railway - Complete Guide

Since the database is hosted on Railway, we need to trigger tests directly in the production environment.

## Option 1: Use Admin API Endpoint (Easiest)

### Trigger Advisory Engine Manually

```bash
# Set your admin token
ADMIN_TOKEN="your_admin_jwt_token_here"
RAILWAY_APP_URL="https://kisan-ai-production-xxxxx.up.railway.app"

# Trigger advisory engine to run for all farmers NOW
curl -X POST "${RAILWAY_APP_URL}/admin/advisory/api/run-now" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json"
```

Expected Response:
```json
{
  "farmers": 150,
  "total_created": 342,
  "by_farmer": {
    "1": 2,
    "2": 3,
    ...
  }
}
```

### Check Recent Advisories

```bash
curl -X GET "${RAILWAY_APP_URL}/admin/advisory/api/recent?limit=50" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}"
```

Look for `ai_insights` field in the response - should contain:
```json
{
  "ai_insights": {
    "risk_summary_mr": "कांद्यात उच्च रोग जोखीम",
    "crop_guidance_mr": "थंड पाणी द्या...",
    "treatment_mr": "बोर्डो मिश्रण 1%",
    "generated_at": "2026-05-02T...",
    "model": "meta-llama/llama-3.1-8b-instruct"
  }
}
```

---

## Option 2: SSH into Railway + Run Celery Tasks

### 1. Connect to Railway

```bash
# Make sure you have Railway CLI installed
railway login

# List your projects
railway list projects

# Select the kisan-ai project
railway link

# Open a shell in the running environment
railway shell
```

### 2. Once Inside Railway Shell

```bash
# Check celery status
celery -A src.scheduler.celery_app inspect active

# Run advisory engine immediately
python -c "
import asyncio
from src.scheduler.tasks import _trigger_farm_advisories_async

result = asyncio.run(_trigger_farm_advisories_async())
print('Advisory engine result:', result)
"

# Run price ingestion immediately
python -c "
import asyncio
from src.scheduler.tasks import _ingest_prices_async

result = asyncio.run(_ingest_prices_async())
print('Price ingestion result:', result)
"

# Run daily brief broadcast immediately
python -c "
import asyncio
from src.scheduler.tasks import _broadcast_daily_brief_async

result = asyncio.run(_broadcast_daily_brief_async())
print('Daily brief broadcast result:', result)
"
```

---

## Option 3: Trigger via Celery Beat Directly

```bash
# In Railway shell:

# View scheduled tasks
celery -A src.scheduler.celery_app inspect scheduled

# Check what tasks are queued
celery -A src.scheduler.celery_app inspect active

# Force a task to run (using celery call)
celery -A src.scheduler.celery_app call src.scheduler.tasks.trigger_farm_advisories
celery -A src.scheduler.celery_app call src.scheduler.tasks.ingest_prices
celery -A src.scheduler.celery_app call src.scheduler.tasks.broadcast_daily_brief
```

---

## Option 4: Quick Verification Script

Create a Python script to run in Railway and verify the fixes:

```bash
# In Railway shell:

cat > /tmp/verify_fixes.py << 'EOF'
import asyncio
from datetime import date
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func
from src.config import settings
from src.models.advisory import Advisory

async def verify():
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession)
    
    try:
        async with async_session() as session:
            print("\n" + "="*60)
            print("VERIFICATION CHECK")
            print("="*60)
            
            # Check advisories
            count_result = await session.execute(
                select(func.count()).select_from(Advisory)
                .where(Advisory.advisory_date == date.today())
            )
            advisory_count = count_result.scalar()
            
            # Check AI insights
            ai_result = await session.execute(
                select(func.count()).select_from(Advisory)
                .where(
                    Advisory.advisory_date == date.today(),
                    Advisory.ai_insights.is_not(None)
                )
            )
            ai_count = ai_result.scalar()
            
            print(f"\nAdvisories Today: {advisory_count}")
            print(f"With AI Insights: {ai_count}")
            
            if advisory_count > 0:
                success_rate = (ai_count / advisory_count) * 100
                print(f"AI Success Rate: {success_rate:.1f}%")
                
                if ai_count > 0:
                    print("\nSAMPLE AI INSIGHTS:")
                    result = await session.execute(
                        select(Advisory)
                        .where(
                            Advisory.advisory_date == date.today(),
                            Advisory.ai_insights.is_not(None)
                        )
                        .limit(1)
                    )
                    adv = result.scalar_one_or_none()
                    if adv:
                        print(f"  Rule: {adv.title}")
                        print(f"  Model: {adv.ai_insights.get('model')}")
                        print(f"  Crop Guidance: {adv.ai_insights.get('crop_guidance_mr', 'N/A')[:60]}...")
            
            print("\n" + "="*60)
    finally:
        await engine.dispose()

asyncio.run(verify())
EOF

python /tmp/verify_fixes.py
```

---

## Monitoring During Tests

### Check Celery Logs

```bash
# In Railway shell:
tail -100 logs/celery_worker.log | grep -E "advisory_engine:|daily_brief:|ai_enrichment:"
```

Expected Log Output:
```
advisory_engine: enriching rule=fungal_high_humidity with AI for crops=['onion'] district='ahmednagar'
advisory_engine: AI enrichment success for rule=fungal_high_humidity model=meta-llama/llama-3.1-8b-instruct
daily_brief: querying advisories for farmer_id=123, date=2026-05-02
daily_brief: found 3 advisories for farmer_id=123
```

### Check Database for Results

```bash
# In Railway shell:
psql $DATABASE_URL << SQL
SELECT 
    COUNT(*) as total,
    COUNT(CASE WHEN ai_insights IS NOT NULL THEN 1 END) as with_ai
FROM advisories
WHERE advisory_date = CURRENT_DATE;
SQL
```

---

## Test Sequence

### Recommended Order:

1. **Check Current State**
   ```
   Option 4: Run verification script to see current advisories
   ```

2. **Trigger Advisory Engine**
   ```
   Option 1: Call /admin/advisory/api/run-now
   OR
   Option 2: In railway shell, run _trigger_farm_advisories_async()
   ```

3. **Wait 30 seconds and Verify**
   ```
   Option 4: Run verification script again
   Check logs for "AI enrichment success"
   ```

4. **Trigger Daily Brief Broadcast**
   ```
   Option 2: In railway shell, run _broadcast_daily_brief_async()
   ```

5. **Check Results**
   ```
   - Look at WhatsApp logs for sent messages
   - Check if farmers received briefs with:
     - Part 2: Today's mandi prices
     - Part 3: AI insights with "सुझाव" text
   ```

---

## Getting Admin Token

If you don't have an admin token:

```bash
# In Railway shell or locally (with DATABASE_URL set):

python -c "
import jwt
from src.config import settings

token = jwt.encode(
    {'type': 'admin', 'user': 'test'},
    settings.jwt_secret,
    algorithm='HS256'
)
print('Admin Token:', token)
"
```

Use this token in the API calls above.

---

## Success Indicators

✅ **Advisory Engine Success:**
- `total_created` > 0 in response
- Logs show "AI enrichment success"
- Database shows advisories with `ai_insights` not NULL

✅ **Price Ingestion Success:**
- `persisted` > 0 in response
- Database shows mandi_prices for today

✅ **Daily Brief Success:**
- `sent` > 0 in response
- WhatsApp logs show messages sent
- Farmers report receiving briefs with:
  - Current day's prices in part 2
  - AI insights in part 3

---

## Troubleshooting

### If Advisory Engine Returns 0 Created:
- Check if farmers have `subscription_status = 'active'`
- Check if district is set for farmers
- Check if advisory rules exist and are active
- Check logs for "AI enrichment failed"

### If AI Insights Are NULL:
- Check if `settings.openrouter_api_key` is set
- Check celery logs for API errors
- Verify LLM model is accessible

### If Prices Show as 0:
- Check if API keys are set (agmarknet, etc.)
- Prices may not be available from APIs (check error messages in logs)
- Manual price data can be inserted if APIs unavailable

---

## Next Steps

After testing on Railway:

1. Monitor celery logs for 24 hours
2. Collect farmer feedback on brief quality
3. Verify price accuracy and AI relevance
4. Check cost metrics for AI API usage

All fixes are now in production - no rollback needed unless critical issues found.

# Quick Reference: Weather API Comparison

## At-a-Glance Comparison

```
DIMENSION              CURRENT (IMD+OW)    MAUSAM GRAM          SKYMET
═══════════════════════════════════════════════════════════════════════════════
Coverage              5 MH districts       2.6M panchayats      2.6M panchayats
Granularity           District/Taluka      Panchayat (3km→1km)  Hyper-local (≤5km)
Forecast days         7 days               5 days               15 days
Update frequency      Daily/hourly         Hourly               Hourly/6-hourly
Data freshness        Stale (IMD stubbed)  Live (launched Oct   Real-time
                                           2024)
Cost                  Free (but limited)   FREE ✅              ₹50L-200L/year
API availability      IMD requires IP WL   Not yet (web scrape) Yes (proprietary)
Government backed     Yes (but stubbed)    Yes (official) ✅    No
Reliability SLA       Unknown              Unknown              Unknown
Advisory accuracy     ~40% (district)      ~70% (panchayat)     ~85% (hyper-local)
Time to implement     N/A (exists)         2 weeks (scraper)    3 weeks (if API key)
Maintenance burden    Medium               Medium (scraper)     Low (API)
Scalability           Limited (5 dist)     Excellent (all 28)   Excellent
Data ownership        Government           Government           Private/Skymet
Integration maturity  Not implemented      Can be PoC now       Requires sales
```

---

## Decision Matrix: Which to Choose?

### CHOOSE MAUSAM GRAM IF:
- ✅ Want free, government-backed data
- ✅ Panchayat (3-5km) accuracy is sufficient
- ✅ 5-day forecast horizon is acceptable
- ✅ Can wait 2 weeks to build scraper (or wait for API)
- ✅ Want to scale to pan-India without licensing friction
- ✅ Advisory rules don't require 10+ day outlook

**RECOMMENDED FOR PHASE 1 (Now) ⭐**

### CHOOSE SKYMET IF:
- ✅ Budget exists (₹50L-200L/year)
- ✅ Need 15-day forecast horizon
- ✅ Hyper-local (≤5km) + satellite crop monitoring critical
- ✅ Advisory accuracy > cost (ROI >2x)
- ✅ Comfortable with vendor lock-in
- ✅ Farmer data privacy not a concern

**RECOMMENDED FOR PHASE 3 (Contingency) ⚠️**

### AVOID CURRENT STATUS QUO IF:
- ❌ IMD API stubbed (not fetching)
- ❌ OpenWeather taluka-level (200+ km²) too coarse
- ❌ No panchayat mapping in farmer onboarding
- ❌ Cannot issue hyper-local disease warnings
- ❌ Scaling beyond 5 districts difficult

---

## Implementation Timeline

```
NOW (Week 1-2):
├─ Contact IMD re: MAUSAM GRAM API ETA
├─ Download panchayat reference (data.gov.in)
└─ Begin farmer onboarding redesign (panchayat picker)

PHASE 1 (Week 3-4):
├─ Build MausamGramScraper (beautifulsoup4)
├─ Integrate weather aggregation in advisory engine
├─ Deploy & monitor scraper for 1 month
└─ Measure advisory accuracy improvement (target +60%)

DECISION POINT (End of Month 1):
└─ IF MAUSAM GRAM API available:
   ├─ Migrate to official API
   └─ Decommission scraper
   
   ELSE IF MAUSAM GRAM works well (70%+ accuracy):
   └─ Continue scraper; plan Phase 2 API migration
   
   ELSE IF accuracy plateau, budget approved:
   └─ Contact Skymet sales; negotiate pricing (Phase 3)

PHASE 2 (Week 5-8, post-API):
├─ Replace scraper with official MAUSAM GRAM API
├─ Add error handling & fallback caching
└─ Update tests & documentation

PHASE 3 (Q3 2026, if needed):
├─ Skymet integration (15-day forecast)
├─ Satellite crop health monitoring
└─ Advanced yield prediction
```

---

## Technical Debt & Risks

### MAUSAM GRAM Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Web scraper breaks if HTML changes | 🟡 Medium | Monitor weekly; add CI tests |
| MAUSAM GRAM server downtime | 🟡 Medium | Cache 7-day history; fall back to OpenWeather |
| IP whitelisting (if API requires) | 🟡 Medium | Contact IMD sales; negotiate public API |
| 5-day forecast insufficient for some rules | 🟡 Medium | Design rules for 5-day window; Skymet fallback |
| Panchayat code mapping errors | 🔴 High | Validate GPS against panchayat boundaries ±5km |

### Skymet Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Licensing cost high (₹50L+/year) | 🔴 High | Negotiate volume discount; prove ROI first |
| Vendor lock-in (proprietary API) | 🔴 High | Implement API abstraction layer; keep MAUSAM GRAM fallback |
| No open documentation | 🟡 Medium | Ensure contract includes support SLA + documentation |
| Farmer data privacy (Skymet owns data) | 🔴 High | Clarify GDPR/DPDPA compliance in contract |

---

## Panchayat Data Integration

### Schema Changes Required

```sql
-- 1. Add panchayat reference table
CREATE TABLE panchayat_reference (
  panchayat_code VARCHAR(20) PRIMARY KEY,  -- MH27001001
  panchayat_name VARCHAR(100),
  taluka VARCHAR(100),
  district VARCHAR(100),
  state VARCHAR(50),
  latitude DECIMAL(10,8),
  longitude DECIMAL(11,8),
  area_sq_km DECIMAL(8,2),
  population INT,
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_panchayat_district ON panchayat_reference(district);
CREATE INDEX idx_panchayat_taluka ON panchayat_reference(taluka);

-- 2. Link farmer to panchayat
ALTER TABLE farmers ADD COLUMN panchayat_code VARCHAR(20);
ALTER TABLE farmers ADD CONSTRAINT fk_farmer_panchayat
  FOREIGN KEY (panchayat_code) REFERENCES panchayat_reference(panchayat_code);

-- 3. Update weather_observations
ALTER TABLE weather_observations ADD COLUMN panchayat_code VARCHAR(20);
ALTER TABLE weather_observations ADD CONSTRAINT fk_weather_panchayat
  FOREIGN KEY (panchayat_code) REFERENCES panchayat_reference(panchayat_code);

-- 4. Aggregate view for advisory engine
CREATE VIEW weather_aggregate_5day AS
SELECT
  panchayat_code,
  DATE_TRUNC('day', date)::DATE as forecast_date,
  MAX(value) FILTER (WHERE metric='temperature') as temp_max,
  MIN(value) FILTER (WHERE metric='temperature') as temp_min,
  AVG(value) FILTER (WHERE metric='humidity') as humidity_avg,
  MAX(value) FILTER (WHERE metric='humidity') as humidity_max,
  SUM(value) FILTER (WHERE metric='rainfall') as rainfall_total
FROM weather_observations
WHERE forecast_days_ahead <= 5
GROUP BY panchayat_code, DATE_TRUNC('day', date);
```

### Farmer Onboarding Update

```python
# src/farmer/routes.py

@router.post("/api/farmer/location/suggest")
async def suggest_panchayat(district: str, taluka: str, search: str, db: AsyncSession):
    """Return matching panchayats for autocomplete."""
    results = await db.execute(
        select(PanchayatReference).where(
            PanchayatReference.district == district,
            PanchayatReference.taluka == taluka,
            PanchayatReference.panchayat_name.ilike(f"%{search}%")
        ).limit(10)
    )
    return [
        {
            "code": p.panchayat_code,
            "name": p.panchayat_name,
            "lat": float(p.latitude),
            "lon": float(p.longitude)
        }
        for p in results.scalars().all()
    ]

@router.post("/api/farmer/onboard")
async def onboard_farmer(
    phone: str,
    district: str,
    taluka: str,
    panchayat_code: str,  # ← NEW
    crops: list[str],
    db: AsyncSession
):
    """Create farmer with panchayat-level location."""
    farmer = Farmer(
        phone=phone,
        district=district,
        taluka=taluka,
        panchayat_code=panchayat_code,  # ← NEW
        crops=crops
    )
    db.add(farmer)
    await db.commit()
    return {"farmer_id": farmer.id, "status": "onboarded"}
```

---

## Effort & Cost Summary

| Phase | Task | Effort | Cost | Timeline |
|-------|------|--------|------|----------|
| **Setup** | Panchayat ETL + farmer onboarding | 1 week | ₹0 | Now |
| **Phase 1** | MAUSAM GRAM scraper + advisory integration | 2 weeks | ₹0 | Weeks 3-4 |
| **Phase 1** | Monitor + validate accuracy | 4 weeks | ₹0 | Month 2 |
| **Phase 2** | API migration (if released) | 1 week | ₹0 | TBD |
| **Phase 3** | Skymet integration (optional) | 3 weeks | ₹50L-200L/year | Q3 2026 |
| **Phase 4** | Satellite crop monitoring | 6 weeks | Incl. Skymet | 2027 |

---

## Success Metrics

### MAUSAM GRAM Phase 1

| Metric | Target | Measurement |
|--------|--------|-------------|
| Scraper uptime | 99%+ | Celery task success rate |
| Forecast accuracy vs actual | 85%+ | Compare forecast temp/rainfall vs MAUSAM GRAM actual |
| Advisory accuracy improvement | +60% vs district | A/B test: panchayat-level vs district-level rules |
| Farmer satisfaction | 4.5/5 stars | Post-advisory farmer survey |
| Scaling readiness | 10K farmers | Scraper handles 10K concurrent panchayat requests |

### Phase 3 (Skymet) ROI

| Metric | Target | Calculation |
|--------|--------|-------------|
| Farmers served | 50K+ | Scaled pan-India |
| Value generated | ₹250L/year | 50K × ₹500/farmer value |
| Skymet cost | ₹100L/year | Negotiated enterprise rate |
| ROI | >2x | Revenue / Cost = 2.5x |

---

## Contact Points

### IMD (MAUSAM GRAM)
- **Website:** https://mausamgram.imd.gov.in/
- **API inquiry:** https://mausam.imd.gov.in/responsive/apis.php
- **Agricultural Met:** https://imdagrimet.gov.in/

### Skymet Weather
- **Website:** https://www.skymetweather.com/
- **API/Enterprise:** https://www.skymetweather.com/contact-us
- **Skymitra app:** Available on Google Play (reference for farmer-facing features)

### Panchayat Data
- **Census India:** https://data.gov.in/ (search "panchayat shapefile")
- **Electoral Commission:** EC boundaries database
- **e-GramSwaraj:** https://mygov.in/e-gramswaraj/ (MoPR official portal)

---

## Recommended Action This Week

1. **Send formal inquiry to IMD** → Request MAUSAM GRAM API ETA + access terms
   - Email: imd-api-support@ or contact form at mausam.imd.gov.in
   - Message: "Dhanyada agricultural advisory system needs panchayat-level weather API for farming advisory. When will MAUSAM GRAM public API be available?"

2. **Download panchayat reference data** → Begin ETL
   ```bash
   # From data.gov.in search "panchayat"
   # Download shape file + CSV → PostgreSQL panchayat_reference table
   ```

3. **Review MausamGramScraper architecture** → Start PoC
   ```python
   # src/ingestion/weather/sources/mausamgram_scraper.py
   # Minimal scraper to fetch 1 panchayat from portal; parse HTML
   ```

4. **Plan farmer onboarding redesign** → Design panchayat picker UX
   - Dropdown: District → Taluka → Panchayat (cascading)
   - Search field: Type panchayat name, autocomplete suggestions
   - Lat/lon auto-filled from panchayat_reference

---

**Status:** Ready to implement Phase 1  
**Owner:** Engineering Team  
**Timeline:** Begin Week 1, complete by end of Month 1

# Panchayat-Level Weather Integration: Technical Implementation Guide

## Quick Start

This guide covers the technical implementation of panchayat-level weather integration for Dhanyada's advisory engine.

**Scope:** Phase 1 (MAUSAM GRAM scraper) + Phase 2 (API migration)  
**Timeline:** 3-4 weeks  
**Dependencies:** beautifulsoup4, asyncio, sqlalchemy  
**Testing:** Unit tests + 1-month production monitoring

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│  Farmer Onboarding (Updated)                               │
│  - Phone number                                            │
│  - District → Taluka → Panchayat (cascading dropdowns)    │
│  - Auto-filled: lat/lon from panchayat_reference          │
└────────────────────────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────┐
│  PanchayatReference Table (27K MH villages)                │
│  - panchayat_code: MH27001001                             │
│  - panchayat_name: Pirangut                               │
│  - district, taluka, lat, lon                             │
└────────────────────────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────┐
│  Weather Data Ingestion (Daily 06:30 IST)                 │
│  - Phase 1: MausamGramScraper (web scrape)               │
│  - Phase 2: MausamGramAPI (official API)                  │
│  - Output: WeatherObservation rows (one per panchayat)   │
└────────────────────────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────┐
│  Weather Aggregation (for advisory rules)                  │
│  - 5-7 day forecast aggregation per panchayat            │
│  - Computed: max_temp, avg_humidity, total_rainfall      │
│  - Derived: consecutive_high_humidity_days, etc.         │
└────────────────────────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────┐
│  Advisory Engine (Existing, Updated)                       │
│  - Query weather by farmer's panchayat_code              │
│  - Match rules: disease risk, irrigation, pest alerts    │
│  - Output: Advisory rows for farmer dashboard/WhatsApp   │
└────────────────────────────────────────────────────────────┘
```

---

## Step 1: Database Schema Updates

### 1.1 Create Panchayat Reference Table

```sql
-- Create panchayat_reference table
CREATE TABLE panchayat_reference (
  id SERIAL PRIMARY KEY,
  panchayat_code VARCHAR(20) UNIQUE NOT NULL,      -- MH27001001
  panchayat_name VARCHAR(100) NOT NULL,            -- Pirangut
  taluka VARCHAR(100) NOT NULL,                    -- Haveli
  taluka_code VARCHAR(20),                         -- For join with talukas table
  district VARCHAR(100) NOT NULL,                  -- Pune
  district_code VARCHAR(20),                       -- For join with districts table
  state VARCHAR(50) DEFAULT 'Maharashtra',
  latitude DECIMAL(10,8) NOT NULL,
  longitude DECIMAL(11,8) NOT NULL,
  area_sq_km DECIMAL(8,2),                         -- Panchayat area
  population INT,                                   -- As per census
  households INT,
  avg_household_size DECIMAL(3,1),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast lookup
CREATE INDEX idx_panchayat_code ON panchayat_reference(panchayat_code);
CREATE INDEX idx_panchayat_district_taluka ON panchayat_reference(district, taluka);
CREATE INDEX idx_panchayat_name ON panchayat_reference(panchayat_name);
CREATE INDEX idx_panchayat_location ON panchayat_reference(latitude, longitude);
```

### 1.2 Modify Farmer Model

```python
# src/models/farmer.py

from sqlalchemy import String, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

class Farmer(Base):
    __tablename__ = "farmers"
    
    # ... existing fields ...
    
    # NEW: Panchayat-level location
    panchayat_code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Census code of gram panchayat (e.g., MH27001001)"
    )
    panchayat_name: Mapped[str] = mapped_column(
        String(100),
        nullable=True,
        comment="Readable panchayat name (e.g., Pirangut)"
    )
    taluka: Mapped[str] = mapped_column(
        String(100),
        nullable=True,
        comment="Sub-district name (e.g., Haveli)"
    )
    latitude: Mapped[float] = mapped_column(
        Numeric(10,8),
        nullable=True,
        comment="Auto-filled from panchayat_reference.latitude"
    )
    longitude: Mapped[float] = mapped_column(
        Numeric(11,8),
        nullable=True,
        comment="Auto-filled from panchayat_reference.longitude"
    )
    
    # Foreign key relationship (optional, if using constraints)
    # panchayat_ref: Mapped["PanchayatReference"] = relationship(
    #     "PanchayatReference",
    #     foreign_keys=[panchayat_code],
    #     primaryjoin="Farmer.panchayat_code == PanchayatReference.panchayat_code"
    # )
```

### 1.3 Update WeatherObservation Model

```python
# src/models/weather.py

class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    
    # ... existing fields ...
    
    # NEW: Panchayat-level location
    panchayat_code: Mapped[str] = mapped_column(
        String(20),
        nullable=True,
        comment="Census code of gram panchayat (MH27001001)"
    )
    panchayat_name: Mapped[str] = mapped_column(
        String(100),
        nullable=True,
        comment="Readable panchayat name"
    )
    
    # Add index for fast weather lookup by panchayat
    __table_args__ = (
        *existing_table_args,
        UniqueConstraint(
            "date", "panchayat_code", "metric", "forecast_days_ahead", "source",
            name="uq_weather_panchayat_dedupe"
        ),
        Index("idx_weather_panchayat_lookup", "date", "panchayat_code", "forecast_days_ahead"),
    )
```

### 1.4 Create Alembic Migration

```bash
# Generate migration
alembic revision --autogenerate -m "Add panchayat_reference table and farmer/weather panchayat columns"
```

**Migration file:** `alembic/versions/00XX_add_panchayat_level.py`

---

## Step 2: Load Panchayat Reference Data

### 2.1 Download Panchayat Data

From https://data.gov.in/:
1. Search for "panchayat"
2. Download "Gram Panchayat Master List" (CSV) + shapefile
3. Extract panchayat_code, name, taluka, district, lat/lon

### 2.2 ETL Script

```python
# src/scripts/load_panchayat_reference.py

import csv
import asyncio
from decimal import Decimal
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from src.models.panchayat import PanchayatReference
from src.models.base import Base

async def load_panchayat_csv(csv_path: str, db_url: str):
    """Load panchayat CSV into database.
    
    Expected CSV columns:
    - State Code
    - State Name
    - District Code
    - District Name
    - Taluka Code
    - Taluka Name
    - Gram Panchayat Code
    - Gram Panchayat Name
    - Latitude
    - Longitude
    """
    engine = create_async_engine(db_url, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    inserted = 0
    skipped = 0
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        async with async_session() as session:
            for row in reader:
                try:
                    # Skip non-Maharashtra rows
                    if row.get("State Name", "").lower() != "maharashtra":
                        skipped += 1
                        continue
                    
                    panchayat = PanchayatReference(
                        panchayat_code=row["Gram Panchayat Code"],
                        panchayat_name=row["Gram Panchayat Name"],
                        taluka=row["Taluka Name"],
                        taluka_code=row["Taluka Code"],
                        district=row["District Name"],
                        district_code=row["District Code"],
                        state="Maharashtra",
                        latitude=Decimal(row["Latitude"]),
                        longitude=Decimal(row["Longitude"]),
                    )
                    session.add(panchayat)
                    inserted += 1
                    
                    # Batch commit every 1000 rows
                    if inserted % 1000 == 0:
                        await session.commit()
                        print(f"✅ Loaded {inserted} panchayats...")
                        
                except Exception as e:
                    print(f"⚠️  Skipped row: {row['Gram Panchayat Code']} — {e}")
                    skipped += 1
                    continue
            
            # Final commit
            await session.commit()
    
    await engine.dispose()
    print(f"✅ Panchayat load complete: {inserted} inserted, {skipped} skipped")

if __name__ == "__main__":
    import os
    db_url = os.getenv("DATABASE_URL")
    csv_path = "data/panchayat_reference.csv"
    
    asyncio.run(load_panchayat_csv(csv_path, db_url))
```

**Run:**
```bash
python src/scripts/load_panchayat_reference.py
```

---

## Step 3: MAUSAM GRAM Scraper (Phase 1)

### 3.1 Create Scraper Class

```python
# src/ingestion/weather/sources/mausamgram_scraper.py

"""MAUSAM GRAM (IMD panchayat weather) scraper.

Portal: https://mausamgram.imd.gov.in/
Coverage: 2.6M panchayats across India (3km grid)
Forecast: 5-day, hourly updates
Status: Free government source, web scraping until API available

Design:
1. Fetch panchayat list from database
2. For each panchayat, scrape MAUSAM GRAM portal
3. Parse 5-day forecast from HTML tables
4. Store as WeatherObservation rows
5. Schedule daily at 06:30 IST (after IMD forecast updates)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from src.ingestion.weather.sources.base import WeatherRecord, WeatherSource
from src.models.panchayat import PanchayatReference

logger = logging.getLogger(__name__)


class MausamGramScraper(WeatherSource):
    """Scrape MAUSAM GRAM portal for panchayat-level weather forecasts.
    
    Example MAUSAM GRAM URL:
    https://mausamgram.imd.gov.in/forecast?panchayat=MH27001001
    
    Returns HTML table with 5-day forecast.
    """
    
    name: str = "mausamgram"
    
    def __init__(
        self,
        api_base: str = "https://mausamgram.imd.gov.in",
        timeout: float = 15.0,
        rate_limit_delay: float = 0.5,  # 500ms between requests (avoid hammering IMD)
    ):
        """Initialize MAUSAM GRAM scraper.
        
        Args:
            api_base: Base URL of MAUSAM GRAM portal
            timeout: Request timeout in seconds
            rate_limit_delay: Delay between requests (seconds)
        """
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def fetch_panchayat(self, panchayat_code: str, panchayat_name: str) -> list[WeatherRecord]:
        """Fetch 5-day forecast for a single panchayat.
        
        Args:
            panchayat_code: Census code (MH27001001)
            panchayat_name: Readable name (Pirangut)
        
        Returns:
            List of WeatherRecord objects (one per metric per day)
        
        Raises:
            httpx.HTTPError on network failure
        """
        try:
            # Construct MAUSAM GRAM search URL
            # Note: Exact endpoint may vary; adjust based on actual portal structure
            url = f"{self.api_base}/forecast"
            params = {
                "panchayat": panchayat_code,
                "district": panchayat_name.split(',')[0] if ',' in panchayat_name else "",
            }
            
            logger.debug(f"MausamGram: fetching {panchayat_code} from {url}")
            
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            
            # Parse HTML response
            records = await self._parse_html(response.text, panchayat_code, panchayat_name)
            logger.info(f"MausamGram: {panchayat_code} — fetched {len(records)} records")
            
            return records
            
        except httpx.HTTPError as exc:
            logger.error(f"MausamGram: fetch failed for {panchayat_code}: {exc}")
            raise
        except Exception as exc:
            logger.error(f"MausamGram: parse failed for {panchayat_code}: {exc}", exc_info=True)
            raise
    
    async def _parse_html(self, html: str, panchayat_code: str, panchayat_name: str) -> list[WeatherRecord]:
        """Parse MAUSAM GRAM HTML response into WeatherRecord objects.
        
        Expected HTML structure (from MAUSAM GRAM portal):
        <table class="forecast-table">
          <tr>
            <td>Date</td>
            <td>Max Temp (°C)</td>
            <td>Min Temp (°C)</td>
            <td>Rainfall (mm)</td>
            <td>Humidity (%)</td>
            <td>Wind Speed (km/h)</td>
          </tr>
          <tr>
            <td>2026-04-20</td>
            <td>32.5</td>
            <td>24.0</td>
            <td>0.0</td>
            <td>65</td>
            <td>12.0</td>
          </tr>
          ...
        </table>
        """
        records = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Find forecast table
            table = soup.find('table', {'class': 'forecast-table'})
            if not table:
                logger.warning(f"MausamGram: no forecast table found for {panchayat_code}")
                return []
            
            # Extract rows (skip header)
            rows = table.find_all('tr')[1:]
            
            for idx, row in enumerate(rows):
                try:
                    cells = [cell.text.strip() for cell in row.find_all('td')]
                    
                    if len(cells) < 6:
                        logger.warning(f"MausamGram: incomplete row in {panchayat_code}: {cells}")
                        continue
                    
                    forecast_date = datetime.fromisoformat(cells[0]).date()
                    days_ahead = (forecast_date - date.today()).days
                    
                    # Skip forecasts beyond 5 days
                    if days_ahead > 5:
                        logger.debug(f"MausamGram: skipping {forecast_date} (>5 days ahead)")
                        continue
                    
                    # Parse metrics
                    metrics = {
                        'temperature': (float(cells[1]) + float(cells[2])) / 2,  # Avg of max/min
                        'temperature_max': float(cells[1]),
                        'temperature_min': float(cells[2]),
                        'rainfall': float(cells[3]),
                        'humidity': float(cells[4]),
                        'wind_speed': float(cells[5]),
                    }
                    
                    # Create WeatherRecord for each metric
                    for metric_name, value in metrics.items():
                        records.append(WeatherRecord(
                            trade_date=forecast_date,
                            apmc=panchayat_code,
                            district="",  # Will be populated from panchayat_reference
                            panchayat_code=panchayat_code,
                            panchayat_name=panchayat_name,
                            metric=metric_name,
                            value=Decimal(str(value)).quantize(Decimal("0.1")),
                            unit=self._get_unit(metric_name),
                            forecast_days_ahead=days_ahead,
                            source=self.name,
                            raw={'row': cells, 'forecast_date': str(forecast_date)},
                        ))
                
                except (ValueError, IndexError) as e:
                    logger.warning(f"MausamGram: failed to parse row {idx} in {panchayat_code}: {e}")
                    continue
            
            return records
        
        except Exception as exc:
            logger.error(f"MausamGram: HTML parse failed for {panchayat_code}: {exc}", exc_info=True)
            raise
    
    @staticmethod
    def _get_unit(metric: str) -> str:
        """Return unit for a given metric."""
        units = {
            'temperature': '°C',
            'temperature_max': '°C',
            'temperature_min': '°C',
            'rainfall': 'mm',
            'humidity': '%',
            'wind_speed': 'km/h',
            'pressure': 'hPa',
        }
        return units.get(metric, 'unknown')
    
    async def fetch_all_panchayats(self, db) -> list[WeatherRecord]:
        """Fetch forecasts for all panchayats.
        
        WARNING: This will make 27K requests to IMD. Use rate limiting!
        In production, stagger across multiple runs or wait for API.
        """
        from sqlalchemy import select
        
        all_records = []
        errors = 0
        
        # Get all panchayats
        result = await db.execute(select(PanchayatReference).limit(100))  # ← Limit for testing
        panchayats = result.scalars().all()
        
        logger.info(f"MausamGram: fetching forecasts for {len(panchayats)} panchayats")
        
        for idx, panchayat in enumerate(panchayats):
            try:
                records = await self.fetch_panchayat(
                    panchayat.panchayat_code,
                    panchayat.panchayat_name
                )
                all_records.extend(records)
                
                # Rate limiting
                if (idx + 1) % 10 == 0:
                    logger.info(f"MausamGram: processed {idx + 1}/{len(panchayats)} panchayats")
                    await asyncio.sleep(self.rate_limit_delay)
                    
            except Exception as e:
                errors += 1
                logger.error(f"MausamGram: failed for {panchayat.panchayat_code}: {e}")
                await asyncio.sleep(self.rate_limit_delay * 2)  # Backoff on error
        
        logger.info(f"MausamGram: completed {len(panchayats)} panchayats ({errors} errors)")
        return all_records
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
```

### 3.2 Update Celery Task

```python
# src/scheduler/tasks.py

from celery import shared_task
from sqlalchemy import select, delete
from datetime import date, datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.ingestion.weather.sources.mausamgram_scraper import MausamGramScraper
from src.models.weather import WeatherObservation
from src.models.panchayat import PanchayatReference

@shared_task(bind=True, max_retries=3)
def ingest_mausamgram_weather(self):
    """Ingest MAUSAM GRAM forecasts for all panchayats.
    
    Scheduled: Daily at 06:30 IST (after IMD forecast updates ~06:00 IST)
    Duration: ~30-60 minutes (depends on number of panchayats)
    """
    import asyncio
    from src.config import get_settings
    
    settings = get_settings()
    
    try:
        logger.info("🌾 MAUSAM GRAM ingestion started")
        
        # Run async ingestion
        result = asyncio.run(_ingest_async(settings))
        
        logger.info(f"✅ MAUSAM GRAM ingestion complete: {result['inserted']} records, {result['errors']} errors")
        return result
        
    except Exception as exc:
        logger.error(f"❌ MAUSAM GRAM ingestion failed: {exc}")
        self.retry(exc=exc, countdown=300)  # Retry after 5 minutes

async def _ingest_async(settings):
    """Async MAUSAM GRAM ingestion."""
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    scraper = MausamGramScraper()
    inserted = 0
    errors = 0
    
    try:
        async with async_session() as session:
            # Fetch all panchayats
            result = await session.execute(select(PanchayatReference))
            panchayats = result.scalars().all()
            logger.info(f"Processing {len(panchayats)} panchayats")
            
            # Delete yesterday's forecasts (to avoid stale data)
            yesterday = date.today() - timedelta(days=1)
            await session.execute(
                delete(WeatherObservation).where(
                    (WeatherObservation.date <= yesterday) &
                    (WeatherObservation.source == "mausamgram")
                )
            )
            await session.commit()
            
            # Fetch and store new forecasts
            for idx, panchayat in enumerate(panchayats):
                try:
                    records = await scraper.fetch_panchayat(
                        panchayat.panchayat_code,
                        panchayat.panchayat_name
                    )
                    
                    for record in records:
                        # Convert WeatherRecord to ORM
                        obs = WeatherObservation(
                            date=record.trade_date,
                            apmc=record.apmc,
                            district=panchayat.district,  # From panchayat_reference
                            panchayat_code=panchayat.panchayat_code,
                            panchayat_name=panchayat.panchayat_name,
                            metric=record.metric,
                            value=record.value,
                            unit=record.unit,
                            min_value=record.min_value,
                            max_value=record.max_value,
                            forecast_days_ahead=record.forecast_days_ahead,
                            source=record.source,
                            raw_payload=record.raw,
                        )
                        session.add(obs)
                        inserted += 1
                    
                    # Batch commit every 100 panchayats
                    if (idx + 1) % 100 == 0:
                        await session.commit()
                        logger.info(f"✅ {idx + 1}/{len(panchayats)} processed, {inserted} records")
                        
                except Exception as e:
                    errors += 1
                    logger.warning(f"⚠️  {panchayat.panchayat_code}: {e}")
            
            # Final commit
            await session.commit()
    
    finally:
        await scraper.close()
        await engine.dispose()
    
    return {"inserted": inserted, "errors": errors}

# Add to celery beat schedule
# src/scheduler/celery_app.py

app.conf.beat_schedule = {
    # ... existing tasks ...
    
    'ingest-mausamgram-weather': {
        'task': 'src.scheduler.tasks.ingest_mausamgram_weather',
        'schedule': crontab(hour=6, minute=30),  # 06:30 IST
    },
}
```

---

## Step 4: Weather Aggregation for Advisory

### 4.1 Create WeatherAggregate

```python
# src/advisory/weather.py

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.weather import WeatherObservation


@dataclass
class WeatherAggregate:
    """Aggregated weather data for advisory rule evaluation."""
    
    panchayat_code: str
    forecast_date_range: tuple[date, date]
    
    # Aggregates (0-5 days)
    max_temp_c: float
    min_temp_c: float
    avg_humidity_pct: float
    max_humidity_pct: float
    total_rainfall_mm: float
    avg_wind_speed_kmh: float
    
    # Derived metrics for disease/irrigation rules
    consecutive_high_humidity_days: int     # Days with RH >85%
    consecutive_hot_days: int               # Days with T_max >35°C
    leaf_wetness_hours: int                 # Est. from RH + rainfall
    
    @staticmethod
    async def from_panchayat(
        db: AsyncSession,
        panchayat_code: str,
        days_ahead: int = 5,
        start_date: date = None,
    ) -> WeatherAggregate:
        """Aggregate weather forecast for a panchayat.
        
        Args:
            db: Database session
            panchayat_code: Panchayat census code
            days_ahead: Number of days to aggregate (default 5)
            start_date: Start date (default today)
        
        Returns:
            WeatherAggregate with computed metrics
        """
        from datetime import timedelta
        
        if start_date is None:
            start_date = date.today()
        
        end_date = start_date + timedelta(days=days_ahead)
        
        # Fetch all weather observations for panchayat
        result = await db.execute(
            select(WeatherObservation).where(
                (WeatherObservation.panchayat_code == panchayat_code) &
                (WeatherObservation.date >= start_date) &
                (WeatherObservation.date <= end_date) &
                (WeatherObservation.forecast_days_ahead <= days_ahead) &
                (WeatherObservation.source == "mausamgram")  # Prioritize MAUSAM GRAM
            ).order_by(WeatherObservation.date)
        )
        
        observations = result.scalars().all()
        
        if not observations:
            raise ValueError(f"No weather data for {panchayat_code} ({start_date} to {end_date})")
        
        # Aggregate by date and metric
        daily_temps = {}  # date -> [min, max]
        daily_humidity = {}  # date -> [values]
        daily_rainfall = {}  # date -> value
        daily_wind = {}  # date -> [values]
        
        for obs in observations:
            d = obs.date
            
            if obs.metric == 'temperature':
                daily_temps[d] = daily_temps.get(d, [obs.value, obs.value])
                daily_temps[d][0] = min(daily_temps[d][0], obs.min_value or obs.value)
                daily_temps[d][1] = max(daily_temps[d][1], obs.max_value or obs.value)
            
            elif obs.metric == 'humidity':
                if d not in daily_humidity:
                    daily_humidity[d] = []
                daily_humidity[d].append(obs.value)
            
            elif obs.metric == 'rainfall':
                daily_rainfall[d] = obs.value
            
            elif obs.metric == 'wind_speed':
                if d not in daily_wind:
                    daily_wind[d] = []
                daily_wind[d].append(obs.value)
        
        # Compute aggregates
        temp_values = [t for min_t, max_t in daily_temps.values() for t in [min_t, max_t]]
        humidity_values = [h for hvals in daily_humidity.values() for h in hvals]
        rainfall_values = list(daily_rainfall.values())
        wind_values = [w for wvals in daily_wind.values() for w in wvals]
        
        max_temp = float(max(temp_values)) if temp_values else 0
        min_temp = float(min(temp_values)) if temp_values else 0
        avg_humidity = float(sum(humidity_values) / len(humidity_values)) if humidity_values else 0
        max_humidity = float(max(humidity_values)) if humidity_values else 0
        total_rainfall = float(sum(rainfall_values)) if rainfall_values else 0
        avg_wind = float(sum(wind_values) / len(wind_values)) if wind_values else 0
        
        # Derived: consecutive high humidity days (RH >85%)
        consecutive_high_humidity = 0
        for d in sorted(daily_humidity.keys()):
            if daily_humidity[d] and all(h > 85 for h in daily_humidity[d]):
                consecutive_high_humidity += 1
            else:
                consecutive_high_humidity = 0
        
        # Derived: consecutive hot days (T_max >35°C)
        consecutive_hot = 0
        for d in sorted(daily_temps.keys()):
            if daily_temps[d][1] > 35:
                consecutive_hot += 1
            else:
                consecutive_hot = 0
        
        # Derived: leaf wetness hours (estimated from RH + rainfall)
        # Formula: if RH >85% or rainfall >0, add hours
        leaf_wetness = 0
        for d in daily_humidity.keys():
            if (daily_humidity[d] and any(h > 85 for h in daily_humidity[d])) or \
               (d in daily_rainfall and daily_rainfall[d] > 0):
                leaf_wetness += 6  # Estimate 6 hours wetness per day
        
        return WeatherAggregate(
            panchayat_code=panchayat_code,
            forecast_date_range=(start_date, end_date),
            max_temp_c=max_temp,
            min_temp_c=min_temp,
            avg_humidity_pct=avg_humidity,
            max_humidity_pct=max_humidity,
            total_rainfall_mm=total_rainfall,
            avg_wind_speed_kmh=avg_wind,
            consecutive_high_humidity_days=consecutive_high_humidity,
            consecutive_hot_days=consecutive_hot,
            leaf_wetness_hours=leaf_wetness,
        )
```

---

## Step 5: Updated Farmer Onboarding

### 5.1 Farmer Endpoints

```python
# src/farmer/routes.py

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.farmer import Farmer
from src.models.panchayat import PanchayatReference

router = APIRouter()

@router.get("/api/farmer/districts")
async def list_districts(db: AsyncSession = Depends(get_db)):
    """List all Maharashtra districts."""
    result = await db.execute(
        select(PanchayatReference.district).distinct().order_by(PanchayatReference.district)
    )
    return {"districts": result.scalars().all()}

@router.get("/api/farmer/talukas/{district}")
async def list_talukas(district: str, db: AsyncSession = Depends(get_db)):
    """List talukas in a district."""
    result = await db.execute(
        select(PanchayatReference.taluka)
        .where(PanchayatReference.district == district)
        .distinct()
        .order_by(PanchayatReference.taluka)
    )
    return {"talukas": result.scalars().all()}

@router.get("/api/farmer/panchayats/{district}/{taluka}")
async def list_panchayats(district: str, taluka: str, db: AsyncSession = Depends(get_db)):
    """List panchayats in a taluka."""
    result = await db.execute(
        select(PanchayatReference)
        .where(
            (PanchayatReference.district == district) &
            (PanchayatReference.taluka == taluka)
        )
        .order_by(PanchayatReference.panchayat_name)
    )
    panchayats = result.scalars().all()
    return {
        "panchayats": [
            {
                "code": p.panchayat_code,
                "name": p.panchayat_name,
                "lat": float(p.latitude),
                "lon": float(p.longitude),
            }
            for p in panchayats
        ]
    }

@router.post("/api/farmer/onboard")
async def onboard_farmer(
    phone: str,
    name: str,
    district: str,
    taluka: str,
    panchayat_code: str,
    crops: list[str],
    db: AsyncSession = Depends(get_db),
):
    """Create a new farmer with panchayat-level location."""
    # Validate panchayat exists
    result = await db.execute(
        select(PanchayatReference).where(PanchayatReference.panchayat_code == panchayat_code)
    )
    panchayat = result.scalar_one_or_none()
    
    if not panchayat:
        raise HTTPException(status_code=400, detail=f"Panchayat {panchayat_code} not found")
    
    # Create farmer
    farmer = Farmer(
        phone=phone,
        name=name,
        district=district,
        taluka=taluka,
        panchayat_code=panchayat_code,
        panchayat_name=panchayat.panchayat_name,
        latitude=float(panchayat.latitude),
        longitude=float(panchayat.longitude),
        crops=crops,
        onboarding_state="complete",
    )
    
    db.add(farmer)
    await db.commit()
    
    return {
        "farmer_id": farmer.id,
        "status": "onboarded",
        "panchayat": {
            "code": panchayat.panchayat_code,
            "name": panchayat.panchayat_name,
            "district": panchayat.district,
            "lat": float(panchayat.latitude),
            "lon": float(panchayat.longitude),
        }
    }
```

### 5.2 Frontend (HTML/JS)

```html
<!-- src/farmer/templates/onboarding.html -->

<div id="onboarding-form">
  <h2>Welcome Farmer 🌾</h2>
  
  <form id="form-onboarding">
    <!-- Phone -->
    <label>Phone Number</label>
    <input type="tel" id="phone" placeholder="+919876543210" required />
    
    <!-- Name -->
    <label>Your Name</label>
    <input type="text" id="name" placeholder="Ramesh Sharma" required />
    
    <!-- District -->
    <label>District</label>
    <select id="district" onchange="load_talukas()" required>
      <option value="">Select district...</option>
    </select>
    
    <!-- Taluka -->
    <label>Taluka (Sub-District)</label>
    <select id="taluka" onchange="load_panchayats()" required>
      <option value="">Select taluka...</option>
    </select>
    
    <!-- Panchayat -->
    <label>Gram Panchayat (Village)</label>
    <select id="panchayat" required>
      <option value="">Select panchayat...</option>
    </select>
    <small>Your village or gram panchayat</small>
    
    <!-- Crops -->
    <label>Your Crops</label>
    <div id="crops-list">
      <input type="checkbox" name="crop" value="onion" /> Onion
      <input type="checkbox" name="crop" value="tomato" /> Tomato
      <input type="checkbox" name="crop" value="cotton" /> Cotton
      <!-- ... more crops ... -->
    </div>
    
    <button type="submit">Complete Onboarding</button>
  </form>
</div>

<script>
async function load_districts() {
  const res = await fetch('/api/farmer/districts');
  const {districts} = await res.json();
  
  const select = document.getElementById('district');
  districts.forEach(d => {
    select.innerHTML += `<option value="${d}">${d}</option>`;
  });
}

async function load_talukas() {
  const district = document.getElementById('district').value;
  if (!district) return;
  
  const res = await fetch(`/api/farmer/talukas/${district}`);
  const {talukas} = await res.json();
  
  const select = document.getElementById('taluka');
  select.innerHTML = '<option value="">Select taluka...</option>';
  talukas.forEach(t => {
    select.innerHTML += `<option value="${t}">${t}</option>`;
  });
}

async function load_panchayats() {
  const district = document.getElementById('district').value;
  const taluka = document.getElementById('taluka').value;
  if (!district || !taluka) return;
  
  const res = await fetch(`/api/farmer/panchayats/${district}/${taluka}`);
  const {panchayats} = await res.json();
  
  const select = document.getElementById('panchayat');
  select.innerHTML = '<option value="">Select panchayat...</option>';
  panchayats.forEach(p => {
    select.innerHTML += `<option value="${p.code}" data-lat="${p.lat}" data-lon="${p.lon}">${p.name}</option>`;
  });
}

document.getElementById('form-onboarding').addEventListener('submit', async (e) => {
  e.preventDefault();
  
  const panchayat_select = document.getElementById('panchayat');
  const selected_option = panchayat_select.options[panchayat_select.selectedIndex];
  
  const crops = Array.from(document.querySelectorAll('input[name="crop"]:checked'))
    .map(c => c.value);
  
  const data = {
    phone: document.getElementById('phone').value,
    name: document.getElementById('name').value,
    district: document.getElementById('district').value,
    taluka: document.getElementById('taluka').value,
    panchayat_code: selected_option.value,
    crops: crops,
  };
  
  const res = await fetch('/api/farmer/onboard', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  
  const result = await res.json();
  alert(`Welcome! Your village is ${result.panchayat.name}, ${result.panchayat.district}.`);
  // Redirect to farmer dashboard
  window.location.href = '/farmer/dashboard';
});

// Load districts on page load
window.addEventListener('DOMContentLoaded', load_districts);
</script>
```

---

## Testing

### Unit Tests

```python
# tests/test_mausamgram_scraper.py

import pytest
from unittest.mock import MagicMock, patch
from src.ingestion.weather.sources.mausamgram_scraper import MausamGramScraper

@pytest.mark.asyncio
async def test_mausamgram_parse_html():
    """Test HTML parsing."""
    html = """
    <table class="forecast-table">
      <tr><td>Date</td><td>Max Temp</td><td>Min Temp</td><td>Rainfall</td><td>Humidity</td><td>Wind</td></tr>
      <tr><td>2026-04-20</td><td>32.5</td><td>24.0</td><td>0.0</td><td>65</td><td>12.0</td></tr>
      <tr><td>2026-04-21</td><td>31.0</td><td>23.5</td><td>2.5</td><td>70</td><td>14.0</td></tr>
    </table>
    """
    
    scraper = MausamGramScraper()
    records = await scraper._parse_html(html, "MH27001001", "Pirangut")
    
    # Should have 5 metrics × 2 days = 10 records
    assert len(records) == 10
    
    # Check first day temp record
    temp_rec = [r for r in records if r.metric == 'temperature' and r.trade_date.day == 20][0]
    assert float(temp_rec.value) == 28.25  # (32.5 + 24.0) / 2
    
    scraper.close()

@pytest.mark.asyncio
async def test_weather_aggregate():
    """Test weather aggregation for advisory rules."""
    from datetime import date
    from src.advisory.weather import WeatherAggregate
    from src.models.weather import WeatherObservation
    
    # Mock observations
    mock_obs = [
        WeatherObservation(date=date.today(), metric='temperature', value=Decimal('32'), max_value=Decimal('32'), min_value=Decimal('24')),
        WeatherObservation(date=date.today(), metric='humidity', value=Decimal('90')),
        WeatherObservation(date=date.today(), metric='rainfall', value=Decimal('0')),
    ]
    
    # Mock database query
    mock_db = MagicMock()
    mock_db.execute = MagicMock()
    
    # Create aggregate
    aggregate = WeatherAggregate(
        panchayat_code="MH27001001",
        forecast_date_range=(date.today(), date.today()),
        max_temp_c=32,
        min_temp_c=24,
        avg_humidity_pct=90,
        max_humidity_pct=90,
        total_rainfall_mm=0,
        avg_wind_speed_kmh=12,
        consecutive_high_humidity_days=1,
        consecutive_hot_days=0,
        leaf_wetness_hours=6,
    )
    
    # Check derived metrics
    assert aggregate.consecutive_high_humidity_days == 1
    assert aggregate.max_temp_c == 32
```

---

## Deployment Checklist

- [ ] Alembic migration created & tested
- [ ] Panchayat reference data loaded (27K rows)
- [ ] MausamGramScraper implemented & unit tested
- [ ] Farmer model updated with panchayat columns
- [ ] Farmer onboarding UI updated (cascading dropdowns)
- [ ] Celery task scheduled (06:30 IST)
- [ ] Weather aggregation implemented
- [ ] Advisory engine updated to use panchayat-level weather
- [ ] End-to-end test: farmer onboarding → advisory generation
- [ ] Production monitoring: scraper uptime, error rates
- [ ] Documentation: README + setup guide

---

## Monitoring & Alerting

### Prometheus Metrics

```python
# src/metrics.py

from prometheus_client import Counter, Histogram

mausamgram_scrape_duration = Histogram(
    'mausamgram_scrape_duration_seconds',
    'Time to scrape MAUSAM GRAM for all panchayats',
)

mausamgram_records_ingested = Counter(
    'mausamgram_records_ingested_total',
    'Total weather records ingested from MAUSAM GRAM',
)

mausamgram_errors = Counter(
    'mausamgram_errors_total',
    'Total errors during MAUSAM GRAM scraping',
    ['panchayat_code'],
)
```

### Grafana Dashboard

- Scraper uptime (%)
- Records ingested per day
- Error rate by panchayat
- Forecast latency (minutes behind IMD updates)

---

## Next Steps (Phase 2)

Once MAUSAM GRAM API released:
1. Get API documentation + access token from IMD
2. Replace scraper with `MausamGramAPISource`
3. Update Celery task to use API
4. Decommission scraper

---

**Status:** Ready to implement  
**Owner:** Backend Team  
**Timeline:** 3-4 weeks  
**Success Criteria:** 10K farmers with panchayat-level forecasts, 70%+ advisory accuracy improvement

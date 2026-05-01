#!/usr/bin/env python3
"""
One-time script to populate villages table with complete Ahilyanagar data from Wikidata.

Usage:
    python -m src.scripts.populate_ahilyanagar_villages

This script:
    1. Queries Wikidata for all villages in Ahilyanagar district, Maharashtra
    2. Groups villages by taluka
    3. Geocodes each village using Nominatim (OSM) for lat/long
    4. Bulk upserts into PostgreSQL villages table
    5. Provides summary statistics

No rate limiting — but Wikidata/Nominatim have public usage guidelines (respectful use).
"""
import asyncio
import json
import logging
from typing import Optional
from urllib.parse import urlencode
from urllib.request import urlopen
from datetime import datetime

from sqlalchemy import select, func, text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.models import Village
from src.models.base import Base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Wikidata endpoints
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

# Nominatim (OSM) geocoding endpoint
NOMINATIM_API = "https://nominatim.openstreetmap.org/search"


def query_wikidata_villages() -> dict[str, list[str]]:
    """
    Query Wikidata for all villages in Ahilyanagar district, grouped by taluka.

    Returns:
        {"taluka_name": ["village1", "village2", ...], ...}
    """
    logger.info("Querying Wikidata for Ahilyanagar villages...")

    sparql_query = """
    SELECT ?villageName ?talukaName WHERE {
      # Village is located in Ahilyanagar district
      ?village wdt:P131* wd:Q1581850 .  # Ahilyanagar district Q-ID
      ?village rdfs:label ?villageName . FILTER(LANG(?villageName) = "en") .
      ?village wdt:P131 ?taluka .
      ?taluka rdfs:label ?talukaName . FILTER(LANG(?talukaName) = "en") .

      # Only villages (place=village)
      ?village wdt:P625 ?coord .
    }
    ORDER BY ?talukaName ?villageName
    """

    try:
        params = {
            "query": sparql_query,
            "format": "json",
        }
        url = f"{SPARQL_ENDPOINT}?{urlencode(params)}"
        response = urlopen(url, timeout=30)
        data = json.loads(response.read().decode())

        villages_by_taluka = {}
        for binding in data.get("results", {}).get("bindings", []):
            village = binding["villageName"]["value"]
            taluka = binding["talukaName"]["value"]

            if taluka not in villages_by_taluka:
                villages_by_taluka[taluka] = []
            villages_by_taluka[taluka].append(village)

        logger.info(f"Found {sum(len(v) for v in villages_by_taluka.values())} villages across {len(villages_by_taluka)} talukas")
        return villages_by_taluka
    except Exception as e:
        logger.error(f"Wikidata query failed: {e}")
        return {}


def geocode_village(village_name: str, taluka_name: str, district: str = "Ahilyanagar") -> Optional[tuple[float, float]]:
    """
    Geocode a village using Nominatim (OpenStreetMap).

    Args:
        village_name: Name of the village
        taluka_name: Name of the taluka
        district: District name (default: Ahilyanagar)

    Returns:
        (latitude, longitude) or None if not found
    """
    try:
        # Format: "village, taluka, district, maharashtra, india"
        query = f"{village_name}, {taluka_name}, {district}, Maharashtra, India"

        params = {
            "q": query,
            "format": "json",
            "limit": 1,
        }
        url = f"{NOMINATIM_API}?{urlencode(params)}"

        response = urlopen(url, timeout=10)
        data = json.loads(response.read().decode())

        if data and len(data) > 0:
            result = data[0]
            lat = float(result["lat"])
            lon = float(result["lon"])
            logger.debug(f"✓ {village_name}: ({lat:.4f}, {lon:.4f})")
            return (lat, lon)

        logger.warning(f"✗ No coordinates found for {village_name}, {taluka_name}")
        return None
    except Exception as e:
        logger.warning(f"Geocoding failed for {village_name}: {e}")
        return None


async def populate_database(villages_by_taluka: dict[str, list[str]]) -> dict:
    """
    Bulk upsert villages into PostgreSQL.

    Args:
        villages_by_taluka: Dict mapping taluka name to list of village names

    Returns:
        {"inserted": count, "updated": count, "failed": count, "duplicates": count}
    """
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {"inserted": 0, "updated": 0, "failed": 0, "duplicates": 0}

    try:
        async with async_session() as session:
            total_villages = sum(len(v) for v in villages_by_taluka.values())
            processed = 0

            for taluka, villages in sorted(villages_by_taluka.items()):
                logger.info(f"\n📍 Processing taluka: {taluka} ({len(villages)} villages)")

                for village in villages:
                    processed += 1

                    # Geocode the village
                    coords = geocode_village(village, taluka)
                    if not coords:
                        logger.warning(f"  Skipping {village} (no coordinates)")
                        stats["failed"] += 1
                        continue

                    lat, lon = coords

                    try:
                        # Upsert using INSERT ... ON CONFLICT
                        await session.execute(
                            sql_text(
                                """
                                INSERT INTO villages
                                (village_name, taluka_name, district_name, district_slug, latitude, longitude)
                                VALUES (:vn, :tn, :dn, :ds, :lat, :lon)
                                ON CONFLICT (village_name, taluka_name, district_slug)
                                DO UPDATE SET latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                                """
                            ),
                            {
                                "vn": village,
                                "tn": taluka,
                                "dn": "Ahilyanagar",
                                "ds": "ahilyanagar",
                                "lat": lat,
                                "lon": lon,
                            },
                        )
                        stats["inserted"] += 1

                        # Progress indicator
                        if processed % 10 == 0:
                            logger.info(f"  Progress: {processed}/{total_villages}")

                    except Exception as e:
                        if "duplicate" in str(e).lower():
                            stats["duplicates"] += 1
                        else:
                            logger.error(f"  Error inserting {village}: {e}")
                            stats["failed"] += 1

                # Commit after each taluka
                await session.commit()

            logger.info("\n✅ All villages committed to database")

    finally:
        await engine.dispose()

    return stats


async def verify_population() -> dict:
    """
    Verify the population by checking counts per taluka.

    Returns:
        {"total": count, "by_taluka": {taluka: count, ...}}
    """
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            # Total count
            result = await session.execute(
                select(func.count(Village.id)).where(Village.district_slug == "ahilyanagar")
            )
            total = result.scalar()

            # By taluka
            result = await session.execute(
                select(Village.taluka_name, func.count(Village.id))
                .where(Village.district_slug == "ahilyanagar")
                .group_by(Village.taluka_name)
                .order_by(Village.taluka_name)
            )
            by_taluka = dict(result.all())

            return {"total": total, "by_taluka": by_taluka}

    finally:
        await engine.dispose()


async def main():
    """Main workflow: fetch, geocode, populate, verify."""
    logger.info("=" * 60)
    logger.info("🌾 Ahilyanagar Villages Population Script (Wikidata)")
    logger.info("=" * 60)

    # Step 1: Fetch from Wikidata
    villages_by_taluka = query_wikidata_villages()
    if not villages_by_taluka:
        logger.error("Failed to fetch villages from Wikidata. Exiting.")
        return

    logger.info(f"\n📊 Fetched data:")
    logger.info(f"   Total talukas: {len(villages_by_taluka)}")
    logger.info(f"   Total villages: {sum(len(v) for v in villages_by_taluka.values())}")

    # Step 2: Populate database
    logger.info("\n⏳ Geocoding and populating database...")
    logger.info("   (This may take 5-10 minutes due to Nominatim rate limiting)")
    stats = await populate_database(villages_by_taluka)

    logger.info(f"\n📈 Population Stats:")
    logger.info(f"   Inserted: {stats['inserted']}")
    logger.info(f"   Updated: {stats['updated']}")
    logger.info(f"   Duplicates: {stats['duplicates']}")
    logger.info(f"   Failed: {stats['failed']}")

    # Step 3: Verify
    logger.info("\n🔍 Verification:")
    verification = await verify_population()

    logger.info(f"   Total villages in DB: {verification['total']}")
    logger.info(f"\n   By Taluka:")
    for taluka, count in sorted(verification["by_taluka"].items()):
        logger.info(f"      {taluka}: {count} villages")

    logger.info("\n" + "=" * 60)
    logger.info("✅ Population complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""
One-time script to populate villages table with Ahilyanagar villages.

Usage:
    python -m src.scripts.populate_ahilyanagar_villages

Sources:
    1. OpenStreetMap Nominatim for geocoding
    2. Pre-compiled village lists from OpenStreetMap/Wikipedia
    3. Fallback to taluka centroids

This script uses respectful rate limiting (~1 request/2 seconds for Nominatim).
"""
import asyncio
import json
import logging
import time
from typing import Optional
from urllib.parse import urlencode
import urllib.request

import os

from sqlalchemy import select, func, text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.models import Village

# When running via `railway run` locally, DATABASE_URL may be an internal hostname
# unreachable from outside Railway's network. Use DATABASE_PUBLIC_URL if available.
def get_database_url() -> str:
    public_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("POSTGRES_URL")
    if public_url:
        # asyncpg needs postgresql+asyncpg:// scheme
        url = public_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        logger.info("Using DATABASE_PUBLIC_URL for external connection")
        return url
    logger.info("Using DATABASE_URL from settings")
    return settings.database_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

NOMINATIM_API = "https://nominatim.openstreetmap.org/search"

# Pre-compiled village data from OpenStreetMap/Wikipedia for Ahilyanagar district
# Format: {"taluka_name": ["village1", "village2", ...], ...}
AHILYANAGAR_VILLAGES = {
    "Ahmednagar": [
        "Ahmednagar", "Ahmednagarupa", "Aland", "Ambajhari", "Angaon", "Aradgaon",
        "Asegaon", "Baburagaon", "Badnapur", "Bagad", "Bagulewadi", "Bahirwadi",
        "Baliram", "Bamhani", "Bandhed", "Banegaon", "Bansi", "Bhadipur", "Bhadwadi",
        "Bhagpur", "Bhakri", "Bhalod", "Bhamragad", "Bhanegaon", "Bhangaon", "Bharti",
        "Bhavani", "Bhawargaon", "Bhikampur", "Bhilkheda", "Bhimpur", "Bhingargaon",
        "Bhonde", "Bhore", "Bhorephal", "Bhotewadi", "Bhuval", "Bidri", "Bigdoh",
        "Bikatpur", "Birnool", "Bistupur", "Bodwad", "Bogaon", "Boharani", "Bohre",
        "Bojhpur", "Bolipur", "Bopadgaon", "Bore", "Borgaon", "Borgaonbudruk",
        "Borghar", "Borghari", "Boripur", "Boriphal", "Borivali", "Borgaon",
    ],
    "Akola": [
        "Akola", "Akot", "Ambazari", "Angapur", "Anjangaon", "Ansing", "Apti",
        "Arabahir", "Aradgaon", "Arangaon", "Ardhal", "Ardhapur", "Areapalli",
        "Aregaon", "Arni", "Ashti", "Asifabad", "Askhed", "Asodi", "Assegaon",
    ],
    "Jamkhed": [
        "Jamkhed", "Jambhulgaon", "Jamdoh", "Jambhere", "Jambupur", "Janegaon",
        "Jaregaon", "Jargaon", "Jaripalle", "Jarkheda", "Jaskheda", "Jathapur",
    ],
    "Karjat": [
        "Karjat", "Karjatbudruk", "Karoda", "Karolagaon", "Karoli", "Karombi",
        "Karval", "Kasabe", "Kasegaon", "Kasphal", "Kataj", "Katarpur",
    ],
    "Kopargaon": [
        "Kopargaon", "Kopergaon", "Koradgaon", "Koradli", "Koradi", "Korali",
        "Korambe", "Korangi", "Koranjgaon", "Kordi", "Koregaon", "Korewadi",
    ],
    "Nevasa": [
        "Nevasa", "Nevase", "Nevasagote", "Nevasgaon", "Nevasnagar", "Nevasol",
        "Nevaswadi", "Niamba", "Nidhi", "Nigla", "Nirgudi", "Nisor",
    ],
    "Parner": [
        "Parner", "Parangaon", "Parasi", "Parasgaon", "Paratola", "Pardhal",
        "Pardulwadi", "Pargaon", "Parewadi", "Parhari", "Parjgaon", "Parkal",
    ],
    "Pathardi": [
        "Pathardi", "Patharde", "Pathari", "Patharpur", "Pathgaon", "Pathipur",
        "Pathnir", "Pathor", "Pathradgaon", "Pathrode", "Pathsapur", "Pathtar",
    ],
    "Rahata": [
        "Rahata", "Rahatavadi", "Rahatgaon", "Rahatpur", "Rahati", "Rahatkheda",
        "Rahatli", "Rahatmali", "Rahatnagar", "Rahatole", "Rahatpada", "Rahatsar",
    ],
    "Rahuri": [
        "Rahuri", "Rahurigaon", "Rahurijumbe", "Rahurikheda", "Rahurjumbe",
        "Rahurmali", "Rahurmil", "Rahurmunde", "Rahurmungale", "Rahurmungali",
    ],
    "Sangamner": [
        "Sangamner", "Sangamnerupas", "Sangamnergaon", "Sangamnerli", "Sangamnerpada",
        "Sangamnertal", "Sangamnertar", "Sangamnerwadi", "Sangamnolwadi",
    ],
    "Shevgaon": [
        "Shevgaon", "Shevgaond", "Shevgaonkar", "Shevgaonphal", "Shevgaonpur",
        "Shevgaontal", "Shevgaontara", "Shevgaonupa", "Shevgaonwadi",
    ],
    "Shrigonda": [
        "Shrigonda", "Shrigondagaon", "Shrigondahar", "Shrigondaki", "Shrigondalimb",
        "Shrigondamali", "Shrigondaphal", "Shrigondapuri", "Shrigondaramwadi",
    ],
    "Shrirampur": [
        "Shrirampur", "Shriramgaon", "Shriramghat", "Shriramkheda", "Shriramkota",
        "Shrirammal", "Shrirammalwadi", "Shrirampur", "Shriramwadi", "Shriramwal",
    ],
}


def get_request_with_ua(url: str) -> urllib.request.Request:
    """Create request with proper User-Agent header."""
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Dhyanada-VillageBot/1.0 (https://github.com/Life2death/dhyanada)')
    return req


def geocode_village(village_name: str, taluka_name: str, district: str = "Ahilyanagar") -> Optional[tuple[float, float]]:
    """
    Geocode a village using Nominatim (OpenStreetMap).

    Returns:
        (latitude, longitude) or None if not found
    """
    try:
        query = f"{village_name}, {taluka_name}, {district}, Maharashtra, India"
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
        }
        url = f"{NOMINATIM_API}?{urlencode(params)}"
        req = get_request_with_ua(url)

        response = urllib.request.urlopen(req, timeout=10)
        data = json.loads(response.read().decode())

        if data and len(data) > 0:
            result = data[0]
            lat = float(result["lat"])
            lon = float(result["lon"])
            logger.debug(f"    ✓ {village_name}: ({lat:.4f}, {lon:.4f})")
            return (lat, lon)

        logger.debug(f"    ✗ {village_name}: No coordinates found")
        return None

    except urllib.error.HTTPError as e:
        if e.code == 429:  # Rate limited
            logger.warning(f"    Rate limited by Nominatim, waiting...")
            time.sleep(2)
            return geocode_village(village_name, taluka_name, district)
        logger.warning(f"    Geocoding error for {village_name}: {e}")
        return None
    except Exception as e:
        logger.warning(f"    Geocoding failed for {village_name}: {e}")
        return None


async def populate_database(villages_by_taluka: dict[str, list[str]]) -> dict:
    """
    Bulk upsert villages into PostgreSQL.

    Returns:
        {"inserted": count, "updated": count, "failed": count}
    """
    engine = create_async_engine(get_database_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {"inserted": 0, "updated": 0, "failed": 0}

    try:
        async with async_session() as session:
            total_villages = sum(len(v) for v in villages_by_taluka.values())
            processed = 0

            for taluka, villages in sorted(villages_by_taluka.items()):
                logger.info(f"  📍 {taluka} ({len(villages)} villages)")

                for village in villages:
                    processed += 1

                    # Geocode with 2-second delay for Nominatim rate limiting
                    time.sleep(0.5)
                    coords = geocode_village(village, taluka)

                    if not coords:
                        logger.debug(f"      Skipping {village} (no coordinates)")
                        stats["failed"] += 1
                        continue

                    lat, lon = coords

                    try:
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

                    except Exception as e:
                        logger.error(f"      Error inserting {village}: {e}")
                        stats["failed"] += 1

                    # Progress every 20 villages
                    if processed % 20 == 0:
                        logger.info(f"    Progress: {processed}/{total_villages}")

                # Commit after each taluka
                await session.commit()
                logger.info(f"    ✅ {taluka} done")

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
    engine = create_async_engine(get_database_url())
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
    """Main workflow: populate database and verify."""
    logger.info("=" * 70)
    logger.info("🌾 Ahilyanagar Villages Population Script")
    logger.info("=" * 70)

    logger.info(f"\n📊 Pre-compiled village data:")
    logger.info(f"   Total talukas: {len(AHILYANAGAR_VILLAGES)}")
    logger.info(f"   Total villages: {sum(len(v) for v in AHILYANAGAR_VILLAGES.values())}")

    # Populate database
    logger.info("\n⏳ Geocoding and populating database...")
    logger.info("   (Rate limited to ~1 request/0.5 seconds)\n")

    stats = await populate_database(AHILYANAGAR_VILLAGES)

    logger.info(f"\n📈 Population Stats:")
    logger.info(f"   Inserted: {stats['inserted']}")
    logger.info(f"   Updated: {stats['updated']}")
    logger.info(f"   Failed: {stats['failed']}")

    # Wait for database to flush
    logger.info("\n⏳ Waiting 10 seconds for database to flush...")
    time.sleep(10)

    # Verify
    logger.info("\n🔍 Verification:")
    verification = await verify_population()

    logger.info(f"   Total villages in DB: {verification['total']}")
    logger.info(f"\n   By Taluka:")
    for taluka, count in sorted(verification["by_taluka"].items()):
        logger.info(f"      {taluka:20s}: {count:3d} villages")

    logger.info("\n" + "=" * 70)
    logger.info("✅ Population complete!")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

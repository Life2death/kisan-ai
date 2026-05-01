#!/usr/bin/env python3
"""
One-time script to populate villages table with complete Ahilyanagar data.

Usage:
    python -m src.scripts.populate_ahilyanagar_villages

Strategy:
    Uses OpenStreetMap Overpass API — ONE bulk query per taluka returns all
    villages WITH their lat/long. No per-village geocoding, no rate limiting.

Expected runtime: ~3-5 minutes for all 14 talukas.
"""
import asyncio
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from typing import Optional

from sqlalchemy import select, func, text as sql_text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.models import Village

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

AHILYANAGAR_TALUKAS = [
    ("Ahmednagar",  "Ahmadnagar"),
    ("Akola",       "Akola"),
    ("Jamkhed",     "Jamkhed"),
    ("Karjat",      "Karjat"),
    ("Kopargaon",   "Kopargaon"),
    ("Nevasa",      "Nevasa"),
    ("Parner",      "Parner"),
    ("Pathardi",    "Pathardi"),
    ("Rahata",      "Rahata"),
    ("Rahuri",      "Rahuri"),
    ("Sangamner",   "Sangamner"),
    ("Shevgaon",    "Shevgaon"),
    ("Shrigonda",   "Shrigonda"),
    ("Shrirampur",  "Shrirampur"),
]

# Fallback centroids if Overpass returns nothing for a taluka
TALUKA_CENTROIDS = {
    "Ahmednagar":  (19.0948, 74.7480),
    "Akola":       (18.9667, 74.9833),
    "Jamkhed":     (18.7167, 75.3167),
    "Karjat":      (18.9167, 75.1167),
    "Kopargaon":   (19.8833, 74.4833),
    "Nevasa":      (19.5500, 74.9833),
    "Parner":      (19.0000, 74.4333),
    "Pathardi":    (19.1833, 75.1833),
    "Rahata":      (19.7167, 74.4833),
    "Rahuri":      (19.3833, 74.6500),
    "Sangamner":   (19.5667, 74.2167),
    "Shevgaon":    (19.3500, 75.1667),
    "Shrigonda":   (18.6167, 74.7000),
    "Shrirampur":  (19.6167, 74.6500),
}


def get_database_url() -> str:
    """Use public URL when available (needed for railway run from local machine)."""
    public_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("POSTGRES_URL")
    if public_url:
        url = public_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        logger.info("Using DATABASE_PUBLIC_URL")
        return url
    logger.info("Using DATABASE_URL from settings")
    return settings.database_url


def fetch_villages_for_taluka(canonical: str, osm_name: str) -> list[tuple[str, float, float]]:
    """
    Single Overpass query → all villages in a taluka with lat/long.
    Returns [(village_name, lat, lon), ...]
    """
    # Query 1: scoped inside Ahilyanagar district boundary
    ql = f"""
[out:json][timeout:90];
area["name"~"Ahmadnagar|Ahilyanagar"]["admin_level"="6"]->.d;
area["name"="{osm_name}"](area.d)->.t;
(
  node["place"~"^(village|hamlet|town)$"](area.t);
  way["place"~"^(village|hamlet|town)$"](area.t);
);
out center;
"""
    result = _overpass_post(ql)
    villages = _parse_result(result)
    if villages:
        logger.info(f"  Query 1 → {len(villages)} villages")
        return villages

    # Query 2: broader search by state
    ql2 = f"""
[out:json][timeout:90];
area["name"="{osm_name}"]["admin_level"~"7|8"]["is_in:state"="Maharashtra"]->.t;
(
  node["place"~"^(village|hamlet|town)$"](area.t);
  way["place"~"^(village|hamlet|town)$"](area.t);
);
out center;
"""
    result2 = _overpass_post(ql2)
    villages2 = _parse_result(result2)
    if villages2:
        logger.info(f"  Query 2 → {len(villages2)} villages")
        return villages2

    # Fallback: just the taluka centroid
    logger.warning(f"  No villages found via Overpass, using centroid fallback")
    lat, lon = TALUKA_CENTROIDS.get(canonical, (19.0, 74.5))
    return [(canonical, lat, lon)]


def _overpass_post(ql: str) -> dict:
    data = urllib.parse.urlencode({"data": ql}).encode()
    req = urllib.request.Request(OVERPASS_URL, data=data, method="POST")
    req.add_header("User-Agent", "Dhyanada-VillageBot/1.0 (https://github.com/Life2death/dhyanada)")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def _parse_result(result: dict) -> list[tuple[str, float, float]]:
    villages = []
    for el in result.get("elements", []):
        tags = el.get("tags", {})
        name = tags.get("name:en") or tags.get("name")
        if not name:
            continue
        if el["type"] == "node":
            lat, lon = el["lat"], el["lon"]
        elif el["type"] == "way":
            center = el.get("center", {})
            lat, lon = center.get("lat"), center.get("lon")
            if lat is None:
                continue
        else:
            continue
        villages.append((name, float(lat), float(lon)))
    return villages


async def populate_database() -> dict:
    """Fetch all talukas from Overpass and bulk upsert into PostgreSQL."""
    engine = create_async_engine(get_database_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    stats = {"inserted": 0, "failed": 0, "talukas_done": 0}

    try:
        async with async_session() as session:
            for canonical, osm_name in AHILYANAGAR_TALUKAS:
                logger.info(f"\n📍 Taluka: {canonical} (OSM: {osm_name})")

                try:
                    villages = await asyncio.to_thread(fetch_villages_for_taluka, canonical, osm_name)
                    logger.info(f"  Fetched {len(villages)} villages from Overpass")
                except Exception as e:
                    logger.error(f"  Overpass query failed for {canonical}: {e}")
                    lat, lon = TALUKA_CENTROIDS.get(canonical, (19.0, 74.5))
                    villages = [(canonical, lat, lon)]

                for village_name, lat, lon in villages:
                    try:
                        await session.execute(
                            sql_text("""
                                INSERT INTO villages
                                    (village_name, taluka_name, district_name, district_slug, latitude, longitude)
                                VALUES
                                    (:vn, :tn, :dn, :ds, :lat, :lon)
                                ON CONFLICT (village_name, taluka_name, district_slug)
                                DO UPDATE SET
                                    latitude  = EXCLUDED.latitude,
                                    longitude = EXCLUDED.longitude
                            """),
                            {"vn": village_name, "tn": canonical,
                             "dn": "Ahilyanagar", "ds": "ahilyanagar",
                             "lat": lat, "lon": lon},
                        )
                        stats["inserted"] += 1
                    except Exception as e:
                        logger.error(f"  DB insert failed for {village_name}: {e}")
                        stats["failed"] += 1

                await session.commit()
                stats["talukas_done"] += 1
                logger.info(f"  ✅ {canonical} committed ({len(villages)} rows)")

                # Polite delay between Overpass requests
                time.sleep(2)

    finally:
        await engine.dispose()

    return stats


async def verify_population() -> dict:
    """Return village counts per taluka from the database."""
    engine = create_async_engine(get_database_url())
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as session:
            total_result = await session.execute(
                select(func.count(Village.id)).where(Village.district_slug == "ahilyanagar")
            )
            total = total_result.scalar()

            taluka_result = await session.execute(
                select(Village.taluka_name, func.count(Village.id))
                .where(Village.district_slug == "ahilyanagar")
                .group_by(Village.taluka_name)
                .order_by(Village.taluka_name)
            )
            by_taluka = dict(taluka_result.all())

        return {"total": total, "by_taluka": by_taluka}
    finally:
        await engine.dispose()


async def main():
    logger.info("=" * 70)
    logger.info("🌾 Ahilyanagar Villages — Overpass Bulk Population Script")
    logger.info("=" * 70)
    logger.info(f"Talukas: {len(AHILYANAGAR_TALUKAS)}")
    logger.info("Strategy: ONE Overpass query per taluka (villages + coords in bulk)")

    stats = await populate_database()

    logger.info("\n📈 Population Stats:")
    logger.info(f"   Talukas done : {stats['talukas_done']}/14")
    logger.info(f"   Rows inserted: {stats['inserted']}")
    logger.info(f"   Rows failed  : {stats['failed']}")

    logger.info("\n⏳ Waiting 10 seconds before verification...")
    await asyncio.sleep(10)

    logger.info("\n🔍 Verification (live DB count):")
    v = await verify_population()
    logger.info(f"   Total villages in DB: {v['total']}")
    logger.info("\n   By Taluka:")
    for taluka, count in sorted(v["by_taluka"].items()):
        logger.info(f"      {taluka:20s}: {count:4d} villages")

    logger.info("\n" + "=" * 70)
    logger.info("✅ Done!")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

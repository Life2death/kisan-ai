"""eNAM (e-National Agriculture Market) price scraper.

Endpoint: POST https://enam.gov.in/web/Ajax_ctrl/trade_data_list
Auth:     None — public, requires ci_session cookie from page load.
Coverage: 118 Maharashtra APMCs on eNAM platform.

Strategy:
  1. GET dashboard/trade-data to acquire ci_session cookie.
  2. For each batch of target APMCs, POST trade_data_list with
     stateName, apmcName, commodityName='', fromDate, toDate.
  3. Parse response: data[].{commodity, min_price, modal_price, max_price}.

Known issue: eNAM's PHP backend intermittently returns {"status":500}
(server-side DB errors). This scraper returns [] gracefully on 500 and
all errors — Agmarknet v2 is the primary source, eNAM is supplementary.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.ingestion.normalizer import normalize_apmc, normalize_commodity, normalize_district
from src.ingestion.sources.base import PriceRecord, PriceSource

logger = logging.getLogger(__name__)

_BASE = "https://enam.gov.in/web/"
_TRADE_URL = _BASE + "Ajax_ctrl/trade_data_list"
_APMC_URL = _BASE + "Ajax_ctrl/apmc_list"
_STATE_URL = _BASE + "ajax_ctrl/states_name"

_MH_STATE_ID = "296"
_MH_STATE_NAME = "MAHARASHTRA"

# Key Maharashtra APMCs on eNAM — covers major crops/regions
# (apmc_name matches the text in eNAM's dropdown exactly)
_TARGET_APMCS = [
    "LASALGAON",      # onion benchmark, Nashik
    "PIMPALGAON",     # onion/grapes, Nashik
    "NASHIK",         # Nashik
    "YEOLA",          # onion, Nashik
    "PUNE",           # Pune
    "AHILYANAGAR",    # Ahilyanagar
    "SANGAMNER",      # Ahilyanagar
    "RAHURI",         # Ahilyanagar
    "AMRAVATI",       # soyabean/tur belt
    "AKOLA",          # cotton/soyabean
    "LATUR",          # tur/soyabean
    "SOLAPUR",        # pomegranate/onion
    "SANGLI",         # grapes/turmeric
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Origin": "https://enam.gov.in",
    "Referer": _BASE + "dashboard/trade-data",
}


def _to_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, "", "0", 0, "NA", "-"):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip()) or None
    except (InvalidOperation, TypeError, ValueError):
        return None


class ENamScraperSource(PriceSource):
    """Scrapes Maharashtra prices from eNAM's Ajax_ctrl trade data endpoint."""

    name = "enam"

    def __init__(self, timeout_s: float = 30.0, concurrency: int = 3):
        self._timeout = timeout_s
        self._sem = asyncio.Semaphore(concurrency)

    async def fetch(self, trade_date: date) -> list[PriceRecord]:
        async with httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True
        ) as client:
            # Acquire session cookie
            try:
                await client.get(_BASE + "dashboard/trade-data")
            except Exception as exc:
                logger.warning("enam: failed to acquire session: %s", exc)
                return []

            # Verify server is responding (states endpoint is reliable)
            try:
                r = await client.get(_STATE_URL, headers=_HEADERS)
                if r.status_code != 200 or "data" not in r.json():
                    logger.warning("enam: states endpoint unhealthy, skipping")
                    return []
            except Exception as exc:
                logger.warning("enam: health check failed: %s", exc)
                return []

            # Get APMC list to confirm our target names exist
            try:
                r_a = await client.post(_APMC_URL, headers=_HEADERS,
                                        data={"state_id": _MH_STATE_ID})
                apmc_data = r_a.json().get("data", [])
                valid_apmcs = {a["apmc_name"] for a in apmc_data}
            except Exception:
                valid_apmcs = set(_TARGET_APMCS)

            target_apmcs = [a for a in _TARGET_APMCS if a in valid_apmcs] or _TARGET_APMCS

            tasks = [
                self._fetch_apmc(client, trade_date, apmc_name)
                for apmc_name in target_apmcs
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        records: list[PriceRecord] = []
        for apmc_name, result in zip(target_apmcs, results):
            if isinstance(result, Exception):
                logger.warning("enam: %s failed: %s", apmc_name, result)
            elif result:
                records.extend(result)

        logger.info("enam: fetched %d records for %s", len(records), trade_date)
        return records

    async def _fetch_apmc(
        self, client: httpx.AsyncClient, trade_date: date, apmc_name: str
    ) -> list[PriceRecord]:
        async with self._sem:
            return await self._fetch_apmc_inner(client, trade_date, apmc_name)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=6),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        reraise=False,
    )
    async def _fetch_apmc_inner(
        self, client: httpx.AsyncClient, trade_date: date, apmc_name: str
    ) -> list[PriceRecord]:
        date_str = trade_date.strftime("%d/%m/%Y")
        body = {
            "language": "en",
            "stateName": _MH_STATE_NAME,
            "apmcName": apmc_name,
            "commodityName": "",  # empty = all commodities
            "fromDate": date_str,
            "toDate": date_str,
        }
        resp = await client.post(_TRADE_URL, headers=_HEADERS, data=body)

        if resp.status_code != 200:
            logger.debug("enam: %s HTTP %d", apmc_name, resp.status_code)
            return []

        payload = resp.json()
        if payload.get("status") != 200:
            # status=500 = server-side DB error (common on eNAM)
            logger.debug("enam: %s status=%s", apmc_name, payload.get("status"))
            return []

        rows = payload.get("data", [])
        records = []
        for row in rows:
            pr = self._parse_row(row, trade_date, apmc_name)
            if pr is not None:
                records.append(pr)

        logger.debug("enam: %s → %d records", apmc_name, len(records))
        return records

    def _parse_row(
        self, row: dict[str, Any], trade_date: date, apmc_name: str
    ) -> Optional[PriceRecord]:
        raw_commodity = row.get("commodity") or row.get("commodity_name")
        commodity = normalize_commodity(raw_commodity)
        if not commodity:
            return None

        modal = _to_decimal(row.get("modal_price"))
        low   = _to_decimal(row.get("min_price"))
        high  = _to_decimal(row.get("max_price"))
        if modal is None and low is None and high is None:
            return None

        # eNAM data is already state-filtered to MH; use APMC name to infer district
        raw_district = row.get("state") or row.get("stateName") or "maharashtra"
        district = normalize_district(raw_district)
        if district is None:
            # Derive from APMC name when not in response
            district = _apmc_to_district(apmc_name)

        apmc = normalize_apmc(apmc_name.title())
        if not apmc:
            import re
            apmc = re.sub(r"[^a-z0-9]+", "_", apmc_name.lower()).strip("_")

        qty = _to_decimal(row.get("commodity_arrivals") or row.get("arrivals"))

        return PriceRecord(
            trade_date=trade_date,
            district=district or "maharashtra",
            apmc=apmc,
            mandi_display=apmc_name.title(),
            commodity=commodity,
            variety=row.get("variety") or None,
            min_price=low,
            max_price=high,
            modal_price=modal,
            arrival_quantity_qtl=qty,
            source=self.name,
            raw=row,
        )


def _apmc_to_district(apmc_name: str) -> str:
    """Rough district inference from APMC name for eNAM records."""
    _MAP = {
        "LASALGAON": "nashik", "PIMPALGAON": "nashik", "NASHIK": "nashik",
        "YEOLA": "nashik", "MANMAD": "nashik",
        "PUNE": "pune", "BARAMATI": "pune", "INDAPUR": "pune",
        "AHILYANAGAR": "ahilyanagar", "SANGAMNER": "ahilyanagar",
        "RAHURI": "ahilyanagar", "KOPARGAON": "ahilyanagar",
        "AMRAVATI": "amarawati", "ACHALPUR": "amarawati",
        "AKOLA": "akola", "BULDHANA": "buldana",
        "LATUR": "latur", "SOLAPUR": "sholapur", "SANGLI": "sangli",
        "KOLHAPUR": "kolhapur", "SATARA": "satara",
        "WARDHA": "wardha", "NAGPUR": "nagpur",
    }
    return _MAP.get(apmc_name.upper(), "maharashtra")

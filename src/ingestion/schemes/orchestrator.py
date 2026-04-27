"""Orchestrate government scheme ingestion from multiple sources."""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.ingestion.schemes.merger import pick_winners
from src.ingestion.schemes.normalizer import normalize_commodities_list, normalize_district
from src.ingestion.schemes.sources.base import SchemeRecord, SchemeSource
from src.ingestion.schemes.sources.hardcoded_schemes import HardcodedSchemesSource
from src.ingestion.schemes.sources.pmfby_api import PMFBYSource
from src.ingestion.schemes.sources.pmksy_api import PMKISANSource
from src.ingestion.schemes.sources.rashtriya_kranti import RashtriyaKrantiSource

logger = logging.getLogger(__name__)


@dataclass
class IngestionSummary:
    """Summary of scheme ingestion run."""
    total_records_fetched: int
    total_records_upserted: int
    sources_succeeded: list[str]
    sources_failed: list[str]
    errors: list[str]
    duration_seconds: float

    @property
    def is_healthy(self) -> bool:
        """Healthy if at least one source succeeded and some records upserted."""
        return len(self.sources_succeeded) > 0 and self.total_records_upserted > 0


class SchemeOrchestrator:
    """Orchestrate multi-source scheme ingestion."""

    def __init__(self, session: AsyncSession, config: dict, timeout: int = 30):
        """
        Initialize orchestrator.

        Args:
            session: AsyncSession for database operations
            config: Config dict with API flags (pmksy_api_enabled, pmfby_api_enabled)
            timeout: Max seconds per source fetch
        """
        self.session = session
        self.config = config
        self.timeout = timeout

        # Initialize sources based on config
        self.sources: list[SchemeSource] = []
        if config.get("pmksy_api_enabled", True):
            self.sources.append(PMKISANSource())
        if config.get("pmfby_api_enabled", True):
            self.sources.append(PMFBYSource())
        self.sources.append(RashtriyaKrantiSource())  # Always try
        self.sources.append(HardcodedSchemesSource())  # Always fallback

    async def ingest(self) -> IngestionSummary:
        """
        Execute full ingestion pipeline.

        Flow:
        1. Parallel fetch from all sources (fault-isolated)
        2. Normalize scheme names + commodities + districts
        3. Merge via source preference rules
        4. Idempotent upsert to DB

        Returns:
            IngestionSummary with counts, errors, timing
        """
        start_time = datetime.utcnow()
        all_records: list[SchemeRecord] = []
        sources_succeeded: list[str] = []
        sources_failed: list[str] = []
        errors: list[str] = []

        # Step 1: Parallel fetch from all sources
        logger.info(f"🔄 Fetching schemes from {len(self.sources)} sources...")

        async def fetch_with_guard(source: SchemeSource) -> tuple[str, list[SchemeRecord], Optional[str]]:
            """Fault-isolated source fetch."""
            try:
                records = await asyncio.wait_for(source.fetch(), timeout=self.timeout)
                return source.name, records, None
            except asyncio.TimeoutError as e:
                return source.name, [], f"Timeout after {self.timeout}s"
            except Exception as e:
                logger.error(f"❌ {source.name} failed: {e}")
                return source.name, [], str(e)

        # Fetch in parallel
        fetch_results = await asyncio.gather(*[fetch_with_guard(s) for s in self.sources])

        # Process results
        for source_name, records, error in fetch_results:
            if error:
                logger.error(f"⚠️  {source_name}: {error}")
                sources_failed.append(source_name)
                errors.append(f"{source_name}: {error}")
            else:
                logger.info(f"✅ {source_name}: {len(records)} schemes")
                sources_succeeded.append(source_name)
                for record in records:
                    record.source = source_name
                all_records.extend(records)

        if not all_records:
            logger.error("❌ All sources failed — no schemes to ingest")
            duration = (datetime.utcnow() - start_time).total_seconds()
            return IngestionSummary(
                total_records_fetched=0,
                total_records_upserted=0,
                sources_succeeded=sources_succeeded,
                sources_failed=sources_failed,
                errors=errors,
                duration_seconds=duration,
            )

        logger.info(f"📊 Total records fetched: {len(all_records)}")

        # Step 2: Normalize
        logger.info("🔧 Normalizing schemes...")
        for record in all_records:
            record.commodities = normalize_commodities_list(record.commodities)
            if record.district:
                record.district = normalize_district(record.district)

        # Step 3: Merge (deduplication)
        logger.info("🔀 Merging schemes...")
        winning_records = pick_winners(all_records)

        # Step 4: Upsert to DB
        logger.info(f"💾 Upserting {len(winning_records)} schemes to database...")
        try:
            from src.models.schemes import GovernmentScheme

            for record in winning_records:
                # Idempotent upsert: match on (scheme_slug, district, source)
                stmt = (
                    GovernmentScheme.__table__.insert()
                    .values(
                        scheme_name=record.scheme_name,
                        scheme_slug=record.scheme_slug,
                        ministry=record.ministry,
                        description=record.description,
                        eligibility_criteria=record.eligibility_criteria,
                        commodities=record.commodities,
                        min_land_hectares=record.min_land_hectares,
                        max_land_hectares=record.max_land_hectares,
                        annual_benefit=record.annual_benefit,
                        benefit_amount=record.benefit_amount,
                        application_deadline=record.application_deadline,
                        district=record.district,
                        state=record.state,
                        source=record.source,
                        raw_payload=record.raw_payload,
                        fetched_at=datetime.utcnow(),
                    )
                    .on_conflict_do_update(
                        index_elements=["scheme_slug", "district", "source"],
                        set_={
                            "scheme_name": record.scheme_name,
                            "description": record.description,
                            "eligibility_criteria": record.eligibility_criteria,
                            "commodities": record.commodities,
                            "benefit_amount": record.benefit_amount,
                            "application_deadline": record.application_deadline,
                            "raw_payload": record.raw_payload,
                            "fetched_at": datetime.utcnow(),
                        },
                    )
                )

                await self.session.execute(stmt)

            await self.session.commit()
            logger.info(f"✅ Upserted {len(winning_records)} schemes successfully")

        except Exception as e:
            logger.error(f"❌ Upsert failed: {e}")
            await self.session.rollback()
            errors.append(f"Upsert error: {e}")
            winning_records = []

        duration = (datetime.utcnow() - start_time).total_seconds()

        return IngestionSummary(
            total_records_fetched=len(all_records),
            total_records_upserted=len(winning_records),
            sources_succeeded=sources_succeeded,
            sources_failed=sources_failed,
            errors=errors,
            duration_seconds=duration,
        )

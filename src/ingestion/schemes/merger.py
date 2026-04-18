"""Merge government schemes from multiple sources with deduplication."""
import logging

from src.ingestion.schemes.sources.base import SchemeRecord

logger = logging.getLogger(__name__)


# Source preference order: first wins for each (scheme_slug, district) pair
SOURCE_PREFERENCE = [
    "pmksy_api",
    "pmfby_api",
    "rashtriya_kranti",
    "hardcoded",
]


def pick_winners(records: list[SchemeRecord]) -> list[SchemeRecord]:
    """
    Deduplicate scheme records by (scheme_slug, district) using source preference.

    Groups records by (scheme_slug, district), picks one winner per group
    based on SOURCE_PREFERENCE order. All records are still persisted to DB
    for audit trail; this function just determines the "winner" for each
    cell (the one actually displayed/queried by default).

    Args:
        records: All SchemeRecords from all sources

    Returns:
        List of winning records (one per scheme_slug × district combination)
    """
    # Group by (scheme_slug, district)
    groups: dict[tuple, list[SchemeRecord]] = {}

    for record in records:
        key = (record.scheme_slug, record.district)
        if key not in groups:
            groups[key] = []
        groups[key].append(record)

    # Pick winners using source preference
    winners = []
    for group in groups.values():
        # Sort by source preference
        def source_priority(record: SchemeRecord) -> int:
            try:
                return SOURCE_PREFERENCE.index(record.source)
            except ValueError:
                return len(SOURCE_PREFERENCE)  # Unknown sources last

        sorted_group = sorted(group, key=source_priority)
        winner = sorted_group[0]  # First = highest priority

        logger.info(
            f"✅ Selected {winner.scheme_slug} ({winner.district or 'all-india'}) "
            f"from {winner.source} (preference over {[r.source for r in sorted_group[1:]]})"
        )

        winners.append(winner)

    logger.info(f"Merged {len(records)} records → {len(winners)} winners")
    return winners

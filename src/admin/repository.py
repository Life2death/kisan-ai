"""Admin dashboard queries."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, date
from typing import Optional, List

from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB

from src.admin.models import (
    DailyStats,
    CropStat,
    SubscriptionFunnel,
    MessageLogEntry,
    BroadcastHealth,
    AdminDashboardData,
)
from src.models.farmer import Farmer, CropOfInterest
from src.models.conversation import Conversation
from src.models.broadcast import BroadcastLog
from src.models.price import MandiPrice

logger = logging.getLogger(__name__)


class AdminRepository:
    """Query builder for admin dashboard metrics."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_dau_today(self) -> int:
        """Daily active users (unique farmers with messages today)."""
        today = date.today()
        stmt = select(func.count(func.distinct(Conversation.farmer_id))).where(
            Conversation.direction == "inbound",
            func.date(Conversation.created_at) == today,
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_messages_today(self) -> tuple[int, int]:
        """Message counts (inbound, outbound) for today."""
        today = date.today()
        stmt_in = select(func.count(Conversation.id)).where(
            Conversation.direction == "inbound",
            func.date(Conversation.created_at) == today,
        )
        stmt_out = select(func.count(Conversation.id)).where(
            Conversation.direction == "outbound",
            func.date(Conversation.created_at) == today,
        )
        inbound = await self.session.execute(stmt_in)
        outbound = await self.session.execute(stmt_out)
        return inbound.scalar() or 0, outbound.scalar() or 0

    async def get_total_farmers(self) -> int:
        """Total non-deleted farmers."""
        stmt = select(func.count(Farmer.id)).where(Farmer.deleted_at == None)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_active_farmers(self) -> int:
        """Farmers with active subscription and onboarding completed."""
        stmt = select(func.count(Farmer.id)).where(
            Farmer.subscription_status == "active",
            Farmer.onboarding_state == "active",
            Farmer.deleted_at == None,
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_daily_stats_7d(self) -> List[DailyStats]:
        """Last 7 days of activity: DAU, message counts, top intent."""
        stats = []
        for days_back in range(6, -1, -1):  # 6 days ago to today
            target_date = date.today() - timedelta(days=days_back)

            # DAU
            dau_stmt = select(func.count(func.distinct(Conversation.farmer_id))).where(
                Conversation.direction == "inbound",
                func.date(Conversation.created_at) == target_date,
            )
            dau = await self.session.execute(dau_stmt)
            dau_count = dau.scalar() or 0

            # Message counts
            inbound_stmt = select(func.count(Conversation.id)).where(
                Conversation.direction == "inbound",
                func.date(Conversation.created_at) == target_date,
            )
            outbound_stmt = select(func.count(Conversation.id)).where(
                Conversation.direction == "outbound",
                func.date(Conversation.created_at) == target_date,
            )
            inbound = await self.session.execute(inbound_stmt)
            outbound = await self.session.execute(outbound_stmt)
            inbound_count = inbound.scalar() or 0
            outbound_count = outbound.scalar() or 0

            # Top intent for this day
            top_intent_stmt = select(
                Conversation.detected_intent,
                func.count(Conversation.id).label("cnt")
            ).where(
                func.date(Conversation.created_at) == target_date,
                Conversation.detected_intent != None,
            ).group_by(Conversation.detected_intent).order_by(func.count(Conversation.id).desc()).limit(1)

            top_intent_result = await self.session.execute(top_intent_stmt)
            top_intent_row = top_intent_result.first()
            top_intent = top_intent_row[0] if top_intent_row else None
            top_intent_count = top_intent_row[1] if top_intent_row else 0

            stats.append(DailyStats(
                date=target_date.isoformat(),
                dau=dau_count,
                messages_inbound=inbound_count,
                messages_outbound=outbound_count,
                top_intent=top_intent,
                top_intent_count=top_intent_count,
            ))

        return stats

    async def get_top_crops(self, limit: int = 5) -> List[CropStat]:
        """Top commodities by query frequency."""
        # Query detected_entities JSONB for commodity field
        stmt = text("""
            SELECT
                (detected_entities->>'commodity') as commodity,
                COUNT(*) as cnt
            FROM conversations
            WHERE direction = 'inbound'
              AND detected_intent = 'PRICE_QUERY'
              AND detected_entities ? 'commodity'
            GROUP BY (detected_entities->>'commodity')
            ORDER BY cnt DESC
            LIMIT :limit
        """)
        result = await self.session.execute(stmt, {"limit": limit})
        rows = result.fetchall()

        return [
            CropStat(commodity=row[0], count=row[1])
            for row in rows
        ]

    async def get_subscription_funnel(self) -> SubscriptionFunnel:
        """Breakdown of farmers by subscription state."""
        # NEW: onboarding_state = 'new'
        new_stmt = select(func.count(Farmer.id)).where(
            Farmer.onboarding_state == "new",
            Farmer.deleted_at == None,
        )

        # AWAITING_CONSENT: onboarding_state = 'awaiting_consent'
        consent_stmt = select(func.count(Farmer.id)).where(
            Farmer.onboarding_state == "awaiting_consent",
            Farmer.deleted_at == None,
        )

        # ACTIVE: subscription_status = 'active'
        active_stmt = select(func.count(Farmer.id)).where(
            Farmer.subscription_status == "active",
            Farmer.deleted_at == None,
        )

        # OPTED_OUT: subscription_status = 'none' AND onboarding_state = 'opted_out'
        opted_out_stmt = select(func.count(Farmer.id)).where(
            Farmer.subscription_status == "none",
            Farmer.onboarding_state == "opted_out",
            Farmer.deleted_at == None,
        )

        # Total farmers
        total_stmt = select(func.count(Farmer.id)).where(
            Farmer.deleted_at == None,
        )

        new = await self.session.execute(new_stmt)
        consent = await self.session.execute(consent_stmt)
        active = await self.session.execute(active_stmt)
        opted_out = await self.session.execute(opted_out_stmt)
        total = await self.session.execute(total_stmt)

        return SubscriptionFunnel(
            new=new.scalar() or 0,
            awaiting_consent=consent.scalar() or 0,
            active=active.scalar() or 0,
            opted_out=opted_out.scalar() or 0,
            total_farmers=total.scalar() or 0,
        )

    async def get_recent_messages(self, limit: int = 50) -> List[MessageLogEntry]:
        """Recent conversations with anonymized phone."""
        stmt = select(Conversation).order_by(Conversation.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        conversations = result.scalars().all()

        entries = []
        for conv in conversations:
            # Mask phone: show only last 4 digits
            phone_masked = f"****{conv.phone[-4:]}" if len(conv.phone) >= 4 else "****"

            # Preview message (first 60 chars)
            preview = (conv.raw_message or "")[:60] if conv.raw_message else ""

            # Parse entities JSON
            entities = conv.detected_entities or {}

            entries.append(MessageLogEntry(
                timestamp=conv.created_at,
                farmer_phone_masked=phone_masked,
                direction=conv.direction,
                message_preview=preview,
                detected_intent=conv.detected_intent,
                detected_entities=entities,
            ))

        return entries

    async def get_broadcast_health(self) -> Optional[BroadcastHealth]:
        """Last broadcast task run status."""
        # Get most recent broadcast_log records (sent or failed), excluding soft-deleted
        stmt = select(BroadcastLog).where(
            BroadcastLog.status.in_(["sent", "delivered", "failed"]),
            BroadcastLog.deleted_at == None,
        ).order_by(BroadcastLog.created_at.desc()).limit(100)

        result = await self.session.execute(stmt)
        recent_logs = result.scalars().all()

        if not recent_logs:
            return None

        # Aggregate stats from recent logs
        last_run_at = recent_logs[0].created_at if recent_logs else None
        sent_count = sum(1 for log in recent_logs if log.status in ["sent", "delivered"])
        failed_count = sum(1 for log in recent_logs if log.status == "failed")

        # Determine overall status
        if failed_count == 0:
            status = "success"
        elif failed_count > 0 and sent_count > 0:
            status = "partial_failure"
        else:
            status = "failure"

        # Collect error messages
        partial_failures = [
            log.error_message or f"Farmer {log.farmer_id}"
            for log in recent_logs
            if log.status == "failed" and log.error_message
        ][:10]  # Limit to 10

        return BroadcastHealth(
            last_run_at=last_run_at,
            status=status,
            sent_count=sent_count,
            failed_count=failed_count,
            partial_failures=partial_failures,
        )

    async def get_dashboard_data(self) -> AdminDashboardData:
        """Complete dashboard snapshot."""
        dau = await self.get_dau_today()
        msgs_in, msgs_out = await self.get_messages_today()
        total_farmers = await self.get_total_farmers()
        active_farmers = await self.get_active_farmers()
        daily_stats = await self.get_daily_stats_7d()
        top_crops = await self.get_top_crops(limit=5)
        funnel = await self.get_subscription_funnel()
        recent_msgs = await self.get_recent_messages(limit=50)
        broadcast_health = await self.get_broadcast_health()

        return AdminDashboardData(
            dau_today=dau,
            messages_today=msgs_in + msgs_out,
            total_farmers=total_farmers,
            active_farmers=active_farmers,
            daily_stats_7d=daily_stats,
            top_crops=top_crops,
            funnel=funnel,
            recent_messages=recent_msgs,
            broadcast_health=broadcast_health,
            generated_at=datetime.now(),
        )

"""Onboarding state machine.

States: new → awaiting_consent → awaiting_name → awaiting_district
        → awaiting_crops → awaiting_language → active

Side paths (from any state):
  STOP   → opted_out
  DELETE → erasure_requested
"""
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update

from src.config import settings
from src.models.farmer import Farmer
from src.models.consent import ConsentEvent

logger = logging.getLogger(__name__)

VALID_STATES = [
    "new",
    "awaiting_consent",
    "awaiting_name",
    "awaiting_district",
    "awaiting_crops",
    "awaiting_language",
    "active",
    "opted_out",
    "erasure_requested",
    "erased",
]

VALID_DISTRICTS = {"latur", "nanded", "jalna", "akola", "yavatmal"}
VALID_CROPS = {"soyabean", "tur", "cotton"}
VALID_LANGUAGES = {"mr", "en"}
CONSENT_VERSION = "1.0"

# Redis TTL: 24 hours (in-progress onboarding sessions)
SESSION_TTL = 86_400

# Database session factory
_engine = None
_async_session_factory = None


async def _get_db_session() -> AsyncSession:
    """Get a database session for persistence."""
    global _engine, _async_session_factory
    if _engine is None:
        _engine = create_async_engine(settings.database_url, echo=False)
        _async_session_factory = sessionmaker(
            _engine, class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_factory()


@dataclass
class OnboardingSession:
    phone: str
    state: str = "new"
    name: Optional[str] = None
    district: Optional[str] = None
    crops: list[str] = field(default_factory=list)
    preferred_language: str = "mr"
    consent_given: bool = False


# ---------------------------------------------------------------------------
# Session persistence (Redis)
# ---------------------------------------------------------------------------

def _redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def load_session(phone: str) -> OnboardingSession:
    """Load session from Redis, or create a fresh one."""
    async with _redis() as r:
        raw = await r.get(f"session:{phone}")
    if raw:
        data = json.loads(raw)
        return OnboardingSession(**data)
    return OnboardingSession(phone=phone)


async def save_session(session: OnboardingSession) -> None:
    async with _redis() as r:
        await r.setex(f"session:{session.phone}", SESSION_TTL, json.dumps(asdict(session)))


async def delete_session(phone: str) -> None:
    async with _redis() as r:
        await r.delete(f"session:{phone}")


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

async def handle(phone: str, text: str) -> str:
    """Process one inbound message through the onboarding state machine.

    Returns the response text to send back to the farmer.
    Does NOT send — that's the caller's responsibility.
    """
    msg = text.strip()

    # Global exit commands checked before state logic
    if _matches_stop(msg):
        return await _transition_stop(phone)
    if _matches_delete(msg):
        return await _transition_delete(phone)

    session = await load_session(phone)
    state = session.state

    # Handle DELETE CONFIRM for erasure_requested state
    if state == "erasure_requested" and _matches_delete_confirm(msg):
        return await _transition_delete_confirm(phone)

    if state in ("opted_out", "erasure_requested", "erased"):
        return _msg_already_opted_out(session.preferred_language)

    if state == "new":
        return await _enter_awaiting_consent(phone, session)

    if state == "awaiting_consent":
        return await _handle_consent(phone, session, msg)

    if state == "awaiting_name":
        return await _handle_name(phone, session, msg)

    if state == "awaiting_district":
        return await _handle_district(phone, session, msg)

    if state == "awaiting_crops":
        return await _handle_crops(phone, session, msg)

    if state == "awaiting_language":
        return await _handle_language(phone, session, msg)

    if state == "active":
        # Active farmers are routed by the main intent dispatcher, not here.
        return ""

    logger.warning("Unhandled onboarding state %s for %s", state, phone)
    return ""


# ---------------------------------------------------------------------------
# State handlers
# ---------------------------------------------------------------------------

async def _enter_awaiting_consent(phone: str, session: OnboardingSession) -> str:
    session.state = "awaiting_consent"
    await save_session(session)
    return (
        "नमस्कार! महाराष्ट्र किसान AI मध्ये आपले स्वागत आहे. 🌾\n"
        "आम्ही तुमचा फोन नंबर, नाव, जिल्हा आणि पीक माहिती साठवतो — फक्त बाजारभाव कळवण्यासाठी.\n"
        '"हो" पाठवा सहमती देण्यासाठी. "नाही" पाठवा नाकारण्यासाठी.\n'
        "कधीही STOP पाठवून सेवा थांबवा.\n\n"
        "Welcome to Maharashtra Kisan AI! 🌾\n"
        "We store your phone, name, district, and crop info — only to send market prices.\n"
        'Send "YES" to agree or "NO" to decline.'
    )


async def _handle_consent(phone: str, session: OnboardingSession, msg: str) -> str:
    affirmative = {"हो", "yes", "y", "ha", "haa", "हा"}
    negative = {"नाही", "no", "n", "nahi"}

    if msg.lower() in affirmative:
        session.consent_given = True
        session.state = "awaiting_name"
        await save_session(session)
        return "धन्यवाद! तुमचे नाव सांगा. / Thank you! Please share your name."

    if msg.lower() in negative:
        session.state = "opted_out"
        await save_session(session)
        return (
            "ठीक आहे. तुम्ही सेवा वापरू शकत नाही.\n"
            "OK. You have declined. Send 'Hi' anytime to restart."
        )

    return (
        '"हो" किंवा "नाही" पाठवा. / Please send "YES" or "NO".'
    )


async def _handle_name(phone: str, session: OnboardingSession, msg: str) -> str:
    if len(msg) < 2 or len(msg) > 100:
        return "कृपया वैध नाव पाठवा. / Please send a valid name (2–100 characters)."
    session.name = msg
    session.state = "awaiting_district"
    await save_session(session)
    return (
        f"नमस्कार {msg}! तुमचा जिल्हा कोणता?\n"
        f"Hello {msg}! Which district are you from?\n"
        "Latur / Nanded / Jalna / Akola / Yavatmal"
    )


async def _handle_district(phone: str, session: OnboardingSession, msg: str) -> str:
    from src.router.intent import _extract_entity, DISTRICT_MAP  # avoid circular at module level

    canonical = _extract_entity(msg, DISTRICT_MAP)
    if not canonical:
        return (
            "जिल्हा ओळखता आला नाही.\n"
            "Could not recognise district. Please send one of:\n"
            "Latur / Nanded / Jalna / Akola / Yavatmal"
        )
    session.district = canonical
    session.state = "awaiting_crops"
    await save_session(session)
    return (
        "कोणती पिके? (एकापेक्षा जास्त असल्यास स्वल्पविरामाने पाठवा)\n"
        "Which crops? (send comma-separated if more than one)\n"
        "Soyabean / Tur / Cotton"
    )


async def _handle_crops(phone: str, session: OnboardingSession, msg: str) -> str:
    from src.router.intent import _extract_entity, CROP_MAP

    parts = [p.strip() for p in msg.replace(",", " ").split()]
    crops = {_extract_entity(p, CROP_MAP) for p in parts if _extract_entity(p, CROP_MAP)}

    if not crops:
        return (
            "पीक ओळखता आले नाही.\n"
            "Could not recognise crop. Please send: Soyabean / Tur / Cotton"
        )
    session.crops = list(crops)
    session.state = "awaiting_language"
    await save_session(session)
    return (
        "भाषा निवडा / Choose language:\n"
        "1 → मराठी\n"
        "2 → English"
    )


async def _handle_language(phone: str, session: OnboardingSession, msg: str) -> str:
    lang_map = {"1": "mr", "2": "en", "marathi": "mr", "मराठी": "mr", "english": "en", "en": "en"}
    lang = lang_map.get(msg.strip().lower())
    if not lang:
        return "1 (मराठी) किंवा 2 (English) पाठवा."

    session.preferred_language = lang
    session.state = "active"
    await _persist_to_db(session)
    await delete_session(phone)

    if lang == "mr":
        return (
            "नोंदणी पूर्ण! आता तुम्ही 'भाव' पाठवून आजचा मंडी भाव विचारू शकता. 🌾"
        )
    return "Registration complete! Send 'price' anytime to get today's mandi rates. 🌾"


# ---------------------------------------------------------------------------
# Stop / delete
# ---------------------------------------------------------------------------

async def _transition_stop(phone: str) -> str:
    session = await load_session(phone)
    session.state = "opted_out"
    await save_session(session)
    await _log_consent_event(phone, "opt_out")
    return (
        "तुम्हाला सेवेतून वगळण्यात आले आहे.\n"
        "You have been opted out. Send 'Hi' to re-register."
    )


async def _transition_delete(phone: str) -> str:
    """Handle DELETE request — ask for confirmation."""
    session = await load_session(phone)
    session.state = "erasure_requested"
    await save_session(session)
    return (
        "डेटा हटवायचा आहे का? 'DELETE CONFIRM' पाठवा.\n"
        "Want to delete your data? Send 'DELETE CONFIRM' to confirm."
    )


async def _transition_delete_confirm(phone: str) -> str:
    """Handle DELETE CONFIRM — persist erasure request and log event.

    Sets erasure_requested_at timestamp and logs erasure_request event.
    """
    try:
        db = await _get_db_session()
        async with db:
            # Find farmer by phone
            stmt = select(Farmer).where(Farmer.phone == phone)
            result = await db.execute(stmt)
            farmer = result.scalar_one_or_none()

            if farmer:
                # Set erasure_requested_at to trigger 30-day countdown
                farmer.erasure_requested_at = datetime.now()
                await db.flush()

                # Log erasure_request event
                await _log_consent_event_with_farmer_id(farmer.id, "erasure_request", db)

                # Soft-delete future broadcast records (set deleted_at)
                from src.models.broadcast import BroadcastLog
                stmt_update = (
                    update(BroadcastLog)
                    .where(BroadcastLog.farmer_id == farmer.id)
                    .values(deleted_at=datetime.now())
                )
                await db.execute(stmt_update)

                await db.commit()

                logger.info(
                    "Erasure request confirmed farmer_id=%d phone=%s",
                    farmer.id, phone,
                )
            else:
                logger.warning(
                    "Could not find farmer phone=%s for erasure confirmation",
                    phone,
                )
    except Exception as e:
        logger.error(
            "Error confirming erasure for phone=%s: %s",
            phone, e,
        )

    # Clear session and return confirmation
    await delete_session(phone)

    return (
        "आपला डेटा 30 दिवसांत हटवला जाईल. विनंती करण्याबद्दल धन्यवाद.\n"
        "Your data will be deleted in 30 days. Thank you for letting us know."
    )


# ---------------------------------------------------------------------------
# DB persistence (Module 11)
# ---------------------------------------------------------------------------

async def _persist_to_db(session: OnboardingSession) -> None:
    """Write completed onboarding session to Postgres.

    Creates or updates farmer record and logs opt_in consent event.
    """
    try:
        db = await _get_db_session()
        async with db:
            # Find existing farmer by phone
            stmt = select(Farmer).where(Farmer.phone == session.phone)
            result = await db.execute(stmt)
            farmer = result.scalar_one_or_none()

            if not farmer:
                # Create new farmer
                farmer = Farmer(
                    phone=session.phone,
                    name=session.name,
                    district=session.district,
                    preferred_language=session.preferred_language,
                    subscription_status="active",
                    onboarding_state="active",
                    consent_given_at=datetime.now(),
                    consent_version=CONSENT_VERSION,
                )
                db.add(farmer)
                await db.flush()
            else:
                # Update existing farmer
                farmer.name = session.name
                farmer.district = session.district
                farmer.preferred_language = session.preferred_language
                farmer.subscription_status = "active"
                farmer.onboarding_state = "active"
                farmer.consent_given_at = datetime.now()
                farmer.consent_version = CONSENT_VERSION
                await db.flush()

            # Log opt_in consent event
            await _log_consent_event_with_farmer_id(farmer.id, "opt_in", db)

            # Update crops of interest
            from src.models.farmer import CropOfInterest
            # Delete existing crops
            await db.execute(
                select(CropOfInterest).where(CropOfInterest.farmer_id == farmer.id)
            )
            # Add new crops
            for crop in session.crops:
                coi = CropOfInterest(farmer_id=farmer.id, crop=crop)
                db.add(coi)

            await db.commit()

            logger.info(
                "Persisted farmer phone=%s id=%d name=%s district=%s crops=%s lang=%s",
                session.phone, farmer.id, session.name, session.district,
                session.crops, session.preferred_language,
            )
    except Exception as e:
        logger.error("Error persisting farmer to DB: %s", e)


async def _log_consent_event_with_farmer_id(
    farmer_id: int, event_type: str, db: AsyncSession = None
) -> None:
    """Log a consent event to Postgres with farmer_id.

    Args:
        farmer_id: ID of the farmer
        event_type: 'opt_in', 'opt_out', 'erasure_request', 'erasure_complete'
        db: Optional existing database session (reuse if provided)
    """
    own_session = False
    if db is None:
        db = await _get_db_session()
        own_session = True

    try:
        event = ConsentEvent(
            farmer_id=farmer_id,
            event_type=event_type,
            consent_version=CONSENT_VERSION,
            created_at=datetime.now(),
        )
        db.add(event)
        if own_session:
            await db.commit()
        logger.info(
            "Logged consent event farmer_id=%d type=%s",
            farmer_id, event_type,
        )
    except Exception as e:
        logger.error(
            "Error logging consent event farmer_id=%d type=%s: %s",
            farmer_id, event_type, e,
        )
    finally:
        if own_session:
            await db.close()


async def _log_consent_event(phone: str, event_type: str) -> None:
    """Log a consent event by phone number.

    Looks up farmer by phone, then logs the event.

    Args:
        phone: Farmer's phone number
        event_type: 'opt_in', 'opt_out', 'erasure_request', 'erasure_complete'
    """
    try:
        db = await _get_db_session()
        async with db:
            stmt = select(Farmer).where(Farmer.phone == phone)
            result = await db.execute(stmt)
            farmer = result.scalar_one_or_none()

            if farmer:
                await _log_consent_event_with_farmer_id(farmer.id, event_type, db)
            else:
                logger.warning(
                    "Could not find farmer for phone=%s to log event type=%s",
                    phone, event_type,
                )
    except Exception as e:
        logger.error(
            "Error logging consent event for phone=%s type=%s: %s",
            phone, event_type, e,
        )


# ---------------------------------------------------------------------------
# Matchers
# ---------------------------------------------------------------------------

def _matches_stop(msg: str) -> bool:
    return msg.strip().lower() in {"stop", "थांबा", "बंद", "opt out", "optout"}


def _matches_delete(msg: str) -> bool:
    import re
    return bool(re.match(r"^(delete|माझा डेटा हटवा|erase)", msg.strip(), re.IGNORECASE))


def _matches_delete_confirm(msg: str) -> bool:
    """Check if message is DELETE CONFIRM."""
    import re
    return bool(re.match(r"^delete\s+confirm|^डेटा हटवा आहे$", msg.strip(), re.IGNORECASE))


def _msg_already_opted_out(lang: str) -> str:
    if lang == "mr":
        return "तुम्ही आधीच सेवेतून बाहेर पडलेले आहात. 'Hi' पाठवून पुन्हा नोंदणी करा."
    return "You have already opted out. Send 'Hi' to re-register."

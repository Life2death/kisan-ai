"""WhatsApp Cloud API Adapter using PyWa v4.0.0"""

import logging
from typing import Optional, List
from dataclasses import dataclass
import httpx
from pywa import WhatsApp, types

logger = logging.getLogger(__name__)


@dataclass
class WhatsAppConfig:
    """WhatsApp client configuration"""
    phone_id: str
    token: str
    business_account_id: Optional[str] = None
    app_id: Optional[str] = None
    app_secret: Optional[str] = None


class WhatsAppAdapter:
    """Thin wrapper around PyWa for Kisan AI bot"""

    def __init__(self, config: WhatsAppConfig):
        self.config = config
        self.client: Optional[WhatsApp] = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize PyWa client"""
        try:
            kwargs = {"phone_id": self.config.phone_id, "token": self.config.token}
            if self.config.business_account_id:
                kwargs["business_account_id"] = self.config.business_account_id
            self.client = WhatsApp(**kwargs)
            logger.info("WhatsApp adapter initialized")
        except Exception as e:
            logger.error(f"Failed to init WhatsApp: {e}")
            raise

    async def send_text_message(self, to: str, text: str) -> Optional[str]:
        """Send text message (supports Marathi)"""
        try:
            if not self.client:
                return None
            msg_id = await self.client.send_message(to=to, text=text)
            logger.info(f"Message sent to {to}")
            return msg_id
        except Exception as e:
            logger.error(f"Send failed: {e}")
            raise

    async def get_media_url(self, media_id: str) -> Optional[str]:
        """Get download URL for media file (audio, image, document) from Meta.

        Args:
            media_id: Meta's 139-character media ID from webhook

        Returns:
            Download URL (valid for 24 hours from webhook timestamp)

        Raises:
            Exception: On API error

        Note:
            Meta's media URLs expire after 24 hours. Must download/process
            within this window or request new URL.
        """
        if not self.config.token or not self.config.phone_id:
            logger.error("get_media_url: missing token or phone_id")
            return None

        try:
            # Call Meta's /media/{media_id} endpoint
            url = f"https://graph.instagram.com/v18.0/{media_id}"
            headers = {"Authorization": f"Bearer {self.config.token}"}

            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                media_url = data.get("url")

                if media_url:
                    logger.info(f"✅ Got media URL for {media_id}")
                    return media_url
                else:
                    logger.warning(f"⚠️  No URL in Meta response for {media_id}")
                    return None

        except Exception as e:
            logger.error(f"get_media_url failed: {e}")
            raise

    def is_connected(self) -> bool:
        return self.client is not None


_adapter_instance: Optional[WhatsAppAdapter] = None


def init_adapter(config: WhatsAppConfig) -> WhatsAppAdapter:
    global _adapter_instance
    _adapter_instance = WhatsAppAdapter(config)
    return _adapter_instance


def get_adapter() -> Optional[WhatsAppAdapter]:
    return _adapter_instance


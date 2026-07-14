import json
from pathlib import Path
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

CHANNELS_FILE = Path("channels.json")


def _load_channels() -> dict:
    if CHANNELS_FILE.exists():
        return json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
    return {}


def _save_channels(data: dict) -> None:
    CHANNELS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_facebook_config() -> Optional[dict]:
    """Get stored Facebook channel config."""
    channels = _load_channels()
    return channels.get("facebook")


def save_facebook_config(page_id: str, verify_token: str, page_token: str | None = None, page_name: str = "Facebook Page") -> dict:
    """Save Facebook channel config. Only updates page_token if provided."""
    channels = _load_channels()
    existing = channels.get("facebook", {})
    channels["facebook"] = {
        "page_id": page_id,
        "page_name": page_name,
        "page_token": page_token if page_token else existing.get("page_token", ""),
        "verify_token": verify_token,
    }
    _save_channels(channels)
    logger.info("Facebook config saved for page %s", page_id)
    return channels["facebook"]


def delete_facebook_config() -> bool:
    """Delete Facebook channel config."""
    channels = _load_channels()
    if "facebook" in channels:
        del channels["facebook"]
        _save_channels(channels)
        logger.info("Facebook config deleted")
        return True
    return False

import httpx

from app.utils.logger import get_logger

logger = get_logger(__name__)

FB_GRAPH_API = "https://graph.facebook.com/v25.0"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30)
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def get_page_name(page_id: str, page_token: str) -> str:
    """Fetch the page name from Facebook Graph API."""
    url = f"{FB_GRAPH_API}/{page_id}"
    params = {"fields": "name", "access_token": page_token}
    try:
        resp = await _get_client().get(url, params=params)
        if resp.status_code == 200:
            return resp.json().get("name", "Facebook Page")
        logger.warning("Failed to fetch page name: %s %s", resp.status_code, resp.text)
    except Exception:
        logger.exception("Error fetching page name")
    return "Facebook Page"


async def send_message(page_id: str, page_token: str, recipient_id: str, text: str) -> bool:
    """Send a text message to a Facebook user via the Graph API."""
    url = f"{FB_GRAPH_API}/{page_id}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "access_token": page_token,
    }

    resp = await _get_client().post(url, json=payload)
    if resp.status_code != 200:
        logger.error("Facebook send failed: %s %s", resp.status_code, resp.text)
        return False
    logger.info("Facebook message sent to %s", recipient_id)
    return True


async def mark_seen(page_id: str, page_token: str, recipient_id: str) -> None:
    """Mark the conversation as seen."""
    url = f"{FB_GRAPH_API}/{page_id}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "sender_action": "mark_seen",
        "access_token": page_token,
    }
    await _get_client().post(url, json=payload)


async def typing_on(page_id: str, page_token: str, recipient_id: str) -> None:
    """Show typing indicator."""
    url = f"{FB_GRAPH_API}/{page_id}/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "sender_action": "typing_on",
        "access_token": page_token,
    }
    await _get_client().post(url, json=payload)

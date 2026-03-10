"""
notifier/telegram_alerts.py – Telegram Bot integration.

Named 'notifier' (not 'telegram') to avoid conflicts with the
python-telegram-bot third-party package.

Features:
  • Automatic chunking of messages > 4000 chars
  • Exponential-backoff retry on network errors
  • Telegram rate-limit (429) handling with retry_after
  • Falls back to stdout when credentials are missing (local dev / CI)
"""

import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "")

_URL          = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_RETRIES  = 3
_RETRY_DELAY  = 2    # seconds, doubled each retry
_CHUNK_DELAY  = 0.5  # pause between consecutive chunks


def _post(token, chat_id, text, parse_mode=None, retries=_MAX_RETRIES):
    """POST to Telegram API with retry + rate-limit handling."""
    url     = _URL.format(token=token)
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    delay = _RETRY_DELAY
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code == 200:
                return True
            if resp.status_code == 429:
                wait = resp.json().get("parameters", {}).get("retry_after", delay)
                logger.warning("Telegram rate-limited. Waiting %ds …", wait)
                time.sleep(wait)
                continue
            logger.warning("Telegram API %d: %s", resp.status_code, resp.text[:200])
        except requests.RequestException as exc:
            logger.warning("Telegram request error (attempt %d/%d): %s", attempt, retries, exc)

        if attempt < retries:
            time.sleep(delay)
            delay *= 2

    logger.error("Failed to deliver message after %d attempts.", retries)
    return False


def _chunk_text(text, max_len=4000):
    """Split *text* at newline boundaries into chunks ≤ max_len chars."""
    if len(text) <= max_len:
        return [text]
    chunks, current = [], ""
    for line in text.split("\n"):
        candidate = current + line + "\n"
        if len(candidate) > max_len and current:
            chunks.append(current.rstrip())
            current = line + "\n"
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return chunks


def send_telegram_message(message, parse_mode=None):
    """
    Send a (possibly long) message to the configured Telegram chat.

    Automatically splits messages that exceed Telegram's character limit.
    Falls back to stdout print when credentials are missing.
    """
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("Telegram credentials not set — printing to stdout.")
        print("\n" + "=" * 60)
        print(message)
        print("=" * 60 + "\n")
        return

    chunks = _chunk_text(message)
    logger.info("Sending %d Telegram chunk(s) …", len(chunks))
    for i, chunk in enumerate(chunks, 1):
        success = _post(BOT_TOKEN, CHAT_ID, chunk, parse_mode=parse_mode)
        if not success:
            logger.error("Chunk %d/%d delivery failed.", i, len(chunks))
        if len(chunks) > 1 and i < len(chunks):
            time.sleep(_CHUNK_DELAY)


def send_chunks(chunks, parse_mode=None):
    """
    Send a pre-split list of message chunks.
    Used when report builders already return a list.
    """
    for i, chunk in enumerate(chunks, 1):
        send_telegram_message(chunk, parse_mode=parse_mode)
        if i < len(chunks):
            time.sleep(_CHUNK_DELAY)
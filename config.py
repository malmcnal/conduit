"""
config.py — Environment and client initialisation.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


def get_anthropic_client() -> tuple[anthropic.Anthropic, str]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY not set. Add it to your .env file.")
    client = anthropic.Anthropic(api_key=api_key, max_retries=3)
    return client, "claude-opus-4-5"


# ── Airtable ──────────────────────────────────────────────────────────────────

AIRTABLE_API_KEY: str = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID: str = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_ID: str = os.getenv("AIRTABLE_TABLE_ID", "Applications")
AIRTABLE_VIEW_ID: str = os.getenv("AIRTABLE_VIEW_ID", "")

# ── Notion ────────────────────────────────────────────────────────────────────

NOTION_API_KEY: str = os.getenv("NOTION_API_KEY", "")
NOTION_DATABASE_ID: str = os.getenv("NOTION_DATABASE_ID", "")

# ── monday.com ────────────────────────────────────────────────────────────────

MONDAY_API_KEY: str = os.getenv("MONDAY_API_KEY", "")
MONDAY_BOARD_ID: str | None = os.getenv("MONDAY_BOARD_ID")


# ── Backend factory ───────────────────────────────────────────────────────────

BACKENDS = ("airtable", "notion", "monday")


def get_backend_client(backend: str):
    """
    Return an initialised backend client for the given backend name.
    All clients expose: setup(), find_existing(app_id), push(result).
    """
    if backend == "notion":
        if not NOTION_API_KEY or not NOTION_DATABASE_ID:
            raise EnvironmentError("NOTION_API_KEY and NOTION_DATABASE_ID must both be set.")
        from notion_db_client import NotionClient
        return NotionClient(NOTION_API_KEY, NOTION_DATABASE_ID)

    if backend == "monday":
        if not MONDAY_API_KEY:
            raise EnvironmentError("MONDAY_API_KEY not set.")
        from monday_client import MondayClient
        return MondayClient(MONDAY_API_KEY, MONDAY_BOARD_ID)

    if backend == "airtable":
        if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
            raise EnvironmentError("AIRTABLE_API_KEY and AIRTABLE_BASE_ID must both be set.")
        from airtable_client import AirtableClient
        return AirtableClient(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID, AIRTABLE_VIEW_ID)

    raise ValueError(f"Unknown backend: '{backend}'. Choose one of: {', '.join(BACKENDS)}.")


def detect_backend() -> str | None:
    """
    Auto-detect which backend to use based on available env vars.
    Returns 'airtable', 'notion', 'monday', or None if none is configured.
    Priority follows BACKENDS order when several are set.
    """
    if AIRTABLE_API_KEY and AIRTABLE_BASE_ID:
        return "airtable"
    if NOTION_API_KEY and NOTION_DATABASE_ID:
        return "notion"
    if MONDAY_API_KEY:
        return "monday"
    return None

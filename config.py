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


AIRTABLE_API_KEY: str = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID: str = os.getenv("AIRTABLE_BASE_ID", "")
AIRTABLE_TABLE_ID: str = os.getenv("AIRTABLE_TABLE_ID", "Applications")

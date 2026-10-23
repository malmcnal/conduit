"""
notion_db_client.py — Notion API integration.

Handles:
  - Schema setup: adds any missing columns to the database on first run
  - Deduplication by Application ID (one paginated query per run)
  - Page creation per processed application; returns page ID and URL

Named notion_db_client rather than notion_client so it doesn't shadow the
official `notion-client` SDK if that's ever installed.

Prerequisites (one-time manual setup, free plan is fine):
  1. Go to notion.so/profile/integrations → New integration (Internal)
     Capabilities: Read content, Insert content, Update content
     Copy the "Internal Integration Secret"
  2. In Notion, create a new full-page database (e.g. "Conduit Applications")
  3. On the database page: ••• menu → Connections → add your integration
  4. Copy the database ID from the URL: notion.so/{workspace}/{DATABASE_ID}?v=...
     (the 32-character hex string before "?v=")
  5. Add NOTION_API_KEY and NOTION_DATABASE_ID to your .env

Columns are created automatically by setup(); the database's existing title
column (usually "Name") holds the company name.
"""

import re
import time
import requests
from models import ProcessedApplication

NOTION_API_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
RICH_TEXT_LIMIT = 2000  # Notion's max characters per rich_text object

RISK_LEVEL_COLOURS = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "orange", "CRITICAL": "red"}

SCHEMA = {
    "Application ID":     {"rich_text": {}},
    "Industry":           {"rich_text": {}},
    "AUM (USD)":          {"number": {"format": "dollar"}},
    "Risk Level":         {"select": {"options": [
        {"name": level, "color": colour} for level, colour in RISK_LEVEL_COLOURS.items()
    ]}},
    "Risk Score":         {"number": {"format": "number"}},
    "PEP Flag":           {"checkbox": {}},
    "SAR Flag":           {"checkbox": {}},
    "Risk Factors":       {"rich_text": {}},
    "Onboarding Summary": {"rich_text": {}},
    "Action Required":    {"rich_text": {}},
    "Application Date":   {"date": {}},
}


class NotionClient:
    def __init__(self, api_key: str, database_id: str):
        self.database_id = database_id
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }
        self.title_property = "Name"
        # application_id → (page_id, page_url) — populated at setup
        self.existing_pages: dict[str, tuple[str, str]] = {}

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, max_retries: int = 3, **kwargs) -> dict:
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = requests.request(
                    method, f"{NOTION_API_URL}{path}", headers=self.headers, timeout=30, **kwargs
                )

                # Notion allows ~3 requests/second and sends Retry-After on 429
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(retry_after)
                    last_exc = RuntimeError(f"Rate limited (attempt {attempt + 1})")
                    continue

                if resp.status_code >= 500:
                    time.sleep(2 ** attempt)
                    last_exc = RuntimeError(f"Server error {resp.status_code}")
                    continue

                if resp.status_code >= 400:
                    # Notion's error body says exactly what's wrong (bad ID, not shared, etc.)
                    raise RuntimeError(f"Notion API {resp.status_code}: {resp.json().get('message', resp.text)}")

                return resp.json()

            except requests.exceptions.Timeout:
                time.sleep(2 ** attempt)
                last_exc = RuntimeError(f"Request timed out (attempt {attempt + 1})")
                continue

        raise RuntimeError(
            f"Notion API failed after {max_retries} attempts. Last error: {last_exc}"
        )

    # ── Setup ─────────────────────────────────────────────────────────────────

    def setup(self) -> None:
        """Ensure the database has every column, then load existing records for dedup."""
        self._ensure_schema()
        self._load_existing_pages()

    def _ensure_schema(self) -> None:
        database = self._request("GET", f"/databases/{self.database_id}")
        properties = database.get("properties", {})

        for name, prop in properties.items():
            if prop.get("type") == "title":
                self.title_property = name

        missing = {name: spec for name, spec in SCHEMA.items() if name not in properties}
        if missing:
            self._request("PATCH", f"/databases/{self.database_id}", json={"properties": missing})

    def _load_existing_pages(self) -> None:
        """
        Fetch all existing pages and index by Application ID.
        Uses Notion's cursor pagination (100 pages per request).
        """
        self.existing_pages = {}
        body: dict = {"page_size": 100}

        while True:
            data = self._request("POST", f"/databases/{self.database_id}/query", json=body)
            for page in data.get("results", []):
                rich_text = page.get("properties", {}).get("Application ID", {}).get("rich_text", [])
                app_id = "".join(part.get("plain_text", "") for part in rich_text)
                if app_id:
                    self.existing_pages[app_id] = (page["id"], page["url"])

            if not data.get("has_more"):
                break
            body["start_cursor"] = data["next_cursor"]

    def find_existing(self, application_id: str) -> tuple[str, str] | None:
        """Return (page_id, page_url) if this application already exists."""
        return self.existing_pages.get(application_id)

    # ── Page creation ─────────────────────────────────────────────────────────

    def create_page(self, result: ProcessedApplication) -> tuple[str, str]:
        """
        Create a Notion page (database row) for a processed application.
        Returns (page_id, page_url).
        """
        app  = result.application
        risk = result.risk_assessment
        summ = result.onboarding_summary

        risk_factors_text = "\n".join(f"• {f}" for f in risk.risk_factors)

        properties = {
            self.title_property:  {"title": _rich_text(app.company_name)},
            "Application ID":     {"rich_text": _rich_text(app.application_id)},
            "Industry":           {"rich_text": _rich_text(app.industry)},
            "AUM (USD)":          {"number": int(app.aum_usd) if app.aum_usd else 0},
            "Risk Level":         {"select": {"name": risk.risk_level}},
            "Risk Score":         {"number": risk.risk_score},
            "PEP Flag":           {"checkbox": risk.pep_flag},
            "SAR Flag":           {"checkbox": risk.sar_flag},
            "Risk Factors":       {"rich_text": _rich_text(risk_factors_text)},
            "Onboarding Summary": {"rich_text": _rich_text(summ.summary)},
            "Action Required":    {"rich_text": _rich_text(summ.action_required)},
        }
        # Notion rejects anything that isn't an ISO date, so omit rather than fail the push
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", app.application_date):
            properties["Application Date"] = {"date": {"start": app.application_date}}

        data = self._request("POST", "/pages", json={
            "parent": {"database_id": self.database_id},
            "properties": properties,
        })
        return data["id"], data["url"]

    def push(self, result: ProcessedApplication) -> tuple[str, str]:
        """Unified push method — matches AirtableClient / MondayClient interface."""
        return self.create_page(result)


def _rich_text(text: str) -> list[dict]:
    """Split text into Notion rich_text objects (each capped at 2,000 characters)."""
    text = text or ""
    chunks = [text[i:i + RICH_TEXT_LIMIT] for i in range(0, len(text), RICH_TEXT_LIMIT)] or [""]
    return [{"type": "text", "text": {"content": chunk}} for chunk in chunks]

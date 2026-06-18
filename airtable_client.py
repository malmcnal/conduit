"""
airtable_client.py — Airtable REST API integration.

Handles:
  - Record creation in a pre-configured Airtable table
  - Deduplication by Application ID (one lookup per run)
  - Returns record ID and a direct URL to the record

Prerequisites (one-time manual setup):
  1. Create a free Airtable account at airtable.com
  2. Create a new Base called "Crestview Client Onboarding"
  3. Rename the default table to "Applications"
  4. Add these fields (Field type in parentheses):
       Application ID   (Single line text)
       Industry         (Single line text)
       AUM (USD)        (Number — integer)
       Risk Level       (Single select — options: LOW, MEDIUM, HIGH, CRITICAL)
       Risk Score       (Number — integer)
       PEP Flag         (Checkbox)
       SAR Flag         (Checkbox)
       Risk Factors     (Long text)
       Onboarding Summary (Long text)
       Action Required  (Single line text)
       Application Date (Date)
  5. Go to airtable.com/create/tokens → create a token with:
       Scopes: data.records:read, data.records:write
       Access: your new base
  6. Copy your Base ID from the URL: airtable.com/{BASE_ID}/{TABLE_ID}
  7. Add AIRTABLE_API_KEY and AIRTABLE_BASE_ID to your .env
"""

import time
import urllib.parse
import requests
from models import ProcessedApplication

AIRTABLE_API_URL = "https://api.airtable.com/v0"


class AirtableClient:
    def __init__(self, api_key: str, base_id: str, table_id: str = "Applications"):
        self.base_id = base_id
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # table_id can be either the table ID (tblXXX) or the table name
        self.table_url = f"{AIRTABLE_API_URL}/{base_id}/{urllib.parse.quote(table_id)}"
        # application_id → (record_id, record_url) — populated at setup
        self.existing_records: dict[str, tuple[str, str]] = {}

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _request(self, method: str, url: str, max_retries: int = 3, **kwargs) -> dict:
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = requests.request(method, url, headers=self.headers, timeout=30, **kwargs)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(retry_after)
                    last_exc = RuntimeError(f"Rate limited (attempt {attempt + 1})")
                    continue

                if resp.status_code >= 500:
                    time.sleep(2 ** attempt)
                    last_exc = RuntimeError(f"Server error {resp.status_code}")
                    continue

                resp.raise_for_status()
                return resp.json()

            except requests.exceptions.Timeout:
                time.sleep(2 ** attempt)
                last_exc = RuntimeError(f"Request timed out (attempt {attempt + 1})")
                continue

        raise RuntimeError(
            f"Airtable API failed after {max_retries} attempts. Last error: {last_exc}"
        )

    # ── Setup ─────────────────────────────────────────────────────────────────

    def setup(self) -> None:
        """Load existing records for dedup checking. Call once per run."""
        self._load_existing_records()

    def _load_existing_records(self) -> None:
        """
        Fetch all existing records and index by Application ID.
        Uses Airtable's pagination (100 records per page).
        """
        self.existing_records = {}
        params: dict = {"fields[]": "Application ID", "pageSize": 100}

        while True:
            data = self._request("GET", self.table_url, params=params)
            for record in data.get("records", []):
                app_id = record.get("fields", {}).get("Application ID", "")
                if app_id:
                    record_id = record["id"]
                    record_url = self._record_url(record_id)
                    self.existing_records[app_id] = (record_id, record_url)

            offset = data.get("offset")
            if not offset:
                break
            params["offset"] = offset

    def find_existing(self, application_id: str) -> tuple[str, str] | None:
        """Return (record_id, record_url) if this application already exists."""
        return self.existing_records.get(application_id)

    # ── Record creation ───────────────────────────────────────────────────────

    def create_record(self, result: ProcessedApplication) -> tuple[str, str]:
        """
        Create an Airtable record for a processed application.
        Returns (record_id, record_url).
        """
        app  = result.application
        risk = result.risk_assessment
        summ = result.onboarding_summary

        risk_factors_text = "\n".join(f"• {f}" for f in risk.risk_factors)

        fields = {
            "Name":                app.company_name,
            "Application ID":      app.application_id,
            "Industry":            app.industry,
            "AUM (USD)":           int(app.aum_usd) if app.aum_usd else 0,
            "Risk Level":          risk.risk_level,
            "Risk Score":          risk.risk_score,
            "PEP Flag":            risk.pep_flag,
            "SAR Flag":            risk.sar_flag,
            "Risk Factors":        risk_factors_text,
            "Onboarding Summary":  summ.summary,
            "Action Required":     summ.action_required,
            "Application Date":    app.application_date,
        }

        data = self._request("POST", self.table_url, json={"fields": fields})
        record_id = data["id"]
        return record_id, self._record_url(record_id)

    def _record_url(self, record_id: str) -> str:
        return f"https://airtable.com/{self.base_id}/{record_id}"

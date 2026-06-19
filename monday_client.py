"""
monday_client.py — monday.com GraphQL API integration.

Handles:
  - Board creation (on first run) with all required columns
  - Board state persistence (board_state.json) so re-runs reuse the same board
  - Item creation with fully populated column values per processed application

Column schema created on the board:
  Name            (built-in)   — company name
  application_id  (text)       — APP-0303 etc.
  industry        (text)
  aum             (numbers)    — USD
  risk_level      (text)       — LOW / MEDIUM / HIGH / CRITICAL
  risk_score      (numbers)    — 0–100
  pep_flag        (text)       — Yes / No
  sar_flag        (text)       — Yes / No
  risk_factors    (long_text)  — bullet list
  summary         (long_text)  — onboarding summary
  action_required (text)       — next action
  application_date (date)
"""

import json
import os
import time
from pathlib import Path
import requests
from models import ProcessedApplication

BOARD_STATE_FILE = Path(__file__).parent / "board_state.json"
MONDAY_API_URL = "https://api.monday.com/v2"


class MondayClient:
    def __init__(self, api_key: str, board_id: str | None = None):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "API-Version": "2023-10",
        }
        self.board_id: str | None = board_id
        self.column_ids: dict[str, str] = {}
        # application_id → (item_id, item_url) — populated at setup, used for dedup
        self.existing_items: dict[str, tuple[str, str]] = {}

        # Load persisted board state if it exists
        if BOARD_STATE_FILE.exists():
            state = json.loads(BOARD_STATE_FILE.read_text())
            self.board_id = self.board_id or state.get("board_id")
            self.column_ids = state.get("column_ids", {})

    # ── GraphQL execution ─────────────────────────────────────────────────────

    def _run(self, query: str, variables: dict | None = None, max_retries: int = 3) -> dict:
        """
        Execute a GraphQL query/mutation with exponential backoff retry.

        Retries on:
          - HTTP 429 (rate limit) — back off and retry
          - HTTP 5xx (server error) — back off and retry
          - requests.Timeout — back off and retry

        Raises immediately on:
          - HTTP 4xx (except 429) — bad request, retrying won't help
          - monday.com API errors in the response body — logic errors
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        last_exc: Exception | None = None

        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    MONDAY_API_URL, headers=self.headers, json=payload, timeout=30
                )

                if resp.status_code == 429:
                    wait = 2 ** attempt          # 1s, 2s, 4s
                    time.sleep(wait)
                    last_exc = RuntimeError(f"Rate limited (attempt {attempt + 1})")
                    continue

                if resp.status_code >= 500:
                    wait = 2 ** attempt
                    time.sleep(wait)
                    last_exc = RuntimeError(f"Server error {resp.status_code} (attempt {attempt + 1})")
                    continue

                resp.raise_for_status()          # raises on remaining 4xx

                data = resp.json()
                if "errors" in data:
                    raise RuntimeError(f"monday.com API error: {data['errors']}")

                return data["data"]

            except requests.exceptions.Timeout:
                wait = 2 ** attempt
                time.sleep(wait)
                last_exc = RuntimeError(f"Request timed out (attempt {attempt + 1})")
                continue

        raise RuntimeError(
            f"monday.com API failed after {max_retries} attempts. Last error: {last_exc}"
        )

    # ── Board setup ───────────────────────────────────────────────────────────

    def setup_board(self) -> str:
        """
        Return the board ID to use.
        Creates a new board with all columns on first run;
        reuses the persisted board on subsequent runs.
        Always loads existing items for dedup checking.
        """
        if not self.board_id or not self.column_ids:
            if self.board_id:
                # Board exists but column IDs not cached — fetch them
                self.column_ids = self._fetch_column_ids(self.board_id)
            else:
                # Create board from scratch
                self.board_id = self._create_board()
                self.column_ids = self._create_columns(self.board_id)
            self._save_state()

        # Always refresh existing items — needed for dedup on every run
        self._load_existing_items()
        return self.board_id

    def _create_board(self) -> str:
        data = self._run("""
            mutation {
                create_board(
                    board_name: "Crestview Client Onboarding",
                    board_kind: public
                ) { id }
            }
        """)
        return data["create_board"]["id"]

    def _create_columns(self, board_id: str) -> dict[str, str]:
        """Create all required columns and return a name→id mapping."""
        columns_to_create = [
            ("Application ID",    "text"),
            ("Industry",          "text"),
            ("AUM (USD)",         "numbers"),
            ("Risk Level",        "text"),
            ("Risk Score",        "numbers"),
            ("PEP Flag",          "text"),
            ("SAR Flag",          "text"),
            ("Risk Factors",      "long_text"),
            ("Onboarding Summary","long_text"),
            ("Action Required",   "text"),
            ("Application Date",  "date"),
        ]

        ids: dict[str, str] = {}
        for title, col_type in columns_to_create:
            result = self._run(
                """
                mutation CreateCol($boardId: ID!, $title: String!, $colType: ColumnType!) {
                    create_column(
                        board_id: $boardId,
                        title: $title,
                        column_type: $colType
                    ) { id title }
                }
                """,
                {"boardId": board_id, "title": title, "colType": col_type},
            )
            col = result["create_column"]
            ids[col["title"]] = col["id"]

        return ids

    def _fetch_column_ids(self, board_id: str) -> dict[str, str]:
        """Fetch existing column IDs from a board."""
        data = self._run(
            """
            query GetColumns($boardId: [ID!]!) {
                boards(ids: $boardId) {
                    columns { id title }
                }
            }
            """,
            {"boardId": [board_id]},
        )
        return {col["title"]: col["id"] for col in data["boards"][0]["columns"]}

    def _save_state(self):
        BOARD_STATE_FILE.write_text(
            json.dumps({"board_id": self.board_id, "column_ids": self.column_ids}, indent=2)
        )

    def _load_existing_items(self) -> None:
        """
        Fetch all existing board items and index them by Application ID.
        Called once per run during setup — one API call covers the whole batch.
        Populates self.existing_items: {application_id → (item_id, item_url)}.
        """
        if "Application ID" not in self.column_ids:
            return

        app_id_col = self.column_ids["Application ID"]

        data = self._run(
            """
            query GetItems($boardId: [ID!]!, $colId: String!) {
                boards(ids: $boardId) {
                    items_page(limit: 500) {
                        items {
                            id
                            column_values(ids: [$colId]) {
                                text
                            }
                        }
                    }
                }
            }
            """,
            {"boardId": [self.board_id], "colId": app_id_col},
        )

        self.existing_items = {}
        for item in data["boards"][0]["items_page"]["items"]:
            col_vals = item.get("column_values", [])
            app_id = col_vals[0]["text"] if col_vals else ""
            if app_id:
                item_id = item["id"]
                item_url = f"https://monday.com/boards/{self.board_id}/pulses/{item_id}"
                self.existing_items[app_id] = (item_id, item_url)

    def find_existing(self, application_id: str) -> tuple[str, str] | None:
        """
        Return (item_id, item_url) if this application already has a board item,
        or None if it doesn't. Used by the pipeline to skip duplicate creation.
        """
        return self.existing_items.get(application_id)

    # ── Item creation ─────────────────────────────────────────────────────────

    def create_item(self, result: ProcessedApplication) -> tuple[str, str]:
        """
        Create a monday.com board item for a processed application.

        Returns:
            (item_id, item_url)
        """
        app  = result.application
        risk = result.risk_assessment
        summ = result.onboarding_summary
        col  = self.column_ids

        risk_factors_text = "\n".join(f"• {f}" for f in risk.risk_factors)

        # Build column values dict, only include columns we know exist
        column_values: dict[str, object] = {}

        def set_col(name: str, value: object):
            if name in col:
                column_values[col[name]] = value

        # text columns  → plain string
        # long_text     → {"text": "..."}
        # numbers       → numeric value
        # date          → {"date": "YYYY-MM-DD"}
        set_col("Application ID",     app.application_id)
        set_col("Industry",           app.industry)
        set_col("AUM (USD)",          app.aum_usd)
        set_col("Risk Level",         risk.risk_level)
        set_col("Risk Score",         risk.risk_score)
        set_col("PEP Flag",           "Yes" if risk.pep_flag else "No")
        set_col("SAR Flag",           "Yes" if risk.sar_flag else "No")
        set_col("Risk Factors",       {"text": risk_factors_text})
        set_col("Onboarding Summary", {"text": summ.summary})
        set_col("Action Required",    summ.action_required)
        set_col("Application Date",   {"date": app.application_date})

        data = self._run(
            """
            mutation CreateItem($boardId: ID!, $name: String!, $columnValues: JSON!) {
                create_item(
                    board_id: $boardId,
                    item_name: $name,
                    column_values: $columnValues
                ) { id }
            }
            """,
            {
                "boardId": self.board_id,
                "name": app.company_name,
                "columnValues": json.dumps(column_values),
            },
        )

        item_id = data["create_item"]["id"]
        item_url = f"https://monday.com/boards/{self.board_id}/pulses/{item_id}"
        return item_id, item_url

    # ── Unified interface ─────────────────────────────────────────────────────

    def setup(self) -> None:
        """Unified setup method — matches AirtableClient interface."""
        self.setup_board()

    def push(self, result: ProcessedApplication) -> tuple[str, str]:
        """Unified push method — matches AirtableClient interface."""
        return self.create_item(result)

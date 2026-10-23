"""Tests for the Notion backend, with the HTTP layer stubbed out.

The interesting logic is the mapping from ProcessedApplication to Notion
properties and the schema/dedup setup, not the requests themselves.
"""

from models import ApplicationRecord, OnboardingSummary, ProcessedApplication, RiskAssessment
from notion_db_client import RICH_TEXT_LIMIT, SCHEMA, NotionClient, _rich_text


def make_result(**app_overrides):
    app = {
        "application_id": "APP-0001",
        "company_name": "Blackthorn Capital Partners",
        "industry": "Family Office",
        "aum_usd": 23_980_000.0,
        "primary_contact": "James Kelly",
        "contact_role": "Principal",
        "domicile": "Ireland",
        "num_jurisdictions": 1,
        "ownership_structure_notes": "Not stated",
        "beneficial_owners": "Undetermined",
        "source_of_funds": "Property sales and business exits",
        "regulatory_history": "None identified.",
        "additional_flags": "Former Department of Finance civil servant (PEP).",
        "application_date": "2026-10-23",
    }
    app.update(app_overrides)
    return ProcessedApplication(
        application=ApplicationRecord(**app),
        risk_assessment=RiskAssessment(
            risk_level="HIGH", risk_score=70, pep_flag=True, sar_flag=False,
            risk_factors=["PEP", "Unverified source of funds"],
            reasoning="PEP match.", recommended_action="Enhanced due diligence.",
        ),
        onboarding_summary=OnboardingSummary(
            summary="Family office with a PEP principal.",
            action_required="Compliance to run EDD this week.",
            reviewer_notes="",
        ),
    )


class StubbedClient(NotionClient):
    """NotionClient with _request replaced by a queue of canned responses."""

    def __init__(self, responses):
        super().__init__("secret", "db123")
        self.responses = list(responses)
        self.calls = []

    def _request(self, method, path, max_retries=3, **kwargs):
        self.calls.append((method, path, kwargs.get("json")))
        return self.responses.pop(0)


def test_rich_text_splits_at_notion_limit():
    chunks = _rich_text("x" * (RICH_TEXT_LIMIT * 2 + 1))
    assert [len(c["text"]["content"]) for c in chunks] == [RICH_TEXT_LIMIT, RICH_TEXT_LIMIT, 1]


def test_rich_text_handles_empty_string():
    assert _rich_text("") == [{"type": "text", "text": {"content": ""}}]


def test_setup_adds_only_missing_columns_and_finds_title():
    existing = {"Title": {"type": "title"}, "Risk Score": {"type": "number"}}
    client = StubbedClient([
        {"properties": existing},                         # GET database
        {},                                               # PATCH schema
        {"results": [], "has_more": False},               # query
    ])
    client.setup()

    method, _, body = client.calls[1]
    assert method == "PATCH"
    assert set(body["properties"]) == set(SCHEMA) - {"Risk Score"}
    assert client.title_property == "Title"


def test_setup_skips_patch_when_schema_complete():
    properties = {"Name": {"type": "title"}, **{name: {} for name in SCHEMA}}
    client = StubbedClient([{"properties": properties}, {"results": [], "has_more": False}])
    client.setup()
    assert [c[0] for c in client.calls] == ["GET", "POST"]


def test_dedup_index_follows_pagination():
    def page(app_id, n):
        return {"id": f"p{n}", "url": f"https://notion.so/p{n}",
                "properties": {"Application ID": {"rich_text": [{"plain_text": app_id}]}}}

    properties = {"Name": {"type": "title"}, **{name: {} for name in SCHEMA}}
    client = StubbedClient([
        {"properties": properties},
        {"results": [page("APP-1", 1)], "has_more": True, "next_cursor": "c2"},
        {"results": [page("APP-2", 2)], "has_more": False},
    ])
    client.setup()

    assert client.find_existing("APP-2") == ("p2", "https://notion.so/p2")
    assert client.find_existing("APP-3") is None
    assert client.calls[2][2]["start_cursor"] == "c2"


def test_push_maps_fields_and_returns_page_url():
    client = StubbedClient([{"id": "page1", "url": "https://notion.so/page1"}])
    assert client.push(make_result()) == ("page1", "https://notion.so/page1")

    _, path, body = client.calls[0]
    props = body["properties"]
    assert path == "/pages"
    assert body["parent"] == {"database_id": "db123"}
    assert props["Name"]["title"][0]["text"]["content"] == "Blackthorn Capital Partners"
    assert props["Risk Level"] == {"select": {"name": "HIGH"}}
    assert props["PEP Flag"] == {"checkbox": True}
    assert props["AUM (USD)"] == {"number": 23_980_000}
    assert props["Application Date"] == {"date": {"start": "2026-10-23"}}


def test_push_omits_non_iso_date_instead_of_failing():
    client = StubbedClient([{"id": "page1", "url": "u"}])
    client.push(make_result(application_date="Not stated"))
    assert "Application Date" not in client.calls[0][2]["properties"]

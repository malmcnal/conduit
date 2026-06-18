"""
Quick Airtable push test — no LLM calls.
Constructs a fake ProcessedApplication and pushes it to verify the integration.
"""

from config import AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID
from airtable_client import AirtableClient
from models import ApplicationRecord, RiskAssessment, OnboardingSummary, ProcessedApplication

app = ApplicationRecord(
    application_id="TEST-001",
    company_name="Test Entity Ltd",
    industry="Financial Services",
    aum_usd=10_000_000,
    domicile="Cayman Islands",
    num_jurisdictions=2,
    primary_contact="Jane Doe",
    contact_role="Introducer",
    application_date="2026-06-18",
    ownership_structure_notes="Single principal, 100% ownership.",
    beneficial_owners="Jane Doe",
    source_of_funds="Investment returns",
    regulatory_history="None",
    additional_flags="None",
)

risk = RiskAssessment(
    risk_level="LOW",
    risk_score=15,
    pep_flag=False,
    sar_flag=False,
    risk_factors=["Offshore domicile (Cayman Islands)", "Limited documentation provided"],
    reasoning="Low-risk entity with straightforward ownership structure.",
    recommended_action="Proceed with standard onboarding.",
)

summary = OnboardingSummary(
    summary="Test Entity Ltd is a low-risk financial services entity with a single principal and straightforward ownership.",
    action_required="Proceed with standard KYC",
    reviewer_notes="This is a test record — safe to delete.",
)

result = ProcessedApplication(application=app, risk_assessment=risk, onboarding_summary=summary)

print(f"Connecting to Airtable (base: {AIRTABLE_BASE_ID}, table: {AIRTABLE_TABLE_ID})…")
client = AirtableClient(AIRTABLE_API_KEY, AIRTABLE_BASE_ID, AIRTABLE_TABLE_ID)
client.setup()

existing = client.find_existing("TEST-001")
if existing:
    record_id, record_url = existing
    print(f"Record already exists: {record_url}")
else:
    record_id, record_url = client.create_record(result)
    print(f"✓ Record created: {record_url}")

"""
models.py — Typed data contracts between pipeline stages.

Each stage consumes the output of the previous stage as a typed model.
This makes the pipeline easy to test, extend, and debug independently.
"""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class ApplicationRecord(BaseModel):
    """One row from applications.csv — the raw client application data."""
    application_id: str
    company_name: str
    industry: str
    aum_usd: float
    primary_contact: str
    contact_role: str
    domicile: str
    num_jurisdictions: int
    ownership_structure_notes: str
    beneficial_owners: str
    source_of_funds: str
    regulatory_history: str
    additional_flags: str
    application_date: str


class RiskAssessment(BaseModel):
    """
    Stage 1 output — structured risk scoring from the LLM.

    The LLM is asked to return this exact JSON shape. Pydantic validates
    the response before it moves to Stage 2, so downstream code can rely
    on these types being correct.
    """
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    risk_score: int = Field(ge=0, le=100, description="0–100 numeric risk score")
    pep_flag: bool = Field(description="Politically Exposed Person identified")
    sar_flag: bool = Field(description="Suspicious Activity Report indicators present")
    risk_factors: list[str] = Field(description="Specific risk factors identified, in priority order")
    reasoning: str = Field(
        description=(
            "Explicit reasoning chain: how the identified risk factors combine to produce "
            "this risk level. Explain why this is LOW vs MEDIUM, or HIGH vs CRITICAL — "
            "not just what was found, but how those findings lead to the verdict. "
            "This is what allows a compliance officer to trust and act on the assessment."
        )
    )
    recommended_action: str = Field(description="One-line action for the compliance team")


class OnboardingSummary(BaseModel):
    """
    Stage 2 output — narrative summary for the compliance reviewer.

    Informed by the Stage 1 risk assessment so the summary reflects
    the actual risk context, not just the raw application data.
    """
    summary: str = Field(description="2–3 sentence summary for the compliance reviewer")
    action_required: str = Field(description="Specific next action — who does what by when")
    reviewer_notes: str = Field(description="Any additional context the reviewer should know")


class ProcessedApplication(BaseModel):
    """Complete pipeline output for one application."""
    application: ApplicationRecord
    risk_assessment: RiskAssessment
    onboarding_summary: OnboardingSummary
    airtable_record_id: str | None = None
    airtable_record_url: str | None = None

"""Tests for the typed contracts between pipeline stages.

These models are what stop a malformed LLM response from reaching the
backend push, so the validation boundaries are worth asserting.
"""

import pytest
from pydantic import ValidationError

from models import OnboardingSummary, RiskAssessment


def valid_risk(**overrides):
    data = {
        "risk_level": "HIGH",
        "risk_score": 72,
        "pep_flag": True,
        "sar_flag": False,
        "risk_factors": ["Complex ownership structure", "High-risk domicile"],
        "reasoning": "Multiple jurisdictions combined with a PEP match.",
        "recommended_action": "Escalate to enhanced due diligence.",
    }
    data.update(overrides)
    return data


def test_valid_risk_assessment_parses():
    r = RiskAssessment(**valid_risk())
    assert r.risk_level == "HIGH"
    assert r.risk_score == 72
    assert r.pep_flag is True
    assert len(r.risk_factors) == 2


@pytest.mark.parametrize("level", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
def test_all_risk_levels_accepted(level):
    assert RiskAssessment(**valid_risk(risk_level=level)).risk_level == level


def test_rejects_invented_risk_level():
    """The LLM must not be able to introduce a level the UI cannot render."""
    with pytest.raises(ValidationError):
        RiskAssessment(**valid_risk(risk_level="SEVERE"))


def test_rejects_lowercase_risk_level():
    with pytest.raises(ValidationError):
        RiskAssessment(**valid_risk(risk_level="high"))


@pytest.mark.parametrize("score", [-1, 101, 1000])
def test_rejects_out_of_range_score(score):
    with pytest.raises(ValidationError):
        RiskAssessment(**valid_risk(risk_score=score))


@pytest.mark.parametrize("score", [0, 100])
def test_score_boundaries_are_inclusive(score):
    assert RiskAssessment(**valid_risk(risk_score=score)).risk_score == score


def test_rejects_missing_required_field():
    data = valid_risk()
    del data["recommended_action"]
    with pytest.raises(ValidationError):
        RiskAssessment(**data)


def test_coerces_numeric_string_score():
    """LLMs sometimes return "72" instead of 72."""
    assert RiskAssessment(**valid_risk(risk_score="72")).risk_score == 72


def test_onboarding_summary_requires_all_fields():
    with pytest.raises(ValidationError):
        OnboardingSummary(summary="Looks fine.")

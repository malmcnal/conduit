"""
risk_assessment.py — Stage 1: LLM-powered risk scoring.

Takes a raw ApplicationRecord and returns a structured RiskAssessment.
The system prompt instructs Claude to respond with JSON only, which is then
validated by Pydantic before passing to Stage 2.
"""

import json
import anthropic
from models import ApplicationRecord, RiskAssessment

SYSTEM_PROMPT = """You are a senior compliance analyst at an investment management firm.
Your job is to assess the risk level of a new client application based on the information provided.

You must respond with a JSON object and nothing else — no explanation, no markdown, no code fences.
The JSON must match this exact schema:
{
  "risk_level": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "risk_score": <integer 0-100>,
  "pep_flag": <true|false>,
  "sar_flag": <true|false>,
  "risk_factors": ["<factor 1>", "<factor 2>", ...],
  "reasoning": "<explicit reasoning chain — not just what was found, but how those findings combine to produce this specific risk level. Explain why this is LOW and not MEDIUM, or CRITICAL and not HIGH. A compliance officer must be able to read this and understand exactly why you reached this verdict>",
  "recommended_action": "<one-line action for the compliance team>"
}

Risk level guidance:
- LOW (0–30): Simple structure, single jurisdiction, clean history, documented source of funds
- MEDIUM (31–60): Some complexity, dual jurisdiction, minor flags, or PEP with manageable exposure
- HIGH (61–80): Complex structure, multiple jurisdictions, incomplete documentation, adverse history, or clear PEP
- CRITICAL (81–100): Sanctions exposure, OFAC/EU sanctions links, SAR mandatory, multiple compounding flags

PEP flag: true if any beneficial owner holds or has held a senior government, political, or military position.
SAR flag: true if transaction patterns, cash movements, or structural arrangements suggest possible money laundering or fraud."""


def assess_risk(
    application: ApplicationRecord,
    client: anthropic.Anthropic,
    model: str,
) -> RiskAssessment:
    """
    Run Stage 1 risk assessment on a single application.

    Args:
        application: The parsed client application record.
        client: Initialised Anthropic client.
        model: Claude model name.

    Returns:
        RiskAssessment — validated Pydantic model.

    Raises:
        ValueError: If the response cannot be parsed or validated.
    """
    user_message = f"""Please assess the following client application:

Application ID: {application.application_id}
Company: {application.company_name}
Industry: {application.industry}
AUM (USD): ${application.aum_usd:,.0f}
Domicile: {application.domicile}
Jurisdictions: {application.num_jurisdictions}

Ownership structure:
{application.ownership_structure_notes}

Beneficial owners:
{application.beneficial_owners}

Source of funds:
{application.source_of_funds}

Regulatory history:
{application.regulatory_history}

Additional flags:
{application.additional_flags}
"""

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.1,  # Low temperature — consistent, deterministic scoring
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if Claude adds them despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
        return RiskAssessment(**data)
    except Exception as e:
        raise ValueError(
            f"Failed to parse risk assessment for {application.application_id}: {e}\n"
            f"Raw response: {raw}"
        )

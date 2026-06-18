"""
onboarding_summary.py — Stage 2: LLM-powered onboarding summary.

Takes both the raw ApplicationRecord AND the Stage 1 RiskAssessment.
The risk context is passed explicitly so the summary reflects the actual
risk scoring rather than being generated blind from raw application data.
"""

import json
import anthropic
from models import ApplicationRecord, RiskAssessment, OnboardingSummary

SYSTEM_PROMPT = """You are a compliance operations specialist preparing onboarding briefings
for senior reviewers at an investment management firm.

Given a client application and its risk assessment, write a concise briefing for the
compliance reviewer who will make the final decision.

You must respond with a JSON object and nothing else — no explanation, no markdown, no code fences.
The JSON must match this exact schema:
{
  "summary": "<2–3 sentence summary of the application and its key risk context>",
  "action_required": "<specific next action — name who does what and by when>",
  "reviewer_notes": "<any additional context, caveats, or things the reviewer should probe>"
}

Tone: direct, factual, professional. No marketing language. Be specific about risks.
If the risk is LOW, be brief. If the risk is HIGH or CRITICAL, be thorough — every detail matters."""


def generate_summary(
    application: ApplicationRecord,
    risk: RiskAssessment,
    client: anthropic.Anthropic,
    model: str,
) -> OnboardingSummary:
    """
    Run Stage 2 summary generation for a single application.

    Args:
        application: The parsed client application record.
        risk: The validated Stage 1 risk assessment.
        client: Initialised Anthropic client.
        model: Claude model name.

    Returns:
        OnboardingSummary — validated Pydantic model.

    Raises:
        ValueError: If the response cannot be parsed or validated.
    """
    flags = []
    if risk.pep_flag:
        flags.append("PEP FLAGGED")
    if risk.sar_flag:
        flags.append("SAR INDICATORS")
    flags_str = ", ".join(flags) if flags else "None"

    user_message = f"""Application: {application.application_id} — {application.company_name}
Industry: {application.industry} | AUM: ${application.aum_usd:,.0f} | Domicile: {application.domicile}

Risk Assessment Results:
- Risk Level: {risk.risk_level}
- Risk Score: {risk.risk_score}/100
- Special Flags: {flags_str}
- Risk Factors:
{chr(10).join(f'  • {f}' for f in risk.risk_factors)}
- Recommended Action: {risk.recommended_action}

Application context:
Ownership: {application.ownership_structure_notes}
Source of funds: {application.source_of_funds}
Regulatory history: {application.regulatory_history}
Additional flags: {application.additional_flags}

Please write the compliance reviewer briefing.
"""

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.2,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
        return OnboardingSummary(**data)
    except Exception as e:
        raise ValueError(
            f"Failed to parse onboarding summary for {application.application_id}: {e}\n"
            f"Raw response: {raw}"
        )

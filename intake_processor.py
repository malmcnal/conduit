"""
intake_processor.py — Stage 0: Unstructured document intake.

Accepts raw text of any format — email body, PDF extract, forwarded memo,
scanned form — and extracts a structured ApplicationRecord using Claude.

This is the capability that addresses the core limitation of RPA:
unlike pattern-matching scripts that break whenever a document changes format,
the LLM understands language and can extract the right fields from any
coherent text. Format variation is the problem; this is why it's not the problem.

Usage:
    from intake_processor import process_document
    app = process_document(raw_text, anthropic_client, model)
"""

import json
from datetime import date
import anthropic
from models import ApplicationRecord

SYSTEM_PROMPT = """You are a client onboarding specialist at a global investment management firm.

Your job is to read unstructured documents — emails, forwarded messages, memos, PDF extracts,
Word documents — and extract a complete, structured client application record in JSON.

You must respond with a JSON object and nothing else — no explanation, no markdown, no code fences.

Required JSON schema:
{
  "application_id": "<if not in the document, generate one: DOC-YYYYMMDD-001 using today's date>",
  "company_name": "<full legal name of the client entity or individual>",
  "industry": "<client classification, e.g. 'Corporate — Venture Capital', 'High-Net-Worth Individual', 'Institutional — Pension Fund', 'Family Office'>",
  "aum_usd": <number — total investment amount in USD. Convert other currencies: GBP × 1.27, EUR × 1.09, CHF × 1.13. Use 0 only if completely absent.>,
  "primary_contact": "<main contact name, or 'Not stated'>",
  "contact_role": "<their title or role, or 'Not stated'>",
  "domicile": "<primary legal jurisdiction of the entity>",
  "num_jurisdictions": <integer — count ALL distinct jurisdictions across all entities, feeder vehicles, and LP domiciles mentioned>,
  "ownership_structure_notes": "<describe ownership structure as completely as the document allows. Note gaps explicitly.>",
  "beneficial_owners": "<names and approximate stakes of beneficial owners. Note 'Undetermined' if cannot be established.>",
  "source_of_funds": "<origin of the investment capital. Note if vague or unsubstantiated.>",
  "regulatory_history": "<regulatory, legal, or compliance matters mentioned. 'None identified.' if clean.>",
  "additional_flags": "<ALL items requiring compliance attention — be specific and thorough. See extraction rules below.>",
  "application_date": "<YYYY-MM-DD — parse any date format. Use today's date if not stated.>"
}

Compliance extraction rules — apply these rigorously to additional_flags:

PEP DETECTION (flag any of the following):
- Current or former government officials at any level (national, regional, military, judicial, central bank)
- Anyone described as: civil servant, minister, secretary, advisor to government, treasury official,
  diplomat, senior public servant, state enterprise executive, or any equivalent phrase
- Phrases like 'used to work for the government', 'left the ministry', 'formerly at the Treasury',
  'ex-civil servant' are all PEP indicators — extract the role and how long ago they left
- Family members or known close associates of government officials also qualify
- Include in the flag: full name, former role, and how long ago they held it

INCOMPLETE DOCUMENTATION (flag all of these):
- Documents explicitly described as missing, pending, 'to follow', or 'we'll send next week'
- KYC records with partial information (e.g. LP lists with missing addresses)
- Financial statements or audits that have not been reviewed by the submitting party
- Any field the sender says they will provide later

URGENCY PRESSURE (flag if present):
- Compressed timeline requests: 'within 2 weeks', 'by end of quarter', 'as soon as possible'
- References to board meetings, quarter-end deadlines, or capital sitting uninvested
- Any implicit or explicit pressure to proceed before documentation is complete

OFFSHORE AND INTERNATIONAL STRUCTURES:
- All offshore vehicles or feeder funds in additional jurisdictions
- Gulf, Middle East, or high-risk jurisdiction investors — note nationality and domicile of each
- Any structure that adds jurisdictions beyond the primary entity domicile

INTRODUCER RELATIONSHIPS:
- Clients referred via third parties — note whether the introducer is known to the firm
- Any indirect contact arrangement (e.g. all comms through an advisor, not the client directly)"""


def process_document(
    raw_text: str,
    client: anthropic.Anthropic,
    model: str,
    source_label: str = "document",
) -> ApplicationRecord:
    """
    Stage 0: Extract a structured ApplicationRecord from any unstructured text.

    The LLM handles format variation — email threads, PDF extracts, Word docs —
    without any template matching. Format changes do not break it. This is the
    fundamental difference from the RPA approach.

    Args:
        raw_text:     Raw document text — any format, any structure.
        client:       Initialised Anthropic client.
        model:        Claude model name.
        source_label: Human-readable label used in error messages.

    Returns:
        ApplicationRecord — validated Pydantic model, ready for Stage 1.

    Raises:
        ValueError: If the LLM response cannot be parsed or validated.
    """
    today = date.today().isoformat()

    user_message = f"""Today's date is {today}. Use this when generating application IDs or interpreting relative dates.

Extract all client application information from the document below and return it as a structured JSON record.

For fields that are genuinely absent, use your best inference where reasonable,
or write 'Not stated' for text fields. Never leave additional_flags empty if there
is anything compliance-relevant in the document — err on the side of flagging more.

---DOCUMENT START---
{raw_text}
---DOCUMENT END---"""

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0.1,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if added despite instructions
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        data = json.loads(raw)
        return ApplicationRecord(**data)
    except Exception as e:
        raise ValueError(
            f"Stage 0 extraction failed for {source_label}: {e}\n"
            f"Raw response:\n{raw}"
        )

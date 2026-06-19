# Conduit

Document intake pipeline. Unstructured documents go in — PDFs, emails, memos — and structured, risk-assessed records come out, pushed to a work management tool.

Built as a proof of concept for AI-powered client onboarding in financial services, but the architecture is general.

## How it works

```
Document (PDF / text)
       │
       ▼
  Stage 0 — Intake
  ┌─────────────────────────────────────────────────────────┐
  │  PDF path:  Marker (OCR + layout + table extraction)    │
  │             → clean markdown                            │
  │             → Claude extracts structured fields         │
  │                                                         │
  │  Text path: Claude extracts structured fields directly  │
  └─────────────────────────────────────────────────────────┘
       │
       ▼
  Stage 1 — Risk Assessment (Claude)
  Risk level, score, PEP flag, SAR flag, contributing factors
       │
       ▼
  Stage 2 — Summary (Claude)
  Plain-language summary + recommended action
       │
       ▼
  Airtable (or CSV output)
```

The Marker integration is the core architectural decision: it separates document parsing (OCR, layout detection, table extraction) from semantic extraction (field identification). Giving Claude clean, structured markdown instead of raw PDF bytes produces significantly better results on complex documents.

## Setup

**Dependencies**

```bash
pip install -r requirements.txt
```

For PDF processing via Marker, Python 3.10+ is required:

```bash
pip install marker-pdf==0.2.6 pdftext==0.3.4
```

**Environment**

Copy `.env.example` to `.env` and fill in:

```
ANTHROPIC_API_KEY=...
AIRTABLE_API_KEY=...   # personal access token from airtable.com/create/tokens
AIRTABLE_BASE_ID=...   # the "app..." portion of your Airtable URL
AIRTABLE_TABLE_ID=...  # the "tbl..." portion of your Airtable URL
```

**Airtable table setup** (one-time)

Create a table with these fields:

| Field name | Type |
|---|---|
| Name | Single line text (primary) |
| Application ID | Single line text |
| Industry | Single line text |
| AUM (USD) | Number |
| Risk Level | Single select — LOW / MEDIUM / HIGH / CRITICAL |
| Risk Score | Number |
| PEP Flag | Checkbox |
| SAR Flag | Checkbox |
| Risk Factors | Long text |
| Onboarding Summary | Long text |
| Action Required | Single line text |
| Application Date | Date |

## Usage

**PDF via Marker (recommended for real documents)**

```bash
python3.12 pipeline.py --marker-file data/sample_intake.pdf
```

**Plain text document**

```bash
python pipeline.py --document data/sample_intake_email.txt
```

**CSV batch**

```bash
python pipeline.py --csv data/applications.csv
```

**Skip Airtable push (local test)**

```bash
python3.12 pipeline.py --marker-file data/sample_intake.pdf --skip-airtable
```

**Test Airtable connection only**

```bash
python test_airtable_push.py
```

**Generate sample PDF**

```bash
python create_sample_pdf.py
# outputs data/sample_intake.pdf
```

## Project structure

```
pipeline.py          — entry point, CLI, display
airtable_client.py   — Airtable REST integration
marker_intake.py     — Stage 0 (PDF path): Marker + Claude
intake_processor.py  — Stage 0 (text path): Claude only
risk_assessment.py   — Stage 1: risk scoring
onboarding_summary.py — Stage 2: summary generation
models.py            — Pydantic data models
config.py            — env loading, client init
create_sample_pdf.py — generates a sample compliance PDF for testing
test_airtable_push.py — Airtable push test (no LLM calls)
```

## Notes

- Marker models download on first run (~1-2GB, cached after)
- On CPU (no GPU), Marker takes 2-4 minutes per page
- `pdftext==0.3.4` is required — later versions changed the API in a way that breaks `marker-pdf==0.2.6`
- monday.com support coming

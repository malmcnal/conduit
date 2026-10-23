# Conduit

[![CI](https://github.com/malmcnal/conduit/actions/workflows/ci.yml/badge.svg)](https://github.com/malmcnal/conduit/actions/workflows/ci.yml)

AI-powered document intake pipeline. Unstructured documents go in — PDFs, emails, scanned forms, handwritten notes — and structured, risk-assessed records come out, pushed to Airtable, Notion or monday.com.

Built for compliance-heavy onboarding workflows in financial services. The architecture is general.

---

## First run in 5 minutes

```bash
git clone https://github.com/malmcnal/conduit
cd conduit
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-ocr.txt && pip install --no-deps "pdftext==0.3.4"
cp .env.example .env          # add your Anthropic key (backend keys optional)
python pipeline.py --marker-file data/sample_intake.pdf --skip-backend
```

You should see a full risk-assessed output in the terminal within 2–3 minutes. No backend required for the first test.

---

## How it works

```
Document (PDF / image / plain text)
        │
        ▼
  Stage 0 — Intake (input-dependent)
  ┌───────────────────────────────────────────────────────────────┐
  │  --marker-file   PDF → Marker (OCR + layout + tables)        │
  │                  → clean markdown → Claude extracts fields    │
  │                                                               │
  │  --document      Plain text → Claude extracts fields directly │
  │                                                               │
  │  --image         Image / handwriting → Claude vision          │
  │                  (or --ocr surya: Surya OCR → Claude)         │
  └───────────────────────────────────────────────────────────────┘
        │
        ▼
  Stage 1 — Risk Assessment (Claude)
  Risk level (LOW/MEDIUM/HIGH/CRITICAL), score, PEP flag, SAR flag
        │
        ▼
  Stage 2 — Onboarding Summary (Claude)
  Plain-language briefing + recommended action for the reviewer
        │
        ▼
  Airtable, Notion or monday.com (or CSV only with --skip-backend)
```

The key architectural decision is separating document parsing from semantic extraction. Marker handles OCR, layout detection, table reconstruction, and reading order. Claude receives clean, structured markdown and only has to understand the content — not recover structure from garbled bytes. This is the same separation Datalab's platform is built on.

---

## Prerequisites

- Python 3.12 (3.10+ for the core pipeline)
- An [Anthropic API key](https://console.anthropic.com/settings/keys)
- Airtable, Notion or monday.com account (optional — `--skip-backend` skips the push). Notion's free plan includes API access.

---

## Installation

Use a project virtualenv so the pinned OCR stack doesn't clash with other projects:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Core pipeline only (text, CSV and Claude-vision image paths):

```bash
pip install -r requirements.txt
```

Everything, including Marker (PDF), Surya (image OCR) and the benchmark libraries:

```bash
pip install -r requirements-ocr.txt
pip install --no-deps "pdftext==0.3.4"
```

> **Note**: `pdftext==0.3.4` is pinned. Later versions changed `dictionary_output()` to expect file paths; `marker-pdf==0.2.6` passes `PdfDocument` objects. marker-pdf declares `pdftext>=0.3.7` anyway, so 0.3.4 has to be installed with `--no-deps` after everything else.

Marker models (~1–2 GB) download automatically on first run and are cached after that.

---

## Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

### Airtable (recommended)

```env
ANTHROPIC_API_KEY=sk-ant-...

AIRTABLE_API_KEY=pat...          # personal access token — airtable.com/create/tokens
AIRTABLE_BASE_ID=app...          # "app..." portion of your base URL
AIRTABLE_TABLE_ID=tbl...         # "tbl..." portion of your table URL
AIRTABLE_VIEW_ID=viw...          # optional — used to build record URLs
```

### Notion (free)

```env
ANTHROPIC_API_KEY=sk-ant-...

NOTION_API_KEY=ntn_...           # internal integration secret
NOTION_DATABASE_ID=...           # 32-char ID from the database URL
```

### monday.com

```env
ANTHROPIC_API_KEY=sk-ant-...

MONDAY_API_KEY=...               # Profile → Developers → API v2 Token
MONDAY_BOARD_ID=...              # numeric board ID from the URL
```

If several are configured, the priority is Airtable, then Notion, then monday.com. Pass `--backend notion` (or `monday`) to override.

---

## Backend setup

### Airtable table

Create a table with these fields (exact names required):

| Field name | Type |
|---|---|
| Name | Single line text (primary field) |
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

### Notion database

1. [notion.so/profile/integrations](https://www.notion.so/profile/integrations) → **New integration** (Internal). Give it Read, Insert and Update content. Copy the secret into `NOTION_API_KEY`.
2. Create an empty full-page database in Notion (e.g. "Conduit Applications").
3. On the database: **••• → Connections →** add your integration.
4. Copy the database ID (the 32-character string before `?v=` in the URL) into `NOTION_DATABASE_ID`.

No manual columns needed: on first run the pipeline adds Application ID, Risk Level (select), PEP/SAR Flag (checkboxes) and the rest. The database's title column holds the company name.

### monday.com board

The pipeline creates items automatically — no manual column setup required. It reads board structure on startup and maps to whatever columns exist.

---

## Usage

### PDF (recommended for enterprise documents)

```bash
python pipeline.py --marker-file data/sample_intake.pdf
```

Uses Marker to extract layout, tables, and OCR before passing to Claude. Best results on complex multi-column PDFs.

### Plain text document

```bash
python pipeline.py --document data/intake_email.txt
```

For emails, memos, or any document you can copy as text. Claude handles format variation — no templates required.

### Scanned image or photo

```bash
python pipeline.py --image data/blackt_CP.jpeg                # Claude vision (default)
python pipeline.py --image data/intake_scan.jpg --ocr surya   # local Surya OCR, then Claude
```

By default Claude reads the image directly and extracts fields in one call, which handles handwriting. `--ocr surya` runs Surya 0.4.5 locally first; it's fine on clean printed scans but can't read handwriting (newer Surya versions can, but need a torch release with no Intel Mac support).

### CSV batch

```bash
python pipeline.py                              # default: data/applications.csv
python pipeline.py --csv data/custom.csv        # custom path
python pipeline.py --app DOC-20260101-001       # single record by ID
```

Already-processed records are skipped automatically (dedup by Application ID).

### Backend selection

```bash
python pipeline.py --marker-file doc.pdf --backend airtable
python pipeline.py --marker-file doc.pdf --backend notion
python pipeline.py --marker-file doc.pdf --backend monday
python pipeline.py --marker-file doc.pdf --skip-backend     # local only, no push
```

### Full flag reference

| Flag | Default | Description |
|---|---|---|
| `--marker-file PATH` | — | Process a PDF via Marker |
| `--document PATH` | — | Process a plain-text document |
| `--image PATH` | — | Process a scan, photo or handwritten image |
| `--ocr [claude\|surya]` | `claude` | How `--image` is read |
| `--csv PATH` | `data/applications.csv` | CSV batch input |
| `--app ID` | — | Process a single application by ID (CSV mode) |
| `--backend [airtable\|notion\|monday]` | auto-detect | Force a specific backend |
| `--skip-backend` | false | Skip backend push, output CSV only |

---

## Benchmarking extraction methods

Compare Marker against standard Python PDF libraries on any document:

```bash
# Text quality only (fast — no Claude calls)
python benchmark.py data/sample_intake.pdf --no-llm

# Full benchmark including Claude extraction scoring
python benchmark.py data/sample_intake.pdf

# Save results to benchmark_results.json
python benchmark.py data/sample_intake.pdf --save
```

Methods compared: Marker (Datalab), pypdf, pdfplumber.

Scored on: characters extracted, structure preservation, field completeness after Claude extraction, estimated input token cost.

---

## Cost per document

Each document run makes 2–3 Claude API calls (one per stage). Token usage and estimated cost are logged to the terminal and to the output CSV.

Typical cost on `claude-opus-4-5` for a 1–2 page compliance document:

| Stage | Typical input tokens | Typical output tokens |
|---|---|---|
| Stage 0 — field extraction | 2,000–4,000 | 400–600 |
| Stage 1 — risk assessment | 800–1,200 | 300–500 |
| Stage 2 — summary | 600–900 | 200–350 |
| **Total per document** | **~3,500–6,000** | **~900–1,500** |

At $15/MTok input and $75/MTok output (claude-opus-4-5), this is roughly **$0.05–$0.17 per document**.

The CSV output includes `input_tokens`, `output_tokens`, and `estimated_cost_usd` columns for every run.

---

## Testing without LLM calls

```bash
python test_airtable_push.py    # push a fake record to Airtable (no Claude)
python create_sample_pdf.py     # generate data/sample_intake.pdf for testing
```

---

## Project structure

```
pipeline.py            — entry point, CLI, terminal display
cost_tracker.py        — token usage tracking and cost estimation
airtable_client.py     — Airtable REST integration
notion_db_client.py    — Notion API integration
monday_client.py       — monday.com GraphQL integration
marker_intake.py       — Stage 0 (PDF): Marker + Claude
vision_intake.py       — Stage 0 (image, default): Claude vision
surya_intake.py        — Stage 0 (image, --ocr surya): Surya OCR + Claude
intake_processor.py    — Stage 0 (text): Claude extraction
risk_assessment.py     — Stage 1: risk scoring
onboarding_summary.py  — Stage 2: summary generation
benchmark.py           — extraction method comparison
models.py              — Pydantic data contracts
config.py              — env loading, backend factory
create_sample_pdf.py   — generates a sample compliance PDF
test_airtable_push.py  — Airtable integration test (no LLM)
data/                  — test documents (PDFs, images)
```

---

## Troubleshooting

**`TypeError: Invalid input type 'PdfDocument'` when using Marker**
Pin `pdftext==0.3.4`. Later versions broke the API that marker-pdf 0.2.6 depends on:
```bash
pip install "pdftext==0.3.4"
```

**Airtable 404 on setup**
`AIRTABLE_BASE_ID` must be just the `app...` portion — not the full URL. Separate the `tbl...` and `viw...` parts into their own env vars.

**First Marker run is slow**
Models download on first run (~1–2 GB). After that they're cached in `~/.cache/huggingface/`. On CPU (Intel Mac), expect 1–3 minutes per page.

**`--document` fails with UnicodeDecodeError on a PDF**
`--document` reads plain text. Use `--marker-file` for PDFs.

**Backend push skipped with "No backend configured"**
Ensure your `.env` has `AIRTABLE_API_KEY` + `AIRTABLE_BASE_ID`, or `MONDAY_API_KEY`. Then reload: the process must be restarted after editing `.env`.

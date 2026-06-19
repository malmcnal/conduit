"""
benchmark.py — PDF extraction method comparison

Runs the same document through three extraction approaches and scores each one
on text quality, extraction completeness, and Claude input cost.

Methods compared:
  marker    — Datalab's layout-aware PDF→markdown converter (handles tables,
               multi-column, OCR, reading order)
  pypdf     — Pure-Python PDF text extraction (fast, no ML, flattens structure)
  pdfplumber — Layout-aware Python extraction using pdfminer under the hood
               (better than pypdf for structured docs, no ML required)

Usage:
    python benchmark.py data/sample_intake.pdf
    python benchmark.py data/sample_intake.pdf --no-llm   # text quality only, skip Claude
    python benchmark.py data/sample_intake.pdf --save     # write results to benchmark_results.json
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

ENCODING = "claude-3-5-haiku-20241022"  # cheap model for benchmarking token counts


# ── Extraction methods ────────────────────────────────────────────────────────

def extract_marker(pdf_path: str) -> tuple[str, float]:
    """Marker: Datalab's layout-aware PDF parser."""
    import io
    import logging
    import warnings

    # Suppress model-loading noise — redirect stdout temporarily so tqdm
    # progress bars and HF warnings don't interleave with our output.
    logging.disable(logging.WARNING)
    warnings.filterwarnings("ignore")
    _real_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        from marker.convert import convert_single_pdf
        from marker.models import load_all_models
        t0 = time.time()
        models = load_all_models()
        text, _, _ = convert_single_pdf(pdf_path, models)
        elapsed = time.time() - t0
    finally:
        sys.stdout = _real_stdout
        logging.disable(logging.NOTSET)
    return text, elapsed


def extract_pypdf(pdf_path: str) -> tuple[str, float]:
    """pypdf: pure-Python extraction, no ML."""
    import pypdf
    t0 = time.time()
    reader = pypdf.PdfReader(pdf_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n\n".join(pages)
    return text, time.time() - t0


def extract_pdfplumber(pdf_path: str) -> tuple[str, float]:
    """pdfplumber: layout-aware extraction using pdfminer."""
    import pdfplumber
    import re
    t0 = time.time()
    lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # layout=False gives cleaner text without excessive whitespace padding
            page_text = page.extract_text(layout=False) or ""
            if page_text.strip():
                lines.append(page_text)
    text = "\n\n".join(lines)
    # Collapse runs of 3+ spaces (layout artefacts) to a single space
    text = re.sub(r" {3,}", " ", text)
    return text, time.time() - t0


EXTRACTORS = {
    "marker":     extract_marker,
    "pypdf":      extract_pypdf,
    "pdfplumber": extract_pdfplumber,
}


# ── Scoring ───────────────────────────────────────────────────────────────────

# ApplicationRecord fields that must be non-trivial to count as "extracted"
REQUIRED_FIELDS = [
    "company_name", "industry", "aum_usd", "primary_contact", "contact_role",
    "domicile", "num_jurisdictions", "ownership_structure_notes",
    "beneficial_owners", "source_of_funds", "regulatory_history",
    "additional_flags",
]

NOT_STATED_TOKENS = {"not stated", "not provided", "unknown", "n/a", "none", "0"}


def field_is_populated(value) -> bool:
    """Return True if a field contains real information."""
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() not in NOT_STATED_TOKENS


def score_extraction(record) -> dict:
    """Score an ApplicationRecord on field completeness."""
    populated = sum(
        field_is_populated(getattr(record, f, None))
        for f in REQUIRED_FIELDS
    )
    total = len(REQUIRED_FIELDS)
    return {
        "fields_populated": populated,
        "fields_total": total,
        "completeness_pct": round(populated / total * 100, 1),
    }


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token (GPT/Claude average)."""
    return len(text) // 4


def text_stats(text: str) -> dict:
    """Basic text quality metrics."""
    lines = [l for l in text.splitlines() if l.strip()]
    words = text.split()
    return {
        "chars": len(text),
        "words": len(words),
        "lines": len(lines),
        "estimated_tokens": estimate_tokens(text),
    }


# ── Rendering ─────────────────────────────────────────────────────────────────

def col(text, width, align="left") -> str:
    s = str(text)
    if align == "right":
        return s.rjust(width)
    return s.ljust(width)


def render_table(headers: list[tuple[str, int, str]], rows: list[list]) -> str:
    """Render a fixed-width ASCII table."""
    sep = "+" + "+".join("-" * (w + 2) for _, w, _ in headers) + "+"
    header_row = "|" + "|".join(f" {col(h, w, a)} " for h, w, a in headers) + "|"
    lines = [sep, header_row, sep]
    for row in rows:
        lines.append("|" + "|".join(f" {col(v, w, a)} " for v, (_, w, a) in zip(row, headers)) + "|")
    lines.append(sep)
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

@dataclass
class BenchmarkResult:
    method: str
    extraction_seconds: float
    chars: int
    words: int
    lines: int
    estimated_tokens: int
    fields_populated: int = 0
    fields_total: int = len(REQUIRED_FIELDS)
    completeness_pct: float = 0.0
    llm_extraction_seconds: float = 0.0
    llm_ran: bool = False
    error: str = ""


def run_benchmark(pdf_path: str, run_llm: bool = True, save: bool = False):
    if not os.path.exists(pdf_path):
        print(f"Error: file not found — {pdf_path}")
        sys.exit(1)

    pdf_name = Path(pdf_path).name
    print(f"\n{'='*60}")
    print(f"  Conduit — PDF Extraction Benchmark")
    print(f"  Document: {pdf_name}")
    print(f"{'='*60}\n")

    # Load LLM client once if needed
    llm_client = None
    llm_model = None
    if run_llm:
        try:
            from config import get_anthropic_client
            llm_client, llm_model = get_anthropic_client()
            print(f"  LLM: {llm_model} (extraction scoring enabled)\n")
        except Exception as e:
            print(f"  Warning: could not load Anthropic client ({e}). Running text-only benchmark.\n")
            run_llm = False

    results: list[BenchmarkResult] = []
    extracted_texts: dict[str, str] = {}

    # ── Step 1: run all extractors ─────────────────────────────────────────
    for name, extractor in EXTRACTORS.items():
        print(f"  [{name}] Extracting text...", end="", flush=True)
        try:
            text, elapsed = extractor(pdf_path)
            extracted_texts[name] = text
            stats = text_stats(text)
            r = BenchmarkResult(
                method=name,
                extraction_seconds=round(elapsed, 2),
                **stats,
            )
            results.append(r)
            print(f" {stats['chars']:,} chars in {elapsed:.1f}s")
        except Exception as e:
            print(f" FAILED: {e}")
            results.append(BenchmarkResult(method=name, extraction_seconds=0, chars=0,
                                           words=0, lines=0, estimated_tokens=0, error=str(e)))

    # ── Step 2: run Claude extraction on each ─────────────────────────────
    if run_llm:
        print()
        from intake_processor import process_document
        for r in results:
            if r.error:
                continue
            text = extracted_texts[r.method]
            print(f"  [Claude ← {r.method}] Extracting compliance fields...", end="", flush=True)
            t0 = time.time()
            try:
                record = process_document(
                    raw_text=text,
                    client=llm_client,
                    model=llm_model,
                    source_label=f"{pdf_name} ({r.method})",
                )
                elapsed = time.time() - t0
                scores = score_extraction(record)
                r.fields_populated = scores["fields_populated"]
                r.fields_total = scores["fields_total"]
                r.completeness_pct = scores["completeness_pct"]
                r.llm_extraction_seconds = round(elapsed, 2)
                r.llm_ran = True
                print(f" {r.fields_populated}/{r.fields_total} fields ({r.completeness_pct}%) in {elapsed:.1f}s")
            except Exception as e:
                print(f" FAILED: {e}")
                r.error = r.error or str(e)

    # ── Step 3: print results table ────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  RESULTS")
    print(f"{'='*60}\n")

    # Text quality table
    print("  Text Extraction Quality\n")
    headers = [
        ("Method",    10, "left"),
        ("Chars",      8, "right"),
        ("Words",      7, "right"),
        ("Lines",      6, "right"),
        ("~Tokens",    8, "right"),
        ("Time (s)",   9, "right"),
    ]
    rows = []
    for r in results:
        rows.append([
            r.method,
            f"{r.chars:,}" if not r.error else "FAILED",
            f"{r.words:,}" if not r.error else "",
            f"{r.lines:,}" if not r.error else "",
            f"{r.estimated_tokens:,}" if not r.error else "",
            f"{r.extraction_seconds:.1f}" if not r.error else "",
        ])
    print(render_table(headers, rows))

    if run_llm:
        print("\n  Compliance Field Extraction (via Claude)\n")
        headers2 = [
            ("Method",       10, "left"),
            ("Fields",        8, "right"),
            ("Complete %",   11, "right"),
            ("LLM Time (s)", 13, "right"),
            ("Input ~Tokens", 14, "right"),
        ]
        rows2 = []
        for r in results:
            if r.error and not r.llm_ran:
                rows2.append([r.method, "FAILED", "", "", ""])
            else:
                rows2.append([
                    r.method,
                    f"{r.fields_populated}/{r.fields_total}",
                    f"{r.completeness_pct}%",
                    f"{r.llm_extraction_seconds:.1f}",
                    f"{r.estimated_tokens:,}",
                ])
        print(render_table(headers2, rows2))

    # ── Step 4: verdict ────────────────────────────────────────────────────
    print("\n  Verdict\n")
    valid = [r for r in results if not r.error]
    if valid:
        best_completeness = max(valid, key=lambda r: r.completeness_pct) if run_llm else None
        best_text = max(valid, key=lambda r: r.chars)
        most_efficient = min(valid, key=lambda r: r.estimated_tokens)

        if best_completeness:
            print(f"  Best extraction completeness : {best_completeness.method} "
                  f"({best_completeness.completeness_pct}% fields populated)")
        print(f"  Most text preserved         : {best_text.method} ({best_text.chars:,} chars)")
        print(f"  Lowest Claude input cost    : {most_efficient.method} "
              f"(~{most_efficient.estimated_tokens:,} tokens)")

        if best_completeness and best_completeness.method == "marker":
            print(f"\n  Marker leads on completeness — the layout-aware parse gives Claude")
            print(f"  cleaner, better-structured input than flat text extraction.")
        elif best_completeness:
            print(f"\n  Note: {best_completeness.method} led on completeness this run.")

    print()

    # ── Step 5: save results ───────────────────────────────────────────────
    if save:
        out_path = "benchmark_results.json"
        with open(out_path, "w") as f:
            json.dump(
                {
                    "document": pdf_name,
                    "results": [asdict(r) for r in results],
                },
                f,
                indent=2,
            )
        print(f"  Results saved to {out_path}\n")

    # ── Step 6: text samples (first 300 chars per method) ─────────────────
    print(f"{'='*60}")
    print("  TEXT SAMPLES (first 300 chars per method)")
    print(f"{'='*60}")
    for name, text in extracted_texts.items():
        preview = text[:300].replace("\n", " ↵ ")
        print(f"\n  [{name}]")
        print(f"  {preview}...")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark PDF extraction methods")
    parser.add_argument("pdf", nargs="?", default="data/sample_intake.pdf",
                        help="Path to PDF file (default: data/sample_intake.pdf)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip Claude extraction — text quality metrics only")
    parser.add_argument("--save", action="store_true",
                        help="Save results to benchmark_results.json")
    args = parser.parse_args()

    run_benchmark(args.pdf, run_llm=not args.no_llm, save=args.save)

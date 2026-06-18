"""
marker_intake.py — Stage 0 (Marker edition)

The original Stage 0 used a single LLM call to do two things:
  1. Parse document structure (headers, tables, layout) from raw text
  2. Extract compliance fields semantically

That works for plain-text emails. It fails on real enterprise documents —
multi-column PDFs, scanned forms, documents with embedded tables — because
the LLM receives garbled or flattened text and has no way to recover the
structure.

This version separates those concerns:
  - Marker handles document parsing: OCR, layout detection, table extraction,
    reading order, multi-column layout, header/footer removal
  - Claude handles semantic extraction from clean, structured markdown

Marker produces markdown that preserves document structure faithfully.
The LLM gets clean input and only has to do one thing: understand the content.

This is the architecture Datalab's platform is built on.

Usage:
    from marker_intake import process_pdf
    app = process_pdf(pdf_path, anthropic_client, model)
"""

import os
from marker.convert import convert_single_pdf
from marker.models import load_all_models
from models import ApplicationRecord
from intake_processor import process_document

_models = None


def _get_models():
    """Load Marker models once and cache them."""
    global _models
    if _models is None:
        print("  Loading Marker models (first run — downloads on initial use)...")
        _models = load_all_models()
        print("  Marker models ready.")
    return _models


def extract_markdown(pdf_path: str) -> str:
    """
    Use Marker to convert a PDF to clean markdown.

    Marker runs OCR if needed, detects page layout, preserves table structure,
    removes headers/footers, and outputs structured markdown. The result is
    significantly cleaner than pdfplumber or pypdf text extraction, especially
    for documents with tables or complex layouts.

    Returns:
        Markdown string ready for LLM extraction.
    """
    full_text, _, _ = convert_single_pdf(pdf_path, _get_models())
    return full_text


def process_pdf(
    pdf_path: str,
    client,
    model: str,
) -> ApplicationRecord:
    """
    Stage 0 (Marker edition): extract a structured ApplicationRecord from a PDF.

    Step 1: Marker converts the PDF to clean markdown (layout-aware).
    Step 2: Claude extracts compliance fields from the clean markdown.

    Args:
        pdf_path: Path to a PDF file.
        client:   Initialised Anthropic client.
        model:    Claude model name.

    Returns:
        ApplicationRecord — same typed output as the original Stage 0.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    print(f"  [Marker] Parsing: {os.path.basename(pdf_path)}")
    markdown = extract_markdown(pdf_path)
    print(f"  [Marker] Extracted {len(markdown):,} chars of clean markdown.")

    print(f"  [Claude] Extracting compliance fields...")
    return process_document(
        raw_text=markdown,
        client=client,
        model=model,
        source_label=os.path.basename(pdf_path),
    )

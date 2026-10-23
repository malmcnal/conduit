"""
surya_intake.py — Stage 0 (Surya edition)

Handles handwritten and scanned images using surya-ocr 0.4.5.
Surya runs a two-stage pipeline:
  1. Detection model — finds text line bounding boxes
  2. Recognition model — reads each line

This runs locally on CPU/MPS with no external server needed.

Note: surya 0.20.0 (VLM-based, better handwriting accuracy) requires
torch >=2.7.0 which does not support Intel Macs. If you're on Apple
Silicon, upgrade torch and install surya from ~/malachymcnally/surya.

Usage:
    python pipeline.py --image data/intake_scan.jpg
    python pipeline.py --image data/intake_scan.png --skip-backend
"""

import os
from pathlib import Path
from PIL import Image

from models import ApplicationRecord
from intake_processor import process_document

_det_model = None
_det_processor = None
_rec_model = None
_rec_processor = None


def _get_models():
    global _det_model, _det_processor, _rec_model, _rec_processor
    if _rec_model is None:
        print("  Loading Surya models (first run — downloads on first use)...")
        from surya.model.detection.segformer import load_model as load_det, load_processor as load_det_proc
        from surya.model.recognition.model import load_model as load_rec
        from surya.model.recognition.processor import load_processor as load_rec_proc
        _det_model     = load_det()
        _det_processor = load_det_proc()
        _rec_model     = load_rec()
        _rec_processor = load_rec_proc()
        print("  Surya models ready.")
    return _det_model, _det_processor, _rec_model, _rec_processor


def extract_text_from_image(image_path: str, langs: list[str] | None = None) -> str:
    """
    Run Surya OCR on an image and return clean, ordered plain text.

    Surya detects text line bounding boxes, then reads each line.
    Lines are already sorted top-to-bottom by Surya's sort_text_lines.
    """
    from surya.ocr import run_ocr

    if langs is None:
        langs = ["en"]

    image = Image.open(image_path).convert("RGB")
    det_model, det_processor, rec_model, rec_processor = _get_models()

    results = run_ocr(
        [image],
        [langs],
        det_model,
        det_processor,
        rec_model,
        rec_processor,
    )

    page = results[0]
    lines = [line.text.strip() for line in page.text_lines if line.text.strip()]
    return "\n".join(lines)


def process_image(
    image_path: str,
    client,
    model: str,
    langs: list[str] | None = None,
) -> ApplicationRecord:
    """
    Stage 0 (Surya edition): extract a structured ApplicationRecord from an image.

    Step 1: Surya detects and reads text lines (OCR).
    Step 2: Claude extracts compliance fields from the text.

    Args:
        image_path: Path to JPG, PNG, or other PIL-supported image.
        client:     Initialised Anthropic client.
        model:      Claude model name.
        langs:      Language codes for recognition (default: ["en"]).

    Returns:
        ApplicationRecord — same typed output as the other Stage 0 paths.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    print(f"  [Surya] Reading: {Path(image_path).name}")
    text = extract_text_from_image(image_path, langs)
    print(f"  [Surya] Extracted {len(text):,} chars across {len(text.splitlines())} lines.")

    if not text.strip():
        raise ValueError(
            f"Surya returned no text from {image_path}. "
            "Check image quality — ensure text is legible and well-lit."
        )

    print("  [Claude] Extracting compliance fields...")
    return process_document(
        raw_text=text,
        client=client,
        model=model,
        source_label=Path(image_path).name,
    )

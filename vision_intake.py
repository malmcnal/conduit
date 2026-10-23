"""
vision_intake.py — Stage 0 (Claude vision edition)

Default path for scanned, photographed and handwritten documents.

Surya 0.4.5 (the last version that runs on Intel Macs) reads printed text
well but produces noise on handwriting. Claude reads the image directly,
so there is no separate OCR step: one call goes from pixels to a validated
ApplicationRecord, using the same system prompt and validation as the
text and PDF paths.

The Surya path is still available with --ocr surya.

Usage:
    python pipeline.py --image data/blackt_CP.jpeg
    python pipeline.py --image data/intake_scan.png --ocr surya
"""

import base64
import os
from pathlib import Path

from models import ApplicationRecord
from intake_processor import extraction_instructions, extract_record

MEDIA_TYPES = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".webp": "image/webp",
}


def process_image(image_path: str, client, model: str) -> ApplicationRecord:
    """
    Stage 0 (Claude vision): extract a structured ApplicationRecord from an image.

    Args:
        image_path: Path to a JPG, PNG, GIF or WebP image.
        client:     Initialised Anthropic client.
        model:      Claude model name.

    Returns:
        ApplicationRecord — same typed output as the other Stage 0 paths.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    suffix = Path(image_path).suffix.lower()
    media_type = MEDIA_TYPES.get(suffix)
    if not media_type:
        raise ValueError(
            f"Unsupported image type '{suffix}'. Use one of: {', '.join(MEDIA_TYPES)}"
        )

    data = base64.standard_b64encode(Path(image_path).read_bytes()).decode("ascii")

    print(f"  [Claude] Reading image: {Path(image_path).name}")
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
        {"type": "text", "text": extraction_instructions(
            "the attached image. It may be a scan, a photo or handwritten notes; "
            "transcribe carefully before extracting"
        )},
    ]
    return extract_record(content, client, model, source_label=Path(image_path).name)

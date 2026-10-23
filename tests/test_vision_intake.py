"""Tests for the Claude vision Stage 0 path, with the API call faked."""

import json

import pytest

from vision_intake import process_image


RECORD = {
    "application_id": "DOC-20261023-001",
    "company_name": "Blackthorn Capital Partners",
    "industry": "Family Office",
    "aum_usd": 23980000,
    "primary_contact": "James Kelly",
    "contact_role": "Principal",
    "domicile": "Ireland",
    "num_jurisdictions": 1,
    "ownership_structure_notes": "Not stated",
    "beneficial_owners": "Undetermined",
    "source_of_funds": "Property sales and business exits",
    "regulatory_history": "None identified.",
    "additional_flags": "Principal is a retired Department of Finance civil servant (PEP).",
    "application_date": "2026-10-23",
}


class FakeText:
    def __init__(self, text):
        self.text = text


class FakeResponse:
    def __init__(self, text):
        self.content = [FakeText(text)]


class FakeMessages:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self.reply)


class FakeClient:
    def __init__(self, reply):
        self.messages = FakeMessages(reply)


def test_sends_image_block_and_validates_record(tmp_path):
    image = tmp_path / "note.jpeg"
    image.write_bytes(b"\xff\xd8fake-jpeg")
    client = FakeClient("```json\n" + json.dumps(RECORD) + "\n```")

    record = process_image(str(image), client, "claude-test")

    assert record.company_name == "Blackthorn Capital Partners"
    content = client.messages.calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/jpeg"
    assert content[1]["type"] == "text"


def test_rejects_unsupported_image_type(tmp_path):
    image = tmp_path / "scan.tiff"
    image.write_bytes(b"fake")
    with pytest.raises(ValueError, match="Unsupported image type"):
        process_image(str(image), FakeClient("{}"), "claude-test")


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        process_image(str(tmp_path / "nope.png"), FakeClient("{}"), "claude-test")


def test_invalid_model_output_raises_value_error(tmp_path):
    image = tmp_path / "note.png"
    image.write_bytes(b"fake")
    with pytest.raises(ValueError, match="Stage 0 extraction failed"):
        process_image(str(image), FakeClient("not json"), "claude-test")

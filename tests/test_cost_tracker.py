"""Tests for token accounting and the tracking proxy."""

import pytest

from cost_tracker import CostTracker, TrackingClient


class FakeUsage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class FakeResponse:
    def __init__(self, input_tokens, output_tokens):
        self.usage = FakeUsage(input_tokens, output_tokens)
        self.content = "response body"


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(1000, 500)


class FakeClient:
    def __init__(self):
        self.messages = FakeMessages()
        self.api_key = "sk-fake"


# ── CostTracker ───────────────────────────────────────────────────────────────

def test_starts_empty():
    t = CostTracker("claude-opus-4-5")
    assert t.input_tokens == 0
    assert t.output_tokens == 0
    assert t.total_tokens == 0
    assert t.estimated_cost_usd == 0


def test_records_usage_and_accumulates():
    t = CostTracker("claude-opus-4-5")
    t.record(FakeUsage(1000, 500))
    t.record(FakeUsage(200, 100))
    assert t.input_tokens == 1200
    assert t.output_tokens == 600
    assert t.total_tokens == 1800


def test_opus_pricing():
    """claude-opus-4-5 is $15/MTok in, $75/MTok out."""
    t = CostTracker("claude-opus-4-5")
    t.record(FakeUsage(1_000_000, 1_000_000))
    assert t.estimated_cost_usd == pytest.approx(90.00)


def test_haiku_is_cheaper_than_opus():
    opus = CostTracker("claude-opus-4-5")
    haiku = CostTracker("claude-haiku-4-5-20251001")
    for t in (opus, haiku):
        t.record(FakeUsage(100_000, 50_000))
    assert haiku.estimated_cost_usd < opus.estimated_cost_usd


def test_unknown_model_falls_back_to_conservative_pricing():
    """An unpriced model must not silently cost zero."""
    t = CostTracker("some-model-released-next-year")
    t.record(FakeUsage(1_000_000, 0))
    assert t.estimated_cost_usd == pytest.approx(15.00)


def test_usage_missing_fields_does_not_crash():
    t = CostTracker("claude-opus-4-5")
    t.record(object())
    assert t.total_tokens == 0


def test_summary_shape():
    t = CostTracker("claude-opus-4-5")
    t.record(FakeUsage(1000, 500))
    s = t.summary()
    assert set(s) == {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "estimated_cost_usd",
    }
    assert s["total_tokens"] == 1500
    assert s["estimated_cost_usd"] == pytest.approx(0.0525)


def test_display_line_contains_cost_and_tokens():
    t = CostTracker("claude-opus-4-5")
    t.record(FakeUsage(1000, 500))
    line = t.display_line()
    assert "$" in line
    assert "1,000 in" in line
    assert "500 out" in line


def test_reset_clears_counts_for_next_document():
    t = CostTracker("claude-opus-4-5")
    t.record(FakeUsage(1000, 500))
    t.reset()
    assert t.total_tokens == 0
    assert t.estimated_cost_usd == 0


# ── TrackingClient proxy ──────────────────────────────────────────────────────

def test_proxy_records_usage_from_create():
    tracker = CostTracker("claude-opus-4-5")
    client = TrackingClient(FakeClient(), tracker)
    client.messages.create(model="claude-opus-4-5", messages=[])
    assert tracker.input_tokens == 1000
    assert tracker.output_tokens == 500


def test_proxy_returns_response_unchanged():
    """Stage functions must see exactly what the real client returned."""
    tracker = CostTracker("claude-opus-4-5")
    client = TrackingClient(FakeClient(), tracker)
    response = client.messages.create(model="claude-opus-4-5", messages=[])
    assert response.content == "response body"


def test_proxy_forwards_kwargs_untouched():
    fake = FakeClient()
    client = TrackingClient(fake, CostTracker("claude-opus-4-5"))
    client.messages.create(model="m", max_tokens=512, stop_sequences=["END"])
    assert fake.messages.calls[0] == {
        "model": "m",
        "max_tokens": 512,
        "stop_sequences": ["END"],
    }


def test_proxy_accumulates_across_pipeline_stages():
    tracker = CostTracker("claude-opus-4-5")
    client = TrackingClient(FakeClient(), tracker)
    for _ in range(3):  # intake, risk, summary
        client.messages.create(model="m", messages=[])
    assert tracker.input_tokens == 3000
    assert tracker.output_tokens == 1500


def test_proxy_passes_through_other_attributes():
    client = TrackingClient(FakeClient(), CostTracker("claude-opus-4-5"))
    assert client.api_key == "sk-fake"

"""
cost_tracker.py — Token usage and cost tracking for Claude API calls.

Wraps anthropic.Anthropic to intercept every messages.create() call and
accumulate input/output tokens without changing any function signatures.

Usage:
    tracker = CostTracker(model)
    client = TrackingClient(anthropic_client, tracker)
    # pass `client` everywhere you'd pass `anthropic_client`
    # after processing: tracker.summary() → dict, tracker.display_line() → str
"""

# Pricing in USD per million tokens (input, output).
# Source: https://www.anthropic.com/pricing — update when pricing changes.
_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-5":              (15.00, 75.00),
    "claude-opus-4":                (15.00, 75.00),
    "claude-sonnet-4-5":            ( 3.00, 15.00),
    "claude-3-5-sonnet-20241022":   ( 3.00, 15.00),
    "claude-3-5-haiku-20241022":    ( 0.80,  4.00),
    "claude-haiku-4-5-20251001":    ( 0.80,  4.00),
}

_DEFAULT_PRICING = (15.00, 75.00)  # conservative fallback


class CostTracker:
    """Accumulates token usage and computes estimated cost for one document."""

    def __init__(self, model: str):
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0
        in_price, out_price = _PRICING.get(model, _DEFAULT_PRICING)
        self._in_per_tok  = in_price  / 1_000_000
        self._out_per_tok = out_price / 1_000_000

    def record(self, usage) -> None:
        """Add usage from one API response."""
        self.input_tokens  += getattr(usage, "input_tokens",  0)
        self.output_tokens += getattr(usage, "output_tokens", 0)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        return (self.input_tokens  * self._in_per_tok +
                self.output_tokens * self._out_per_tok)

    def summary(self) -> dict:
        """Dict ready for CSV output."""
        return {
            "input_tokens":       self.input_tokens,
            "output_tokens":      self.output_tokens,
            "total_tokens":       self.total_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
        }

    def display_line(self) -> str:
        """Single-line human-readable cost string for terminal output."""
        return (
            f"~${self.estimated_cost_usd:.4f}  "
            f"({self.input_tokens:,} in + {self.output_tokens:,} out = "
            f"{self.total_tokens:,} tokens)"
        )

    def reset(self) -> None:
        """Reset for the next document in a batch."""
        self.input_tokens  = 0
        self.output_tokens = 0


class _TrackingMessages:
    """Proxy for client.messages that records usage on every create() call."""

    def __init__(self, messages, tracker: CostTracker):
        self._messages = messages
        self._tracker  = tracker

    def create(self, **kwargs):
        response = self._messages.create(**kwargs)
        if hasattr(response, "usage"):
            self._tracker.record(response.usage)
        return response


class TrackingClient:
    """
    Drop-in wrapper around anthropic.Anthropic.

    Intercepts every messages.create() call, records token usage in the
    CostTracker, and returns the original response unchanged.
    All other attributes (e.g. client.api_key) are proxied transparently.
    """

    def __init__(self, client, tracker: CostTracker):
        self._client  = client
        self._tracker = tracker

    @property
    def messages(self) -> _TrackingMessages:
        return _TrackingMessages(self._client.messages, self._tracker)

    def __getattr__(self, name: str):
        return getattr(self._client, name)

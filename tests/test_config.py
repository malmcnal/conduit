"""Tests for the backend factory.

The pipeline never names a backend directly; it asks the factory for a client
that exposes setup() / find_existing() / push(). These tests cover the factory
contract that makes that indirection safe.
"""

import pytest

import config


def test_unknown_backend_raises_value_error():
    with pytest.raises(ValueError, match="Unknown backend"):
        config.get_backend_client("salesforce")


def test_unknown_backend_names_the_valid_options():
    """The error should tell the caller what to use instead."""
    with pytest.raises(ValueError) as exc:
        config.get_backend_client("")
    message = str(exc.value)
    assert "airtable" in message
    assert "monday" in message


def test_detect_backend_returns_a_known_name_or_none():
    backend = config.detect_backend()
    assert backend in {"airtable", "monday", None}


def test_backend_clients_share_the_same_interface():
    """Both clients must satisfy the contract the pipeline depends on."""
    from airtable_client import AirtableClient
    from monday_client import MondayClient

    for client_class in (AirtableClient, MondayClient):
        for method in ("setup", "find_existing", "push"):
            assert callable(getattr(client_class, method, None)), (
                f"{client_class.__name__} is missing {method}()"
            )

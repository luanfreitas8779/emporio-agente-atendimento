from datetime import date

import pytest

from src.config import reference_date


def test_default_reference_date_is_march_25_2026(monkeypatch):
    monkeypatch.delenv("REFERENCE_DATE", raising=False)

    assert reference_date() == date(2026, 3, 25)


def test_reference_date_can_be_set_by_the_environment(monkeypatch):
    monkeypatch.setenv("REFERENCE_DATE", "2026-04-10")

    assert reference_date() == date(2026, 4, 10)


def test_invalid_reference_date_states_the_expected_format(monkeypatch):
    monkeypatch.setenv("REFERENCE_DATE", "10/04/2026")

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        reference_date()

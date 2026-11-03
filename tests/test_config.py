from datetime import date

import pytest

from src.config import data_de_referencia


def test_data_de_referencia_padrao_e_25_de_marco_de_2026(monkeypatch):
    monkeypatch.delenv("DATA_DE_REFERENCIA", raising=False)

    assert data_de_referencia() == date(2026, 3, 25)


def test_data_de_referencia_pode_ser_configurada_pelo_ambiente(monkeypatch):
    monkeypatch.setenv("DATA_DE_REFERENCIA", "2026-04-10")

    assert data_de_referencia() == date(2026, 4, 10)


def test_data_de_referencia_invalida_informa_o_formato_esperado(monkeypatch):
    monkeypatch.setenv("DATA_DE_REFERENCIA", "10/04/2026")

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        data_de_referencia()

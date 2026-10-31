import pytest

from src.policies import SECOES, consultar_politicas


def test_informa_horario_de_sabado_e_domingo():
    horarios = consultar_politicas("horarios")

    assert "Sábado: 09:00 às 13:00" in horarios
    assert "Domingo e feriados: fechado" in horarios


def test_aceita_somente_as_secoes_definidas_na_especificacao():
    assert SECOES == (
        "sobre_a_loja",
        "horarios",
        "pagamentos",
        "trocas_e_devolucoes",
        "entregas",
        "promocoes",
        "atendimento",
        "garantia",
        "privacidade",
    )
    for secao in SECOES:
        assert consultar_politicas(secao)
    with pytest.raises(ValueError):
        consultar_politicas("fofocas")


def test_informa_o_endereco_da_loja():
    assert "Rua 14 de Maio, 3200 — Centro" in consultar_politicas("sobre_a_loja")


def test_informa_a_taxa_de_frete_em_campo_grande_abaixo_de_500_reais():
    entregas = consultar_politicas("entregas")

    assert "Frete grátis para pedidos acima de R$ 500,00" in entregas
    assert "taxa fixa de R$ 35,00" in entregas


def test_boquilha_de_sopro_nao_e_elegivel_para_troca():
    assert "Boquilhas de instrumentos de sopro" in consultar_politicas("trocas_e_devolucoes")


def test_promocao_encerrada_nao_pode_ser_prometida():
    assert "Uma promoção encerrada não pode ser prometida" in consultar_politicas("promocoes")


def test_349_90_em_6x_nao_atende_a_parcela_minima_de_80_reais():
    pagamentos = consultar_politicas("pagamentos", valor=349.90, parcelas=6)

    assert "máximo de 4x" in pagamentos
    assert "6x não atende" in pagamentos


def test_700_reais_em_7x_atende_a_parcela_minima_de_100_reais():
    pagamentos = consultar_politicas("pagamentos", valor=700, parcelas=7)

    assert "7x atende" in pagamentos
    assert "máximo de 7x de R$ 100,00" in pagamentos

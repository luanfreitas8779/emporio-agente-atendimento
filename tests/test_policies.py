import pytest

from src.policies import SECOES, consultar_politicas


def test_sabado_abre_das_9_as_13():
    assert "Sábado: 09:00 às 13:00" in consultar_politicas("horarios")


def test_domingo_e_feriados_a_loja_fecha():
    assert "Domingo e feriados: fechado" in consultar_politicas("horarios")


def test_de_segunda_a_sexta_abre_das_9_as_18():
    assert "Segunda a sexta-feira: 09:00 às 18:00" in consultar_politicas("horarios")


def test_informa_o_endereco_da_loja():
    assert "Rua 14 de Maio, 3200 — Centro" in consultar_politicas("sobre_a_loja")


def test_telefone_geral_e_whatsapp_sao_numeros_distintos():
    texto = consultar_politicas("sobre_a_loja")

    assert "Telefone: (67) 3341-4444" in texto
    assert "WhatsApp: (67) 3321-4500" in texto


def test_email_de_contato_e_escrito_sem_acento():
    assert "contato@emporiodamusica.com.br" in consultar_politicas("sobre_a_loja")


def test_loja_nao_vende_acessorios():
    texto = consultar_politicas("sobre_a_loja")

    assert "exclusivamente com instrumentos musicais" in texto
    assert "cordas, palhetas, cabos, cases, pedais ou amplificadores" in texto


def test_frete_em_campo_grande_abaixo_de_500_reais_tem_taxa_fixa_de_35():
    assert "abaixo de R$ 500,00 pagam taxa fixa de R$ 35,00" in consultar_politicas("entregas")


def test_frete_gratis_acima_de_500_reais():
    assert "Frete grátis para pedidos acima de R$ 500,00" in consultar_politicas("entregas")


def test_entrega_em_campo_grande_leva_de_1_a_3_dias_uteis():
    assert "1 a 3 dias úteis" in consultar_politicas("entregas")


def test_boquilha_de_instrumento_de_sopro_nao_e_elegivel_para_troca():
    assert "Boquilhas de instrumentos de sopro" in consultar_politicas("trocas_e_devolucoes")


def test_arrependimento_vale_7_dias_apos_o_recebimento_somente_em_compra_online():
    texto = consultar_politicas("trocas_e_devolucoes")

    assert "7 dias corridos após o recebimento" in texto
    assert "compras online" in texto


def test_troca_por_defeito_vale_30_dias_apos_a_compra():
    assert "30 dias corridos após a compra" in consultar_politicas("trocas_e_devolucoes")


def test_promocao_encerrada_nao_pode_ser_prometida():
    assert "Uma promoção encerrada não pode ser prometida" in consultar_politicas("promocoes")


def test_desconto_de_pix_nao_se_aplica_a_preco_promocional():
    assert "desconto de PIX não se aplica a preços promocionais" in consultar_politicas("promocoes")


def test_secao_fora_da_lista_e_recusada():
    with pytest.raises(ValueError, match="fofocas"):
        consultar_politicas("fofocas")


def test_pix_tem_5_por_cento_de_desconto_sobre_o_preco_de_tabela():
    assert "PIX: pagamento à vista, com 5% de desconto sobre o preço de tabela" in consultar_politicas("pagamentos")


def test_parcela_minima_de_4x_a_6x_e_80_reais_conforme_a_secao_especifica():
    assert "De 4x a 6x: parcela mínima de R$ 80,00" in consultar_politicas("pagamentos")


def test_parcela_minima_de_7x_a_12x_e_100_reais():
    assert "De 7x a 12x: parcela mínima de R$ 100,00" in consultar_politicas("pagamentos")


def test_parcela_minima_de_ate_3x_e_50_reais():
    assert "De 1x a 3x: parcela mínima de R$ 50,00" in consultar_politicas("pagamentos")


def test_349_90_em_6x_nao_atende_a_parcela_minima_e_o_maximo_e_4x():
    texto = consultar_politicas("pagamentos", valor=349.90, parcelas=6)

    assert "6x não atende" in texto
    assert "máximo de 4x" in texto


def test_700_reais_em_7x_atende_a_parcela_minima_de_100_reais():
    texto = consultar_politicas("pagamentos", valor=700, parcelas=7)

    assert "7x atende" in texto
    assert "máximo de 7x de R$ 100,00" in texto


def test_reclamacao_tem_retorno_em_ate_24_horas_uteis():
    assert "24 horas úteis" in consultar_politicas("atendimento")


def test_atendimento_nao_indica_lojas_parceiras():
    assert "sem indicar lojas" in consultar_politicas("atendimento")


def test_garantia_legal_e_de_90_dias_a_partir_do_recebimento():
    assert "90 dias" in consultar_politicas("garantia")
    assert "recebimento" in consultar_politicas("garantia")


def test_troca_por_defeito_e_garantia_legal_sao_regras_distintas():
    assert "regra distinta da garantia legal" in consultar_politicas("garantia")


def test_cliente_pode_pedir_a_exclusao_dos_dados():
    texto = consultar_politicas("privacidade")

    assert "LGPD" in texto
    assert "exclusão dos dados" in texto


def test_toda_secao_da_especificacao_tem_conteudo():
    for secao in SECOES:
        assert consultar_politicas(secao).strip()


def test_mais_de_12_parcelas_nao_sao_oferecidas():
    texto = consultar_politicas("pagamentos", valor=5000, parcelas=13)

    assert "até 12x" in texto
    assert "13x" in texto
    assert "atende à parcela mínima" not in texto


@pytest.mark.parametrize("valor, parcelas", [(0, 3), (-10, 3), (100, 0), (100, -2)])
def test_recusa_valor_ou_parcelas_nao_positivos(valor, parcelas):
    with pytest.raises(ValueError):
        consultar_politicas("pagamentos", valor=valor, parcelas=parcelas)

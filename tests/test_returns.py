from datetime import date

from src.returns import avaliar_devolucao


def test_compra_online_tres_dias_apos_a_entrega_esta_dentro_do_prazo_de_arrependimento(conexao):
    # Pedido 7 (cliente 14): entrega estimada em 17/02/2026, prazo de 7 dias até 24/02/2026.
    veredito = avaliar_devolucao(
        conexao, cliente_id=14, numero=7, motivo="arrependimento", canal="online",
        hoje=date(2026, 2, 20),
    )

    assert veredito.resultado == "dentro_do_prazo"
    assert [(r.nome, r.resultado, r.prazo_ate) for r in veredito.regras] == [
        ("arrependimento", "dentro_do_prazo", "24/02/2026")
    ]

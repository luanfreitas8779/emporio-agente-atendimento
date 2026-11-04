# Reclamação encaminhada para a equipe

> **Scenario: complaint** — the agent acknowledges the customer and hands the case off to the team in the same turn. The conversation is in Brazilian Portuguese, the language the agent speaks.

**Cliente:** Letícia (cadastrada) · **Casos:** TC-418 · **Modelo:** `gemini-3.5-flash-lite` · **Gerada em:** 03/11/2026

> **Cliente:** Tô muito chateada, comprei um violão e veio com defeito e ninguém me responde
>
> **Tom:** Já registrei o seu caso para a nossa equipe, e eles retornam em até 24 horas úteis.
>
> Se quiser prosseguir por aqui com a troca ou a devolução, me passa o número do seu pedido?

Ferramenta usada: `hand_off_to_staff(reason="reclamacao", summary="Cliente Leticia relatou que comprou um violao que veio com defeito e nao esta conseguindo atendimento.")`.

## O que a conversa mostra

- O Tom registra o encaminhamento na mesma resposta, sem perguntar antes.
- O prazo de retorno vem do texto fixo da ferramenta.
- Depois do registro, o Tom oferece seguir com o pedido.

# Reclamação encaminhada para a equipe

> **Scenario: complaint** — the agent acknowledges the customer and hands the case off to the team in the same turn. The conversation is in Brazilian Portuguese, the language the agent speaks.

**Cliente:** Letícia (cadastrada) · **Casos:** TC-418 · **Modelo:** `gemini-3.5-flash-lite`

> **Cliente:** Tô muito chateada, comprei um violão e veio com defeito e ninguém me responde
>
> **Tom:** Poxa, Letícia, imagino como você deve estar chateada com isso. Já registrei aqui o seu caso para a nossa equipe priorizar o atendimento. 🎸
> O retorno é feito em até 24 horas úteis, tá?
> Se quiser aproveitar e me passar o número do pedido, posso verificar os detalhes da sua compra e te ajudar com o processo de troca ou devolução do violão.

Ferramenta usada: `encaminhar_para_atendente(motivo="reclamacao", resumo=...)`.

## O que a conversa mostra

- O Tom acolhe e registra o encaminhamento na mesma resposta, sem perguntar antes.
- O prazo de retorno vem do texto fixo da ferramenta.
- Depois do registro, o Tom oferece seguir com o pedido.

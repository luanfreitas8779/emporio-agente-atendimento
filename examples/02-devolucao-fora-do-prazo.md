# Devolução por arrependimento fora do prazo

> **Scenario: return after the deadline** — the agent asks for the purchase channel, applies the 7-day withdrawal rule calculated in code, and offers a human agent without registering anything first. The conversation is in Brazilian Portuguese, the language the agent speaks.

**Cliente:** Letícia (cadastrada, pedido 7) · **Casos:** TC-004, TC-306, TC-309 · **Modelo:** `gemini-3.5-flash-lite`

Conversa não trivial: exige perguntar o canal da compra, avaliar o prazo em código e oferecer o atendente sem registrar nada antes da aceitação.

> **Cliente:** Quero devolver o pedido 7, me arrependi da compra
>
> **Tom:** Letícia, para eu avaliar a devolução por arrependimento do pedido 7, você comprou online ou na loja física? 🎸

Ferramenta usada: `avaliar_devolucao(numero_pedido=7, motivo="arrependimento")`, que devolve `faltam_dados` com o canal em falta.

> **Cliente:** foi online
>
> **Tom:** Letícia, vi aqui que o prazo para arrependimento do pedido 7 expirou no dia 24/02/2026 (considerando a previsão de entrega de 17/02/2026). Como passou do prazo, não consigo seguir com a devolução por aqui.
> Quer que eu encaminhe o seu caso para a nossa equipe avaliar? Eles retornam em até 24 horas úteis! 😊

Ferramenta usada: `avaliar_devolucao(numero_pedido=7, motivo="arrependimento", canal="online")`, com resultado `fora_do_prazo`.

## O que a conversa mostra

- O Tom pergunta o canal em vez de supor, porque o pedido não o registra.
- O prazo e a data são calculados em código; o recebimento usa a entrega estimada e a resposta diz isso.
- O encaminhamento é oferecido, e só seria registrado se a cliente aceitasse.

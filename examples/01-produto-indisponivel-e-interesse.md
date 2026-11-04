# Produto indisponível, erro de digitação e registro de interesse

> **Scenario: unavailable product** — the search tolerates a typo, and the agent registers the customer's interest without promising a notice or a restock date. The conversation is in Brazilian Portuguese, the language the agent speaks.

**Cliente:** Ana (cadastrada) · **Casos:** TC-101, TC-401 · **Modelo:** `gemini-3.5-flash-lite` · **Gerada em:** 03/11/2026

> **Cliente:** gianini gf 3d tem aí?
>
> **Tom:** O Giannini GF-3D Dreadnought Sunburst está indisponível no momento.
>
> Se quiser, posso registrar seu interesse para que o aviso fique anotado — lembrando que isso não reserva o produto nem garante aviso ou data de reposição. Quer que eu anote?

Ferramenta usada: `search_products(search_term="gianini gf 3d")`.

> **Cliente:** Quero ser avisado quando chegar
>
> **Tom:** Prontinho, seu interesse ficou anotado! Só lembrando que isso não reserva o produto e não garante aviso nem data de reposição.

Ferramenta usada: `register_interest(product_id=96)`.

## O que a conversa mostra

- A busca aproximada encontra o produto apesar da letra a menos em "gianini".
- A disponibilidade vem da ferramenta; o Tom não confirma estoque.
- Mesmo com o cliente pedindo para ser avisado, o registro de interesse não promete aviso, data nem reserva.

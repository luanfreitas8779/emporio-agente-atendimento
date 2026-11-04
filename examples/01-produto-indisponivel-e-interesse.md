# Produto indisponível, erro de digitação e registro de interesse

> **Scenario: unavailable product** — the search tolerates a typo, and the agent registers the customer's interest without promising a restock date. The conversation is in Brazilian Portuguese, the language the agent speaks.

**Cliente:** Ana (cadastrada) · **Casos:** TC-101, TC-401 · **Modelo:** `gemini-3.5-flash-lite`

> **Cliente:** gianini gf 3d tem aí?
>
> **Tom:** Opa, Ana! O Giannini GF-3D Dreadnought Sunburst está sem estoque no momento. 🎸
> Quer que eu te avise se ele pintar por aqui de novo ou prefere dar uma olhada em outros violões disponíveis?

Ferramenta usada: `search_products(search_term="gianini gf 3d")`.

> **Cliente:** Quero ser avisado quando chegar
>
> **Tom:** Deixei seu interesse anotado, Ana! Assim que tivermos novidades, você fica sabendo.
> Quer dar uma olhada em outros violões que temos disponíveis por aqui?

Ferramenta usada: `registrar_interesse(product_id=96)`.

## O que a conversa mostra

- A busca aproximada encontra o produto apesar da letra a menos em "gianini".
- A disponibilidade vem da ferramenta; o Tom não confirma estoque.
- O registro de interesse não promete data nem reserva o produto.

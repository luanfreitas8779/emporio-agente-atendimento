# Parcelamento calculado em código

**Cliente:** Ana (cadastrada) · **Casos relacionados:** TC-204 e TC-205, que cobrem a parcela mínima; esta conversa usa o limite de 12 parcelas · **Modelo:** `gemini-3.5-flash-lite`

> **Cliente:** Dá pra parcelar o Takamine GD20 em 12x?
>
> **Tom:** Dá sim, Ana! O Takamine GD20 Dreadnought Natural sai por R$ 2.199,00 e dá para parcelar em até 12x sem juros de R$ 183,25 no cartão de crédito. 🎵

Ferramentas usadas: `buscar_produtos(termo="Takamine GD20")` e `consultar_politicas(secao="pagamentos", valor=2199, parcelas=12)`.

## O que a conversa mostra

- O preço vem do catálogo e o valor da parcela vem da política, ambos calculados em código.
- O modelo encadeia duas ferramentas na mesma pergunta.

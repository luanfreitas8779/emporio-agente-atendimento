# Busca por orçamento, fora de escopo, status do pedido e endereço

> **Scenario: budget, scope, order status, and address** — colloquial search with a price limit, refusal of accessories, order tracking with the delay calculated in code, and the store address from the policies. The conversation is in Brazilian Portuguese, the language the agent speaks.

**Cliente:** Ana (cadastrada) · **Casos:** TC-001, TC-002, TC-301, TC-440, TC-501 · **Modelo:** `gemini-3.5-flash-lite` · **Gerada em:** 03/11/2026

Cada trecho é uma conversa curta e independente.

## Linguagem coloquial e filtro de preço

> **Cliente:** me vê um violão até mil conto
>
> **Tom:** Temos estes violões disponíveis:
>
> - Giannini GF-1R Aço Folk Sunburst: R$ 579,90 (PIX: R$ 550,91)
> - Giannini GN-15 Nylon Cedr Natural: R$ 689,00 (PIX: R$ 654,55)
> - Rozini RC-104 Nylon Estudante: R$ 459,90 (PIX: R$ 436,91)
> - Shelby SGD-195E Elétrico Aço Sunburst: R$ 799,00 (PIX: R$ 759,05)
> - Shelby SN-100 Folk Aço Preto: R$ 549,00 (PIX: R$ 521,55)
> - Tagima Dallas Tuner Aço Natural: R$ 749,00 (PIX: R$ 711,55)
> - Tagima Memphis AC-39 Nylon Natural: R$ 429,90 (PIX: R$ 408,41)
> - Tagima TW-7 7 Cordas Aço Natural: R$ 999,00 (PIX: R$ 949,05)
> - Tagima Woodstock Dreadnought Natural: R$ 899,00 (PIX: R$ 854,05)
> - Yamaha C40 Nylon Natural: R$ 599,90 (PIX: R$ 569,91)
> - Yamaha C70 Nylon Natural: R$ 849,00 (PIX: R$ 806,55)
> - Yamaha F310 Aço Natural: R$ 699,90 (PIX: R$ 664,91)
>
> Qual deles você prefere?

Ferramenta usada: `search_products(search_term="violão", max_price=1000, only_available=True)`, chamada duas vezes com os mesmos argumentos. Os 12 violões são o resultado esperado pelo TC-001, sem o Giannini GF-3D (sem estoque) e o Shelby SN-7C (fora de catálogo).

## Produto fora do escopo da loja

> **Cliente:** Vocês vendem encordoamento?
>
> **Tom:** Oi, Ana! A Empório da Música trabalha apenas com instrumentos. Se precisar de ajuda para escolher um violão, guitarra ou outro instrumento, é só falar!

Nenhuma ferramenta foi usada.

## Status do pedido

> **Cliente:** Cadê meu pedido?
>
> **Tom:** Ana, o pedido 8 (Kala KA-C Concert Mogno) está com o status enviado e o código de rastreio é BRJL5544332BR.
>
> A entrega estimada era 28/02/2026 e o pedido segue como enviado: 25 dias de atraso.
>
> Como há esse atraso, quer que eu chame um atendente para ajudar a verificar o que aconteceu?

Ferramenta usada: `get_my_orders()`; o cliente vem do telefone da sessão, e o atraso é calculado em código a partir da data de referência (25/03/2026).

## Endereço da loja

> **Cliente:** Qual o endereço da loja?
>
> **Tom:** Fica na Rua 14 de Maio, 3200, no Centro de Campo Grande/MS.

Ferramenta usada: `get_policies(section="sobre_a_loja")`.

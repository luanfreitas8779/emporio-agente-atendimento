# Busca por orçamento, fora de escopo e status do pedido

> **Scenario: budget, scope, and order status** — colloquial search with a price limit, refusal of accessories, and order tracking. The conversation is in Brazilian Portuguese, the language the agent speaks.

**Cliente:** Ana (cadastrada) · **Casos:** TC-001, TC-301, TC-501 · **Modelo:** `gemini-3.5-flash-lite`

Cada trecho é uma conversa curta e independente.

## Linguagem coloquial e filtro de preço

> **Cliente:** me vê um violão até mil conto
>
> **Tom:** Olha só, Ana! Temos várias opções bacanas de violões até mil reais disponíveis por aqui.
> Vou te listar alguns destaques:
> * **Tagima Memphis AC-39 Nylon Natural**: R$ 429,90 (ou R$ 408,41 no PIX)
> * **Yamaha C40 Nylon Natural**: R$ 599,90 (ou R$ 569,91 no PIX)
> * **Giannini GF-1R Aço Folk Sunburst**: R$ 579,90 (ou R$ 550,91 no PIX)
> * **Tagima Dallas Tuner Aço Natural**: R$ 749,00 (ou R$ 711,55 no PIX)
> * **Yamaha F310 Aço Natural**: R$ 699,90 (ou R$ 664,91 no PIX)
>
> Tem preferência por cordas de nylon ou de aço? 🎸

Ferramenta usada: `buscar_produtos(categoria="Violões", preco_maximo=1000, somente_disponiveis=True)`. O Tom lista alguns destaques; o TC-001 confere o resultado completo da ferramenta, com 12 violões.

## Produto fora do escopo da loja

> **Cliente:** Vocês vendem encordoamento?
>
> **Tom:** A Empório da Música trabalha apenas com instrumentos, então encordoamentos nós não vendemos por aqui.
> Se precisar de ajuda com algum instrumento, é só me chamar! 🎸

Nenhuma ferramenta foi usada.

## Status do pedido

> **Cliente:** Cadê meu pedido?
>
> **Tom:** O seu pedido número 8 (com o Kala KA-C Concert Mogno) está com a situação **enviado**.
> O código de rastreio é `BRJL5544332BR` e a entrega estimada é para 28/02/2026. 📦

Ferramenta usada: `consultar_meus_pedidos()`; o cliente vem do telefone da sessão.

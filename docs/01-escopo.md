# Visão e escopo

| Campo | Valor |
|---|---|
| Projeto | Agente de atendimento da Empório da Música |
| Versão do documento | 0.2 |
| Situação | Em revisão |
| Data-alvo de entrega | 02/11/2026, 18:00 (UTC-3) |

## 1. Contexto

A Empório da Música é uma loja especializada em instrumentos musicais, fundada em 2008 em Campo Grande/MS. O atendimento é feito pela equipe da loja, que concentra boa parte do tempo em perguntas recorrentes sobre horários, status de pedidos, preços e disponibilidade.

Esse volume reduz o tempo disponível para atendimentos que exigem análise humana e aumenta o risco de respostas inconsistentes.

## 2. Objetivos

| ID | Objetivo |
|---|---|
| OBJ-01 | Responder perguntas recorrentes por texto, com base nos dados e políticas da loja |
| OBJ-02 | Reduzir a carga da equipe, sem substituir o atendimento humano em casos sensíveis |
| OBJ-03 | Garantir que preços, estoque, pedidos e prazos venham de fontes verificadas |
| OBJ-04 | Dar continuidade ao atendimento quando o cliente retorna em outro dia |

## 3. Partes interessadas

| Parte | Interesse |
|---|---|
| Clientes | Respostas rápidas, corretas e acolhedoras |
| Equipe de atendimento | Menos perguntas repetitivas e casos encaminhados com contexto |
| Gestão da loja | Consistência com as políticas e proteção dos dados de clientes |
| Equipe técnica | Solução simples de operar, testar e evoluir |

## 4. Escopo

### 4.1 Incluído no MVP

- Atendimento por texto em interface web.
- Consulta de produtos, preços, estoque e promoções ativas.
- Consulta de pedidos do cliente identificado.
- Consulta das políticas da loja.
- Tratamento de pedidos fora do escopo.
- Persistência do histórico e de interesses por produto.
- Registro de reclamações e encaminhamentos para a equipe.

### 4.2 Fora do MVP

- Integração com o WhatsApp.
- Autenticação forte de clientes.
- Compra, pagamento ou alteração de pedidos pelo chat.
- Notificação automática de reposição de estoque.
- Integração com sistemas de produção da loja.
- Painel administrativo.
- Implantação em produção.

## 5. Requisitos funcionais

| ID | Requisito | Prioridade |
|---|---|---|
| RF-01 | O agente deve assumir a persona definida na [especificação do agente](04-agente.md) | Alta |
| RF-02 | O agente deve decidir entre responder, consultar dados, consultar políticas ou encaminhar | Alta |
| RF-03 | O sistema deve buscar produtos por nome, categoria e preço máximo | Alta |
| RF-04 | O sistema deve calcular preço final segundo as regras de promoção e PIX | Alta |
| RF-05 | O sistema deve mostrar somente pedidos do cliente identificado | Alta |
| RF-06 | O agente deve aplicar políticas de troca, devolução, garantia, pagamento e frete | Alta |
| RF-07 | O agente deve recusar assuntos fora do escopo e redirecionar pedidos de acessórios | Alta |
| RF-08 | O sistema deve persistir o histórico por telefone | Alta |
| RF-09 | O sistema deve registrar e recuperar interesses em produtos indisponíveis | Alta |
| RF-10 | O agente deve encaminhar reclamações e casos sem resposta segura | Média |
| RF-11 | A interface deve mostrar as ferramentas usadas em cada resposta | Baixa |

## 6. Requisitos não funcionais

| ID | Categoria | Requisito |
|---|---|---|
| RNF-01 | Confiabilidade | Dados factuais devem vir de ferramentas, nunca da memória do modelo |
| RNF-02 | Privacidade | O isolamento de dados por cliente deve ser garantido em código |
| RNF-03 | Segurança | Chaves de API não podem ser versionadas |
| RNF-04 | Manutenibilidade | O provedor e o modelo devem ser configuráveis |
| RNF-05 | Testabilidade | A suíte padrão deve rodar sem chave de API e sem consumir cota |
| RNF-06 | Custo | O MVP deve operar dentro do plano gratuito do Gemini |
| RNF-07 | Resiliência | Limites de uso devem gerar nova tentativa ou mensagem clara ao cliente |
| RNF-08 | Portabilidade | O ambiente deve ser recriado a partir do repositório e de um único comando de carga |

## 7. Critérios de aceite

| ID | Critério | Requisitos |
|---|---|---|
| CA-01 | A busca por violões até R$ 1.000 retorna 12 opções disponíveis, sem itens esgotados ou descontinuados | RF-03 |
| CA-02 | O endereço da loja é informado a partir da política revisada | RF-06 |
| CA-03 | O preço do Takamine GD20 é informado como R$ 2.199,00 | RF-03, RF-04 |
| CA-04 | Pedidos de devolução consideram status, datas, motivo e canal de compra | RF-06 |
| CA-05 | Uma mensagem não consegue acessar pedidos de outro cliente | RF-05, RNF-02 |
| CA-06 | Pedidos fora do escopo são recusados sem informações inventadas | RF-07 |
| CA-07 | O agente nunca informa uma data de reposição sem dado de origem | RF-09, RNF-01 |
| CA-08 | Em nova sessão, "chegou o violão?" é associado ao interesse salvo e ao estoque atual | RF-08, RF-09 |
| CA-09 | A suíte automatizada padrão passa sem chave de API | RNF-05 |

## 8. Premissas e restrições

### Premissas

- A data de referência do sistema é configurável, com valor padrão 2026-03-25.
- O telefone informado na interface representa o identificador que seria entregue pelo canal de mensagens.
- `products.csv` é a fonte oficial do catálogo.
- A cota gratuita do Gemini foi medida em 01/11/2026: 15 requisições por minuto e 500 por dia, por projeto e modelo.

### Restrições

- Python como linguagem principal.
- Esforço estimado entre 10 e 15 horas.
- Uso do plano gratuito do Gemini.

## 9. Riscos

| ID | Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|---|
| R-01 | Cota gratuita insuficiente | Alta | Alto | Testes com modelo simulado, histórico limitado, nova tentativa e modelo configurável |
| R-02 | Modelo inventar dados | Média | Alto | Dados obtidos por ferramentas e regras explícitas de resposta |
| R-03 | Exposição de dados de clientes | Baixa | Alto | Cliente definido pela sessão e consultas parametrizadas |
| R-04 | Manipulação por prompt injection | Média | Alto | Regras críticas aplicadas em código, não apenas no prompt |
| R-05 | Dependências incompatíveis com Python 3.14 | Média | Médio | Validar versões na configuração do ambiente |
| R-06 | Inconsistências nos dados de origem | Alta | Médio | Regras de tratamento descritas em [Dados](03-dados.md) |

## 10. Documentos relacionados

- [Arquitetura](02-arquitetura.md)
- [Dados](03-dados.md)
- [Especificação do agente](04-agente.md)
- [Plano de testes e cronograma](05-testes-e-roteiro.md)

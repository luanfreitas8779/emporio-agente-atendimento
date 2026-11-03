# Vision and scope

| Field | Value |
|---|---|
| Project | Empório da Música customer service agent |
| Document version | 0.2 |
| Status | Under review |
| Target delivery date | November 2, 2026, 18:00 (UTC-3) |

## 1. Context

Empório da Música is a store specialized in musical instruments, founded in 2008 in Campo Grande, Mato Grosso do Sul, Brazil. Customer service is handled by the store team, which spends much of its time on recurring questions about opening hours, order status, prices, and availability.

This volume reduces the time available for cases that require human judgment and increases the risk of inconsistent answers.

## 2. Goals

| ID | Goal |
|---|---|
| OBJ-01 | Answer recurring questions by text, based on the store's data and policies |
| OBJ-02 | Reduce the team's workload without replacing human service in sensitive cases |
| OBJ-03 | Ensure that prices, stock, orders, and deadlines come from verified sources |
| OBJ-04 | Provide continuity when the customer returns on another day |

## 3. Stakeholders

| Stakeholder | Interest |
|---|---|
| Customers | Fast, correct, and friendly answers |
| Customer service team | Fewer repetitive questions and cases handed off with context |
| Store management | Consistency with the policies and protection of customer data |
| Technical team | A solution that is simple to operate, test, and evolve |

## 4. Scope

### 4.1 Included in the MVP

- Text-based customer service in a web interface.
- Lookup of products, prices, stock, and active promotions.
- Lookup of the identified customer's orders.
- Lookup of the store policies.
- Handling of out-of-scope requests.
- Persistence of the history and of product interests.
- Registration of complaints and handoffs to the team.

### 4.2 Out of the MVP

- WhatsApp integration.
- Strong customer authentication.
- Purchases, payments, or order changes through the chat.
- Automatic restock notifications.
- Integration with the store's production systems.
- Admin dashboard.
- Production deployment.

## 5. Functional requirements

| ID | Requirement | Priority |
|---|---|---|
| RF-01 | The agent must adopt the persona defined in the [agent specification](04-agent.md) | High |
| RF-02 | The agent must decide between answering, querying data, looking up policies, or handing off | High |
| RF-03 | The system must search products by name, category, and maximum price | High |
| RF-04 | The system must calculate the final price according to the promotion and PIX rules | High |
| RF-05 | The system must show only the identified customer's orders | High |
| RF-06 | The agent must apply the exchange, return, warranty, payment, and shipping policies | High |
| RF-07 | The agent must decline out-of-scope topics and redirect requests for accessories | High |
| RF-08 | The system must persist the history by phone number | High |
| RF-09 | The system must register and retrieve interests in unavailable products | High |
| RF-10 | The agent must hand off complaints and cases without a safe answer | Medium |
| RF-11 | The interface must show the tools used in each answer | Low |

## 6. Non-functional requirements

| ID | Category | Requirement |
|---|---|---|
| RNF-01 | Reliability | Factual data must come from tools, never from the model's memory |
| RNF-02 | Privacy | Data isolation between customers must be enforced in code |
| RNF-03 | Security | API keys must not be committed |
| RNF-04 | Maintainability | The provider and the model must be configurable |
| RNF-05 | Testability | The default suite must run without an API key and without consuming quota |
| RNF-06 | Cost | The MVP must operate within the Gemini free tier |
| RNF-07 | Resilience | Rate limits must trigger a retry or a clear message to the customer |
| RNF-08 | Portability | The environment must be recreated from the repository and a single load command |

## 7. Acceptance criteria

| ID | Criterion | Requirements |
|---|---|---|
| CA-01 | The search for acoustic guitars up to R$ 1.000 returns 12 available options, without out-of-stock or discontinued items | RF-03 |
| CA-02 | The store address is provided from the reviewed policy | RF-06 |
| CA-03 | The price of the Takamine GD20 is given as R$ 2.199,00 | RF-03, RF-04 |
| CA-04 | Return requests take into account status, dates, reason, and purchase channel | RF-06 |
| CA-05 | A message cannot access another customer's orders | RF-05, RNF-02 |
| CA-06 | Out-of-scope requests are declined without invented information | RF-07 |
| CA-07 | The agent never gives a restock date without source data | RF-09, RNF-01 |
| CA-08 | In a new session, "chegou o violão?" ("has the guitar arrived?") is linked to the saved interest and to the current stock | RF-08, RF-09 |
| CA-09 | The default automated suite passes without an API key | RNF-05 |

## 8. Assumptions and constraints

### Assumptions

- The system's reference date is configurable, with a default value of 2026-03-25.
- The phone number entered in the interface stands for the identifier the messaging channel would provide.
- `products.csv` is the official catalog source.
- The Gemini free quota was measured on November 1, 2026: 15 requests per minute and 500 per day, per project and model.

### Constraints

- Python as the main language.
- Estimated effort between 10 and 15 hours.
- Use of the Gemini free tier.

## 9. Risks

| ID | Risk | Probability | Impact | Mitigation |
|---|---|---|---|---|
| R-01 | Insufficient free quota | High | High | Tests with a simulated model, limited history, retries, and a configurable model |
| R-02 | The model invents data | Medium | High | Data obtained through tools and explicit answer rules |
| R-03 | Exposure of customer data | Low | High | Customer defined by the session and parameterized queries |
| R-04 | Manipulation through prompt injection | Medium | High | Critical rules enforced in code, not only in the prompt |
| R-05 | Dependencies incompatible with Python 3.14 | Medium | Medium | Validate versions when setting up the environment |
| R-06 | Inconsistencies in the source data | High | Medium | Handling rules described in [Data](03-data.md) |

## 10. Related documents

- [Architecture](02-architecture.md)
- [Data](03-data.md)
- [Agent specification](04-agent.md)
- [Test plan and schedule](05-test-plan.md)

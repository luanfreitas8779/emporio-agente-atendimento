# Empório da Música: agente de atendimento

Agente de atendimento por texto em Python. Consulte o [README](README.md) e a pasta `docs/` antes de propor mudanças.

## Convenções

- Escrever documentação, tickets e mensagens de commit em português, em tom técnico.
- Seguir as decisões registradas em `docs/02-arquitetura.md`.
- Fazer commits pequenos, no padrão Conventional Commits.
- Desenvolver toda issue com a skill `tdd`: invocá-la antes de começar e trabalhar em ciclos de um teste que falha, a implementação mínima e a repetição. Nenhum teste é escrito depois do código.
- Nunca versionar chaves de API ou o banco local.

## Agent skills

### Issue tracker

Specs e tickets ficam no GitHub Issues deste repositório. Consulte `docs/agents/issue-tracker.md`.

### Domain docs

Repositório de contexto único, com as ADRs em `docs/02-arquitetura.md`. Consulte `docs/agents/domain.md`.

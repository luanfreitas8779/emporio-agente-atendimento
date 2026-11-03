# Empório da Música: customer service agent

Text-based customer service agent in Python. Read the [README](README.md) and the `docs/` folder before proposing changes.

## Conventions

- Write documentation, code (identifiers, comments, and docstrings), tickets, and commit messages in English, in a technical tone.
- Keep in Brazilian Portuguese everything the customer or the model reads: answers, fixed messages, interface text, the system prompt, tool descriptions, and fixed tool returns (see the README, Assumptions).
- Follow the decisions recorded in `docs/02-architecture.md`.
- Make small commits, following Conventional Commits.
- Develop every issue with the `tdd` skill: invoke it before starting and work in cycles of one failing test, the minimal implementation, and repetition. No test is written after the code.
- Never commit API keys or the local database.

## Agent skills

### Issue tracker

Specs and tickets live in this repository's GitHub Issues. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context repository, with the ADRs in `docs/02-architecture.md`. See `docs/agents/domain.md`.

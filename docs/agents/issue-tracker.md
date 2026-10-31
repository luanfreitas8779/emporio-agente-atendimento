# Issue tracker: GitHub

Specs e tickets deste repositório ficam no GitHub Issues. Todas as operações usam o `gh`.

## Convenções

- **Criar:** `gh issue create --title "..." --body "..."`.
- **Ler:** `gh issue view <número> --json number,title,body,labels,comments`.
- **Listar:** `gh issue list --state open --json number,title,body,labels`.
- **Criar ticket de uma spec:** `gh issue create --parent <spec> ...`.
- **Declarar bloqueio:** `gh issue create --blocked-by <n>,<n> ...` ou `gh issue edit <ticket> --add-blocked-by <bloqueador>`.
- **Contar bloqueios abertos:** `gh api repos/{owner}/{repo}/issues/<n> --jq .issue_dependencies_summary.blocked_by`.
- **Comentar:** `gh issue comment <número> --body "..."`.
- **Alterar rótulos:** `gh issue edit <número> --add-label "..."` ou `--remove-label "..."`.
- **Fechar:** comentar a resolução e depois executar `gh issue close <número>`.

Um ticket está desbloqueado quando todos os bloqueadores estão fechados.

## Rótulos

Specs e tickets prontos usam o rótulo `ready-for-agent`.

## Pull requests como entrada

**Não.** Pull requests externos não entram na fila de tickets.

## Quando uma skill pedir para publicar

Criar uma issue neste repositório.

## Quando uma skill pedir o ticket relacionado

Ler a issue conforme a seção de convenções.

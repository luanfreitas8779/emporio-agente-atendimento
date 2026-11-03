# Issue tracker: GitHub

Specs and tickets for this repository live in GitHub Issues. All operations use `gh`.

## Conventions

- **Create:** `gh issue create --title "..." --body "..."`.
- **Read:** `gh issue view <number> --json number,title,body,labels,comments`.
- **List:** `gh issue list --state open --json number,title,body,labels`.
- **Create a ticket from a spec:** `gh issue create --parent <spec> ...`.
- **Declare a blocker:** `gh issue create --blocked-by <n>,<n> ...` or `gh issue edit <ticket> --add-blocked-by <blocker>`.
- **Count open blockers:** `gh api repos/{owner}/{repo}/issues/<n> --jq .issue_dependencies_summary.blocked_by`.
- **Comment:** `gh issue comment <number> --body "..."`.
- **Change labels:** `gh issue edit <number> --add-label "..."` or `--remove-label "..."`.
- **Close:** comment the resolution, then run `gh issue close <number>`.

A ticket is unblocked when all of its blockers are closed.

## Labels

Ready specs and tickets use the `ready-for-agent` label.

## Pull requests as input

**No.** External pull requests do not enter the ticket queue.

## When a skill asks to publish

Create an issue in this repository.

## When a skill asks for the related ticket

Read the issue as described in the conventions section.

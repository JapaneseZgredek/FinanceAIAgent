---
name: commit
description: Create conventional commits for all unstaged/staged changes. Automatically groups files into logical commits by scope, stages them, and commits — no manual staging required.
argument-hint: [optional message hint]
disable-model-invocation: true
allowed-tools: Bash(git *)
---

# Conventional Commit

Automatically group ALL changed files (staged and unstaged) into logical commits and execute them — no pre-staging required.

## Steps

1. Run `git status` to see all changed files (staged + unstaged + untracked)
2. Run `git log --oneline -5` to match existing commit style
3. For each changed file, run `git diff HEAD -- <file>` to understand what changed
4. Group files into logical commit batches by scope (see rules below)
5. For each batch: `git add <files>`, then commit with the appropriate message
6. Execute all commits sequentially without asking for confirmation

## Grouping Rules

Files belong in the **same commit** if they are part of the same logical change.
Files belong in **separate commits** if they touch unrelated scopes.

**Scope → file mapping:**

| Scope | Files |
|-------|-------|
| `indicators` | `app/utils/indicators.py` |
| `price` | `app/tools/price_tools.py`, `app/clients/alpha_vantage_client.py` |
| `runner` | `app/claude_runner.py` |
| `client` | `app/clients/claude_client.py` |
| `config` | `app/config.py` |
| `cache` | `app/clients/cache.py` |
| `errors` | `app/utils/errors.py` |
| `retry` | `app/utils/retry.py` |
| `main` | `main.py` |
| `claude` | `.claude/` directory |
| `documentation` | `README.md`, `docs/`, `CLAUDE.md` |

**Cross-scope grouping heuristics:**
- `app/claude_runner.py` + `app/clients/claude_client.py` + `main.py` → one commit if they are part of the same feature/refactor
- `README.md` + `CLAUDE.md` + `docs/ROADMAP.md` → one `docs(documentation)` commit
- `.claude/` files → one `chore(claude)` commit per logical change

When in doubt, group by "would a reviewer expect these in one PR?"

## Commit Message Format

```
type(scope): short description in imperative mood (max 72 chars)

Optional body: explain WHY, not what.
Use bullet points for multiple changes.
Keep lines under 80 chars.
```

## Allowed Types

| Type | When to use |
|------|-------------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `chore` | Maintenance, tooling, config |
| `docs` | Documentation only |
| `test` | Adding or fixing tests |
| `style` | Code style (formatting, whitespace — no logic change) |

## Rules

- Subject line: imperative mood ("add", "fix", "update" — not "added", "fixed")
- No period at end of subject line
- Body optional — only add if the *why* isn't obvious from the subject
- Never amend published commits
- Never use `--no-verify`
- DO NOT ADD CLAUDE AS CO-AUTHOR
- DO NOT ask for confirmation — just commit
- If there is nothing to commit, say so and stop

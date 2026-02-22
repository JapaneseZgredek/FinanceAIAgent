---
name: commit
description: Create a conventional commit for this project. Analyzes staged changes, proposes a properly scoped commit message, and commits. Use this whenever you're ready to commit work.
argument-hint: [optional message hint]
disable-model-invocation: true
allowed-tools: Bash(git *)
---

# Conventional Commit

Create a git commit for the staged changes following this project's convention.

## Steps

1. Run `git status` and `git diff --staged` to understand what's staged
2. Run `git log --oneline -5` to match the existing commit style
3. Analyze whether the staged changes represent a single logical unit — if not, suggest which files to unstage and commit separately
4. Draft the commit message following the format below
5. Execute the commit

## Commit Message Format

```
type(scope): short description in imperative mood (max 72 chars)

Optional body: explain WHY this change was made, not what.
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

## Project Scopes

Use the most specific scope that applies:

| Scope | Files |
|-------|-------|
| `indicators` | `app/utils/indicators.py` |
| `news` | `app/tools/news_tools.py`, `app/clients/exa_client.py` |
| `price` | `app/tools/price_tools.py`, `app/clients/alpha_vantage_client.py` |
| `agents` | `app/agents/build_agents.py` |
| `tasks` | `app/tasks/build_tasks.py` |
| `crew` | `app/crew_runner.py` |
| `config` | `app/config.py` |
| `cache` | `app/clients/cache.py` |
| `errors` | `app/utils/errors.py` |
| `retry` | `app/utils/retry.py` |
| `limits` | `app/utils/prompt_limits.py` |
| `claude` | `.claude/` directory |
| `documentation` | `README.md`, `docs/`, `CLAUDE.md` |

If the change spans multiple unrelated scopes → split into separate commits.
If it spans multiple related scopes → use the most significant one.

## Rules

- Subject line: imperative mood ("add", "fix", "update" — not "added", "fixed")
- No period at end of subject line
- Body optional — only add if the *why* isn't obvious from the subject
- Never amend published commits
- Never use `--no-verify`

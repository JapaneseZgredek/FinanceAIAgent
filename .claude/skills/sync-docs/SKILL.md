---
name: sync-docs
description: >
  Sync project documentation to reflect work done in the current session.
  Reads session context to detect completed tasks, then surgically updates
  README.md, CLAUDE.md, and docs/ROADMAP.md.
  Use after completing a feature, refactor, or architectural change.
  Refuses to make changes if session context is too thin to justify updates.
argument-hint: (no arguments needed)
allowed-tools: Read, Edit, Bash(git diff *), Bash(git status), Bash(git log *)
---

# sync-docs

Sync project documentation based on what was actually done in this session.

## Step 1 — Assess context sufficiency

Before touching any file, evaluate whether this session contains enough
information to justify documentation updates.

**Sufficient context signals (need at least 2):**
- One or more source files were created, modified, or deleted
- A feature, refactor, or fix was discussed and implemented
- Architecture, tech stack, or config changed
- A roadmap item was completed
- `git diff` or `git status` shows meaningful changes

Run these to gather evidence:
```
git status
git diff HEAD
git log --oneline -5
```

**If fewer than 2 signals are present**, stop immediately and respond:

```
⚠️  sync-docs: not enough session context to update documentation.
Run this skill after completing a task, not at the start of a session.
```

Do not proceed past this point if context is insufficient.

---

## Step 2 — Read the maintainable files

Read all three files before making any edits:

| File | What to update |
|------|---------------|
| `README.md` | "What's implemented" section, project structure tree, data flow diagram, Requirements section |
| `CLAUDE.md` | Tech stack table, architecture tree, execution flow, pipeline description, config table, key design patterns |
| `docs/ROADMAP.md` | Item statuses (⬚ → ✅), implementation details on newly completed items |

---

## Step 3 — Identify what actually changed

Based on session context and `git diff`, determine precisely:
- Which files were added / removed / renamed
- Which features or behaviours changed
- Which roadmap items were completed
- Whether the tech stack, config, or architecture shifted

**Only update sections directly affected by these changes.**
Do not rewrite sections that are still accurate.

---

## Step 4 — Apply surgical edits

### README.md
- Update the project structure tree if files were added/removed
- Update "What's implemented" if a new capability was added
- Update the data flow diagram if the pipeline changed
- Update Requirements if API keys or dependencies changed
- Do NOT touch Setup, Run, Troubleshooting, Security unless they changed

### CLAUDE.md
- Update Tech Stack table if frameworks/libraries changed
- Update the architecture file tree if files were added/removed
- Update Execution Flow and Pipeline Architecture if the pipeline changed
- Update the config table if new env vars were added or defaults changed
- Update Key Design Patterns if a pattern was introduced or removed
- Do NOT touch Code Style, Useful Commands, or Testing unless they changed

### docs/ROADMAP.md
- Mark completed items: ⬚ → ✅
- Add implementation details to newly completed items
  (which files, which functions, what approach was used)
- Add new ⬚ items only if the session revealed a clear need not yet listed
- Do NOT change items that were not touched this session

---

## Step 5 — Report what was updated

After all edits, print a concise summary:

```
sync-docs complete:

✅ Updated:
- README.md — updated project structure tree
- CLAUDE.md — updated tech stack table, config table
- docs/ROADMAP.md — marked item 11 as ✅

⏭ Skipped (no changes needed):
- README.md → Setup, Run, Security sections still accurate
```
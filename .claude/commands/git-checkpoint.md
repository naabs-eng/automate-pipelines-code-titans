---
description: Safe git commit — stages only source files, generates a semantic commit message
allowed-tools: Bash
---

## Context

Current git state:
!`git status 2>&1`

What changed (staged and unstaged diff summary):
!`git diff HEAD --stat 2>&1`

Recent commit history (to match message style):
!`git log --oneline -8 2>&1`

Current branch:
!`git branch --show-current 2>&1`

## Task

Create a safe, well-messaged git commit for the current changes.

### Step 1 — Safety Check

Review the `git status` output above:
1. Identify all modified/new files.
2. Flag any dangerous files that must NOT be committed:
   - `data/**` — pipeline output (gitignored but check if accidentally un-ignored)
   - `logs/**` — log files
   - `.env` — credentials
   - `drivers/**` — binary JDBC jars
   - `__pycache__/**`, `*.pyc` — bytecode
3. If any dangerous files appear un-ignored, STOP and fix `.gitignore` first.

### Step 2 — Identify Safe Files

From the changed files, determine which are safe to stage:
- `src/**/*.py`
- `tests/**/*.py`
- `config.yaml`
- `requirements.txt`
- `CLAUDE.md`
- `.claude/**`
- `sql/**`
- `.github/**`
- `.gitignore`, `.flake8`, `pytest.ini`
- `README.md`

### Step 3 — Understand the Changes

Read the content of changed `src/` and `tests/` files to understand what actually changed. Based on the changes, determine:
- **Type**: `feat` (new capability), `fix` (bug fix), `refactor` (restructure), `test` (test additions), `ci` (workflow), `chore` (deps/config)
- **Scope**: `bronze`, `silver`, `gold`, `config`, `main`, `tests`, `ci`, `sql`
- **What changed**: one-line description, active voice, no "Added" (just "add")

### Step 4 — Generate Commit Message

Format: `<type>(<scope>): <description>`

Examples matching this project:
- `feat(silver): add transform_inventory method with null PK guard`
- `fix(bronze): correct JDBC URL to use integratedSecurity=true for Windows auth`
- `test(silver): add pytest suite for type casting and null filter contracts`
- `ci: add pipeline-tests workflow with Java 11 and coverage`
- `chore(config): add spark.jdbc_driver_path and sql_shuffle_partitions keys`

### Step 5 — Stage and Commit

Show the user:
1. Files that will be staged (the safe list only)
2. The generated commit message

Then run:
```bash
git add src/ tests/ config.yaml requirements.txt .claude/ .github/ sql/ CLAUDE.md .gitignore
git commit -m "<generated message>"
```

Report the commit hash after success.

### Step 6 — Suggest Next Steps

If on a feature branch: suggest `git push origin <branch>` and opening a PR.
If any CI workflows exist in `.github/workflows/`, mention they will run on push/PR.

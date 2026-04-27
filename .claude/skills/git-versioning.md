---
name: Git Versioning
description: Use when committing changes, creating branches, writing commit messages, resolving merge conflicts, or managing git workflow for this data pipeline project.
---

# Git Versioning — ClaudeDataPipeline

## Branch Strategy

Use a simple feature-branch workflow:

```
main
  └── feature/<short-description>      # new features and enhancements
  └── fix/<short-description>          # bug fixes
  └── data/<table-name>                # new source table additions
  └── test/<layer-or-component>        # test suite additions
  └── ci/<workflow-name>               # CI/CD changes
```

**Examples**:
- `feature/incremental-ingestion`
- `fix/jdbc-windows-auth`
- `data/inventory-table`
- `test/silver-transformations`
- `ci/pipeline-tests-workflow`

Merge to `main` via pull request. Never commit directly to `main`.

---

## What Is Safe to Commit

**Always safe to commit**:
- `src/**/*.py` — all Python source files
- `tests/**/*.py` — all test files
- `config.yaml` — pipeline configuration (no credentials)
- `requirements.txt` — Python dependencies
- `CLAUDE.md` — project memory
- `.claude/**` — Claude Code configuration and commands
- `sql/**` — SQL DDL and sample data scripts
- `.github/**` — CI/CD workflows
- `.gitignore`, `.flake8`, `pytest.ini` — project config files
- `README.md` — documentation

**Never commit**:
- `data/**` — pipeline output (Parquet files, gitignored)
- `logs/**` — pipeline and session logs (gitignored)
- `.env` — credentials (gitignored)
- `drivers/**` — binary JDBC jars (gitignored)
- `.claude/settings.local.json` — personal settings (gitignored)
- `__pycache__/**`, `*.pyc` — Python bytecode (gitignored)

**Correct staging** (never use `git add .`):
```bash
git add src/ tests/ config.yaml requirements.txt CLAUDE.md .claude/ sql/ .github/ .gitignore
```

---

## Commit Message Convention

Format: `<type>(<scope>): <short description>`

**Types**:
- `feat` — new feature or new table
- `fix` — bug fix
- `refactor` — code restructure without behavior change
- `test` — adding or updating tests
- `ci` — CI/CD workflow changes
- `docs` — documentation changes
- `chore` — dependency updates, config changes

**Scopes** (use the layer or component):
- `bronze`, `silver`, `gold` — specific layer changes
- `config` — config.yaml or ConfigManager changes
- `main` — pipeline orchestration (main.py)
- `tests` — test suite
- `sql` — SQL schema scripts
- `ci` — GitHub Actions workflows

**Examples**:
```
feat(silver): add transform_inventory method with null PK guard
fix(bronze): correct JDBC URL to use integratedSecurity=true for Windows auth
refactor(gold): replace inner join with left join to preserve all order_items
test(silver): add pytest suite covering type casting and null filter contracts
ci: add pipeline-tests workflow with Java 11 and coverage reporting
feat(data): scaffold Inventory table across all three medallion layers
fix(config): add missing spark.jdbc_driver_path key
```

---

## Pre-Commit Checklist

Before running `git commit`, verify:

```bash
# 1. Syntax check all changed Python files
python -m py_compile src/bronze/ingestion.py
python -m py_compile src/silver/transformations.py
python -m py_compile src/main.py

# 2. Run tests (if tests exist)
pytest tests/ -v -m "not integration"

# 3. Check no sensitive files are staged
git diff --cached --name-only  # review this list

# 4. Verify no data/logs in staged files
git diff --cached --name-only | grep -E "^(data/|logs/|\.env)"
# Should return nothing
```

---

## Resolving Merge Conflicts in Pipeline Files

**For `config.yaml` conflicts**: The config is additive — both sides likely added different keys. Merge by keeping all keys from both sides, resolving any duplicate keys by choosing the newer/correct value.

**For `main.py` conflicts**: Main.py is the orchestration file. Conflicts usually happen when two branches add different table wiring. Keep all `spark.read.parquet()` calls, all `layer.transform_*()` calls, and all `layer.save_*()` calls — they are additive.

**For `transformations.py` or `aggregations.py` conflicts**: These are method additions. Keep all methods from both sides unless they truly conflict on the same method name.

---

## Tagging Releases

For stable pipeline versions, use annotated tags:
```bash
git tag -a v1.0.0 -m "Initial release: Products, Customers, Orders, OrderItems pipeline"
git tag -a v1.1.0 -m "Add Inventory table and daily_inventory_levels gold table"
```

Tag after all tests pass on `main`. Push tags explicitly:
```bash
git push origin v1.0.0
```

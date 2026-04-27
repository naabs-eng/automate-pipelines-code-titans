---
name: CI/CD GitHub Actions
description: Use when creating, modifying, or debugging GitHub Actions workflows for this Python + PySpark pipeline project. Covers test automation, linting, and config validation.
---

# CI/CD — GitHub Actions for ClaudeDataPipeline

## Overview

Three workflows run in CI for this project:

| Workflow | Trigger | Purpose |
|---|---|---|
| `pipeline-tests.yml` | push + pull_request | Run pytest suite (no SQL Server) |
| `code-quality.yml` | push + pull_request | flake8 + black + isort |
| `schema-validation.yml` | pull_request only | Validate config.yaml completeness |

---

## PySpark in GitHub Actions — Key Requirements

1. **Java 11 is required**: PySpark depends on JVM. Use `actions/setup-java@v4` with Temurin distribution.
2. **SPARK_LOCAL_IP must be set**: Without this, PySpark tries to resolve the hostname and may fail or warn excessively.
3. **Shuffle partitions must be reduced**: Default 200 shuffle partitions on a 2-core runner is wasteful. Set to `1` for tests.
4. **SQL Server tests must be skipped**: No SQL Server available in CI. Mark integration tests and skip them.

```yaml
env:
  SPARK_LOCAL_IP: 127.0.0.1
  PYSPARK_PYTHON: python3
```

---

## Test Markers (pytest.ini)

Create `pytest.ini` in project root:
```ini
[pytest]
markers =
    integration: marks tests that require a live SQL Server connection
    unit: marks pure unit tests with no Spark or external dependencies
addopts = -v
```

Run in CI (skip integration):
```bash
pytest tests/ -m "not integration" --cov=src --cov-report=xml
```

Run locally with SQL Server:
```bash
pytest tests/ -m "integration" -v
```

---

## Environment Variables Available in GitHub Actions

For secrets (like SQL credentials if ever needed in CI):
```yaml
env:
  SQL_USER: ${{ secrets.SQL_USER }}
  SQL_PASSWORD: ${{ secrets.SQL_PASSWORD }}
```

Add secrets in: GitHub repo → Settings → Secrets and variables → Actions

For this project, SQL Server tests are skipped in CI so no SQL credentials are needed.

---

## Workflow File Locations

```
.github/
  workflows/
    pipeline-tests.yml       ← runs pytest
    code-quality.yml         ← runs flake8 + black + isort
    schema-validation.yml    ← validates config.yaml on PRs
```

---

## Linting Configuration

**`.flake8`** (project root):
```ini
[flake8]
max-line-length = 120
ignore = E203, W503, E501
exclude =
    .venv,
    __pycache__,
    data/,
    logs/,
    drivers/
```

PySpark method chaining requires long lines — 120 char limit is appropriate.

**`pyproject.toml`** (or `setup.cfg`) for black and isort:
```toml
[tool.black]
line-length = 120
target-version = ["py311"]

[tool.isort]
profile = "black"
line_length = 120
```

---

## Adding New Workflow Triggers

For scheduled daily pipeline validation (future):
```yaml
on:
  schedule:
    - cron: '0 6 * * *'  # Run at 6am UTC daily
  push:
    branches: [main]
```

For PR-only gates:
```yaml
on:
  pull_request:
    branches: [main]
    paths:
      - 'src/**'
      - 'tests/**'
      - 'config.yaml'
```

`paths` filter means the workflow only triggers when relevant files change — avoids running tests when only docs change.

---

## Debugging Failed Workflows

Common CI failures for this project:

| Failure | Cause | Fix |
|---|---|---|
| `java.lang.UnsatisfiedLinkError` | Java not installed or wrong version | Ensure `actions/setup-java@v4` runs before `pip install pyspark` |
| `pyspark: command not found` | pip install failed or PATH issue | Add `pip install -r requirements.txt` step before pytest |
| `ConnectionRefusedError` | Integration test tried to connect to SQL Server | Add `-m "not integration"` to pytest command |
| `OSError: [Errno 99] Cannot assign requested address` | SPARK_LOCAL_IP not set | Add `SPARK_LOCAL_IP: 127.0.0.1` to workflow env |
| `ModuleNotFoundError: No module named 'src'` | pytest run from wrong directory | Run pytest from project root; add `src/` to PYTHONPATH if needed |
| Coverage below threshold | New code without tests | Write tests or lower threshold temporarily |

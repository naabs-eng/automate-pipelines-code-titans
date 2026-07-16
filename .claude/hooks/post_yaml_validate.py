"""
PostToolUse hook — runs after any Write/Edit/MultiEdit on config.yaml.

1. Validates: parseable YAML + required top-level keys present + pipelines is a non-empty list.
2. Syncs: regenerates the '## Active Pipelines' section in CLAUDE.md from the pipelines: key.
"""
import json
import sys
from pathlib import Path

REQUIRED_KEYS = ["paths", "postgresql", "spark", "pipelines"]

CLAUDE_MD = Path("CLAUDE.md")
SECTION_HEADING = "## Active Pipelines"
SECTION_END_MARKER = "\n---"


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_file_path(stdin_data: str) -> str:
    try:
        data = json.loads(stdin_data)
        tool_input = data.get("tool_input", {})
        if isinstance(tool_input, dict):
            return tool_input.get("file_path", "") or tool_input.get("path", "")
    except Exception:
        pass
    return ""


def format_schedule(pipeline: dict) -> str:
    sc = pipeline.get("schedule_config", {})
    stype = sc.get("type", pipeline.get("schedule", "—"))
    time_ = sc.get("time", "")
    day = sc.get("day", "")
    parts = [stype]
    if day:
        parts.append(day)
    if time_:
        parts.append(time_)
    return " ".join(parts)


def format_sources(pipeline: dict) -> str:
    sources = pipeline.get("sources", [])
    parts = []
    for src in sources:
        stype = src.get("source_type", "")
        tables = src.get("tables", [])
        for t in tables:
            parts.append(f"`{t}`")
    return ", ".join(parts) if parts else "—"


def derive_produces(pipeline: dict) -> str:
    name = pipeline.get("name", "")
    sources = pipeline.get("sources", [])

    if name.endswith("_bronze_silver"):
        outputs = []
        for src in sources:
            stype = src.get("source_type", "")
            if stype in ("postgresql", "file"):
                for t in src.get("tables", []):
                    base = t.rsplit(".", 1)[0] if "." in t else t  # strip .csv/.json
                    outputs.append(f"`{base}_bronze/silver`")
        return ", ".join(outputs) if outputs else "—"

    if name.endswith("_gold"):
        # Look in pipelines/ doc for output info; fall back to a hint
        doc_path = Path("pipelines") / f"{name}.md"
        if doc_path.exists():
            for line in doc_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if "output" in line.lower() and "`" in line:
                    # Extract backtick-quoted names from the line
                    parts = [p for p in line.split("`") if p and "/" not in p and " " not in p]
                    if parts:
                        return ", ".join(f"`{p}`" for p in parts[:3])
        return "Gold (see `pipelines/` docs)"

    return "—"


def build_pipelines_section(config: dict) -> str:
    pipelines = config.get("pipelines", [])
    lines = [
        "## Active Pipelines",
        "",
        "Pipelines are defined in `config.yaml` under the `pipelines:` key and tracked as `.md` docs in `pipelines/`.",
        "",
        "| Pipeline | Schedule | Sources | Produces |",
        "|---|---|---|---|",
    ]

    for pl in pipelines:
        name = pl.get("name", "—")
        schedule = format_schedule(pl)
        sources = format_sources(pl)
        produces = derive_produces(pl)
        lines.append(f"| `{name}` | {schedule} | {sources} | {produces} |")

    # Unused source files
    sources_dir = Path("data/sources")
    wired_files = set()
    for pl in pipelines:
        for src in pl.get("sources", []):
            if src.get("source_type") == "file":
                for t in src.get("tables", []):
                    wired_files.add(t)

    unused = []
    if sources_dir.exists():
        for f in sorted(sources_dir.iterdir()):
            if f.is_file() and f.name not in wired_files:
                unused.append(f"`{f.name}`")

    lines.append("")
    if unused:
        lines.append(f"**Unused source files** (in `data/sources/` but not wired to any pipeline yet): {', '.join(unused)}")
    else:
        lines.append("*All files in `data/sources/` are wired to a pipeline.*")

    return "\n".join(lines)


def sync_claude_md(config: dict):
    if not CLAUDE_MD.exists():
        return

    content = CLAUDE_MD.read_text(encoding="utf-8")

    start = content.find(f"\n{SECTION_HEADING}\n")
    if start == -1:
        return

    # Find the closing --- after the section
    end = content.find(SECTION_END_MARKER, start + 1)
    if end == -1:
        return

    new_section = "\n" + build_pipelines_section(config) + "\n"
    updated = content[:start] + new_section + content[end:]
    CLAUDE_MD.write_text(updated, encoding="utf-8")
    print(f"[post_yaml_validate] Synced Active Pipelines in CLAUDE.md ({len(config.get('pipelines', []))} pipelines)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)

        file_path = get_file_path(raw)
        if not file_path or Path(file_path).name != "config.yaml":
            sys.exit(0)

        try:
            import yaml
        except ImportError:
            sys.exit(0)

        try:
            content = Path(file_path).read_text(encoding="utf-8")
            config = yaml.safe_load(content)
        except yaml.YAMLError as e:
            print(f"[post_yaml_validate] INVALID YAML in config.yaml: {e}", file=sys.stderr)
            sys.exit(0)

        if not isinstance(config, dict):
            print("[post_yaml_validate] config.yaml does not parse to a mapping.", file=sys.stderr)
            sys.exit(0)

        # Validate required keys
        missing = [k for k in REQUIRED_KEYS if k not in config]
        if missing:
            print(f"[post_yaml_validate] config.yaml is missing required keys: {missing}", file=sys.stderr)

        # Validate pipelines list
        pipelines = config.get("pipelines")
        if not pipelines or not isinstance(pipelines, list):
            print("[post_yaml_validate] config.yaml: pipelines is missing or empty — no pipelines defined.", file=sys.stderr)

        # Sync CLAUDE.md Active Pipelines section
        sync_claude_md(config)

    except Exception:
        pass


if __name__ == "__main__":
    main()

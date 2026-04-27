"""
Stop hook — prints a session summary when Claude Code finishes.
Reports commands run, pipeline executions, and any failures.
"""
import sys
import re
from pathlib import Path
from datetime import datetime


AUDIT_LOG = Path("logs/claude_session_audit.log")
PIPELINE_LOG = Path("logs/pipeline_runs.log")


def count_recent_entries(log_path: Path, session_start: str) -> list[str]:
    """Return log lines from approximately this session (last N lines as proxy)."""
    if not log_path.exists():
        return []
    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [l for l in lines if l.strip()]


def parse_audit_log(lines: list[str]) -> dict:
    stats = {
        "total_commands": 0,
        "python_runs": 0,
        "git_commands": 0,
        "pytest_runs": 0,
        "unique_files_touched": set(),
    }
    for line in lines[-100:]:  # look at last 100 entries as this session
        stats["total_commands"] += 1
        cmd_match = re.search(r"CMD:\s*(.+?)\s*\|", line)
        if cmd_match:
            cmd = cmd_match.group(1)
            if "python" in cmd.lower():
                stats["python_runs"] += 1
            if cmd.startswith("git"):
                stats["git_commands"] += 1
            if "pytest" in cmd.lower():
                stats["pytest_runs"] += 1
    return stats


def parse_pipeline_log(lines: list[str]) -> dict:
    pipeline_stats = {"success": 0, "failure": 0, "total": 0}
    for line in lines[-20:]:
        pipeline_stats["total"] += 1
        if "SUCCESS" in line:
            pipeline_stats["success"] += 1
        elif "FAILURE" in line:
            pipeline_stats["failure"] += 1
    return pipeline_stats


def get_latest_errors() -> list[str]:
    """Get ERROR lines from the most recent pipeline log file."""
    log_dir = Path("logs")
    if not log_dir.exists():
        return []
    log_files = sorted(log_dir.glob("pipeline_*.log"))
    if not log_files:
        return []
    latest = log_files[-1]
    lines = latest.read_text(encoding="utf-8", errors="ignore").splitlines()
    return [l.strip() for l in lines if "ERROR" in l][-5:]  # last 5 errors


def main():
    try:
        audit_lines = count_recent_entries(AUDIT_LOG, "")
        pipeline_lines = count_recent_entries(PIPELINE_LOG, "")

        audit_stats = parse_audit_log(audit_lines)
        pipeline_stats = parse_pipeline_log(pipeline_lines)
        latest_errors = get_latest_errors()

        border = "=" * 50
        print(f"\n{border}")
        print("  Claude Code Session Summary — ClaudeDataPipeline")
        print(border)
        print(f"  Commands run (this session) : ~{min(audit_stats['total_commands'], 50)}")
        print(f"  Python executions           : {audit_stats['python_runs']}")
        print(f"  Git commands                : {audit_stats['git_commands']}")
        print(f"  pytest runs                 : {audit_stats['pytest_runs']}")

        if pipeline_stats["total"] > 0:
            print(f"  Pipeline runs               : {pipeline_stats['total']} "
                  f"({pipeline_stats['success']} success, {pipeline_stats['failure']} fail)")

        if latest_errors:
            print(f"\n  Last pipeline errors:")
            for err in latest_errors:
                print(f"    ! {err[:100]}")

        print(border)
        print(f"  Logs: logs/claude_session_audit.log")
        if pipeline_stats["total"] > 0:
            print(f"  Pipeline history: logs/pipeline_runs.log")
        print(f"{border}\n")

    except Exception:
        # Never crash the session on hook error
        pass


if __name__ == "__main__":
    main()

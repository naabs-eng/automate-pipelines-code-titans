"""
PostToolUse hook — logs every bash command Claude executes to an audit trail.
Writes to logs/claude_session_audit.log and tracks pipeline run outcomes.
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path


AUDIT_LOG = Path("logs/claude_session_audit.log")
PIPELINE_RUN_LOG = Path("logs/pipeline_runs.log")
MAX_OUTPUT_CHARS = 300


def ensure_log_dir():
    Path("logs").mkdir(exist_ok=True)


def truncate(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


def is_pipeline_run(command: str) -> bool:
    return "src/main.py" in command or "main.py" in command


def extract_pipeline_outcome(output: str) -> str:
    if not output:
        return "unknown"
    lower = output.lower()
    if "completed successfully" in lower or "pipeline completed" in lower:
        return "SUCCESS"
    if "error" in lower or "failed" in lower or "exception" in lower:
        return "FAILURE"
    return "COMPLETED"


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)

        data = json.loads(raw)
        tool_input = data.get("tool_input", {})
        tool_response = data.get("tool_response", {})

        command = tool_input.get("command", "") if isinstance(tool_input, dict) else str(tool_input)
        output = ""
        if isinstance(tool_response, dict):
            output = tool_response.get("stdout", "") or tool_response.get("output", "") or str(tool_response)
        elif isinstance(tool_response, str):
            output = tool_response

        ensure_log_dir()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        short_output = truncate(output)

        audit_entry = f"[{timestamp}] CMD: {command} | OUT: {short_output}\n"
        with open(AUDIT_LOG, "a", encoding="utf-8") as f:
            f.write(audit_entry)

        if is_pipeline_run(command):
            outcome = extract_pipeline_outcome(output)
            pipeline_entry = f"[{timestamp}] {outcome}: {command}\n"
            with open(PIPELINE_RUN_LOG, "a", encoding="utf-8") as f:
                f.write(pipeline_entry)

    except (json.JSONDecodeError, KeyError, OSError):
        pass
    except Exception:
        pass


if __name__ == "__main__":
    main()

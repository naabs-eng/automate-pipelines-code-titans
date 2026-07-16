"""
PostToolUse hook — syntax-checks any .py file immediately after Write/Edit/MultiEdit.
Prints compile errors to stderr so Claude sees them before proceeding.
"""
import json
import sys
import subprocess
from pathlib import Path


def get_file_path(stdin_data: str) -> str:
    try:
        data = json.loads(stdin_data)
        tool_input = data.get("tool_input", {})
        if isinstance(tool_input, dict):
            return tool_input.get("file_path", "") or tool_input.get("path", "")
    except Exception:
        pass
    return ""


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)

        file_path = get_file_path(raw)
        if not file_path or not file_path.endswith(".py"):
            sys.exit(0)

        if not Path(file_path).exists():
            sys.exit(0)

        result = subprocess.run(
            [sys.executable, "-m", "py_compile", file_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            error = result.stderr.strip() or result.stdout.strip()
            print(f"[post_py_compile] SYNTAX ERROR in {file_path}:\n{error}", file=sys.stderr)

    except Exception:
        pass


if __name__ == "__main__":
    main()

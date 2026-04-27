"""
PreToolUse hook — intercepts bash commands before execution.
Blocks dangerous patterns. Outputs JSON decision to stdout.
"""
import json
import sys
import re

BLOCKED_PATTERNS = [
    (r"rm\s+-rf", "Destructive: rm -rf is blocked. Delete files manually if intentional."),
    (r"git\s+push\s+--force", "Destructive: force push is blocked. Use a normal push or ask for confirmation."),
    (r"git\s+push\s+-f\b", "Destructive: force push (-f) is blocked."),
    (r"git\s+reset\s+--hard", "Destructive: git reset --hard is blocked. Use git stash or a soft reset."),
    (r"DROP\s+DATABASE", "Destructive: DROP DATABASE is blocked. Run SQL commands manually in SSMS."),
    (r"DROP\s+TABLE", "Destructive: DROP TABLE is blocked. Run SQL commands manually in SSMS."),
    (r">\s*\.env", "Security: Writing to .env is blocked. Edit .env manually — never let automated tools write credentials."),
    (r">\s*config\.yaml", "Safety: Overwriting config.yaml via redirect is blocked. Use an editor to modify config."),
]

WARNING_PATTERNS = [
    (r"git\s+add\s+\.", "Warning: 'git add .' may stage data/, logs/, or .env. Prefer 'git add src/ tests/ config.yaml'"),
    (r"git\s+add\s+-A", "Warning: 'git add -A' may stage unintended files. Use explicit paths."),
]


def check_command(command: str) -> tuple[bool, str]:
    """Returns (should_block, reason)."""
    for pattern, reason in BLOCKED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, reason
    return False, ""


def check_warnings(command: str) -> list[str]:
    """Returns list of warning messages (non-blocking)."""
    warnings = []
    for pattern, msg in WARNING_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            warnings.append(msg)
    return warnings


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)

        data = json.loads(raw)
        tool_input = data.get("tool_input", {})
        command = tool_input.get("command", "") if isinstance(tool_input, dict) else str(tool_input)

        should_block, reason = check_command(command)

        if should_block:
            print(json.dumps({
                "decision": "block",
                "reason": f"[pre_bash_guard] {reason}"
            }))
            sys.exit(0)

        warnings = check_warnings(command)
        if warnings:
            # Non-blocking: print warning to stderr so it appears in Claude's context
            for w in warnings:
                print(f"[pre_bash_guard] {w}", file=sys.stderr)

        # Allow all other commands
        print(json.dumps({"decision": "allow"}))

    except (json.JSONDecodeError, KeyError):
        # If we can't parse the input, allow the command
        print(json.dumps({"decision": "allow"}))
    except Exception:
        # Never block on hook error
        print(json.dumps({"decision": "allow"}))


if __name__ == "__main__":
    main()

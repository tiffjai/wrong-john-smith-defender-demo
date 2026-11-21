#!/usr/bin/env python3
"""Launch the project's Grok builder with its Supabase MCP connection."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", nargs="?", help="Feature or task for the builder")
    parser.add_argument("--doctor", action="store_true", help="Check the live MCP connection")
    parser.add_argument("--headless", action="store_true", help="Run one noninteractive task")
    parser.add_argument("--dry-run", action="store_true", help="Show the launch command without running Grok")
    args = parser.parse_args()
    if args.headless and not args.task:
        parser.error("--headless requires a task")
    rules = (ROOT / "bots/supabase-builder.md").read_text()
    if args.doctor:
        command = ["grok", "mcp", "doctor", "supabase"]
    else:
        command = ["grok", "--rules", rules]
        task = args.task or (
            "Verify the Supabase MCP connection, inspect the existing schema and "
            "local migrations without changing the database, and report what is "
            "ready and what is missing for the hackathon dashboard."
        )
        command += ["-p", task] if args.headless else [task]
    if args.dry_run:
        import shlex
        print(f"Working directory: {ROOT}")
        print(shlex.join(command))
        return 0
    executable = shutil.which("grok")
    if not executable:
        print(
            "Grok Build is not installed or is missing from PATH.\n"
            "Install it using https://docs.x.ai/build/overview, then rerun this command.\n"
            "On first launch sign in to Grok and authorize Supabase through /mcps.",
            file=sys.stderr,
        )
        return 127
    command[0] = executable
    try:
        return subprocess.call(command, cwd=ROOT)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())

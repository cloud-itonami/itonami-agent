#!/usr/bin/env python3
"""Decision-free measurement of the itonami-agent Hermes-compatibility state.

Holds no judgement. It reports the test suite's own numbers, the README's
remaining gap rows, and the open compatibility PRs. The bot decides; this
file only measures.

Its exit code is load-bearing in one direction. Hermes injects stdout into
the prompt, so an empty report reaches the model as *nothing is missing* —
the one answer that must never be produced by failure. Every refusal
therefore prints a REFUSED banner and still exits 0: the bot has to run and
be told it is blind, not be silently skipped.
"""
import subprocess
import sys
from pathlib import Path

WORKTREE = Path.home() / "github" / "wt" / "itonami-compat" / "agent"


def refused(reason):
    print("REFUSED: " + reason)
    print("The bot cannot see the compatibility state this run. Do not conclude that work is complete.")


def main():
    if not WORKTREE.is_dir():
        refused("worktree missing: " + str(WORKTREE))
        return 0
    try:
        run = subprocess.run(
            ["kbb", "--backend", "sci", "--classpath", "src:test", "run-tests.cljk"],
            cwd=str(WORKTREE), capture_output=True, text=True, timeout=300)
        tail = [l for l in run.stdout.splitlines() if l.strip()][-3:]
        print("TESTS: " + " | ".join(tail))
    except Exception as exc:
        refused("test run failed: " + str(exc))
        return 0
    try:
        readme = (WORKTREE / "README.md").read_text(encoding="utf-8")
        gaps = [l.strip() for l in readme.splitlines()
                if "not implemented" in l.lower() or "remaining" in l.lower()]
        print("README_GAP_ROWS: " + str(len(gaps)))
        for line in gaps:
            print("GAP: " + line[:200])
    except Exception as exc:
        refused("README unreadable: " + str(exc))
    try:
        prs = subprocess.run(
            ["gh", "pr", "list", "--repo", "kotoba-lang/itonami-agent", "--state", "open",
             "--json", "number,title"],
            capture_output=True, text=True, timeout=60)
        print("OPEN_PRS: " + prs.stdout.strip())
    except Exception as exc:
        refused("gh pr list failed: " + str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())

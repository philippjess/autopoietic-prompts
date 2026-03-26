#!/usr/bin/env python3
"""
Full Generation Runner — Automates the complete cycle between generations.

Usage:
  python next_generation.py <current_gen> [--skip-merge] [--dry-run]

Steps:
  1. Check status of current generation's sessions
  2. Merge all open PRs via GitHub API
  3. Pull merged code locally
  4. Run analysis on current generation
  5. Apply cosmic ray mutations for next generation
  6. Commit and push mutations
  7. Launch next generation via Jules API

Requires:
  JULES_API_KEY and GITHUB_PAT environment variables
"""

import os
import sys
import json
import time
import subprocess
import argparse
import urllib.request
import urllib.error
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITHUB_OWNER = "philippjess"
GITHUB_REPO = "autopoietic-prompts"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"


def github_request(method: str, path: str, data: dict = None) -> dict:
    """Make a GitHub API request."""
    pat = os.environ.get("GITHUB_PAT")
    if not pat:
        print("❌ GITHUB_PAT environment variable not set")
        sys.exit(1)

    url = f"{GITHUB_API}{path}"
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github.v3+json",
    }

    body = json.dumps(data).encode("utf-8") if data else None
    if body:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"  ⚠️  GitHub API error {e.code}: {error_body[:200]}")
        return {"error": e.code}


def step_1_merge_prs(generation: int) -> int:
    """Merge all open PRs from the current generation."""
    print(f"\n📥 Step 1: Merging PRs for Generation {generation}")

    # List open PRs
    prs = github_request("GET", "/pulls?state=open&per_page=100")
    if isinstance(prs, dict) and "error" in prs:
        return 0

    gen_prefix = f"Gen{generation:03d}"
    gen_prs = [pr for pr in prs if gen_prefix in pr.get("title", "")]
    print(f"   Found {len(gen_prs)} open PRs matching '{gen_prefix}'")

    merged = 0
    for pr in gen_prs:
        pr_number = pr["number"]
        pr_title = pr["title"]
        result = github_request("PUT", f"/pulls/{pr_number}/merge", {
            "merge_method": "squash",
            "commit_title": f"[{gen_prefix}] {pr_title}",
        })
        if "error" not in result:
            merged += 1
            print(f"   ✅ Merged PR #{pr_number}: {pr_title}")
        else:
            print(f"   ❌ Failed PR #{pr_number}: {pr_title}")

    print(f"   Merged: {merged}/{len(gen_prs)}")
    return merged


def step_2_pull(repo_root: str):
    """Pull merged changes."""
    print(f"\n📥 Step 2: Pulling merged changes")
    result = subprocess.run(
        ["git", "pull", "origin", "main"],
        cwd=repo_root, capture_output=True, text=True
    )
    print(f"   {result.stdout.strip()}")
    if result.returncode != 0:
        print(f"   ⚠️  Git pull warning: {result.stderr.strip()}")


def step_3_analyze(repo_root: str, generation: int):
    """Run cultural analysis."""
    print(f"\n🔬 Step 3: Analyzing Generation {generation}")
    result = subprocess.run(
        [sys.executable, os.path.join(repo_root, "orchestrator", "analyze.py"), str(generation)],
        cwd=repo_root, capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"   ⚠️  Analysis warning: {result.stderr.strip()}")


def step_4_mutate(repo_root: str, next_gen: int, dry_run: bool = False):
    """Apply cosmic ray mutations."""
    print(f"\n☢️  Step 4: Applying mutations for Generation {next_gen}")
    args = [sys.executable, os.path.join(repo_root, "orchestrator", "mutate.py"), str(next_gen)]
    if dry_run:
        args.append("--dry-run")

    result = subprocess.run(args, cwd=repo_root, capture_output=True, text=True)
    print(result.stdout)


def step_5_commit_push(repo_root: str, next_gen: int, dry_run: bool = False):
    """Commit and push mutations."""
    print(f"\n📤 Step 5: Committing and pushing mutations")
    if dry_run:
        print("   (dry run — skipping)")
        return

    subprocess.run(["git", "add", "-A"], cwd=repo_root, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", f"☢️ Cosmic rays: mutations for Gen {next_gen:03d}"],
        cwd=repo_root, capture_output=True, text=True
    )
    print(f"   {result.stdout.strip()}")

    result = subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=repo_root, capture_output=True, text=True
    )
    print(f"   {result.stdout.strip()}")


def step_6_launch(next_gen: int, dry_run: bool = False):
    """Launch next generation via launch.py."""
    print(f"\n🚀 Step 6: Launching Generation {next_gen}")
    args = [
        sys.executable,
        os.path.join(REPO_ROOT, "orchestrator", "launch.py"),
        str(next_gen),
        "--batch-size", "15",
    ]
    if dry_run:
        args.append("--dry-run")

    result = subprocess.run(args, cwd=REPO_ROOT, text=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Full Generation Runner")
    parser.add_argument("current_gen", type=int, help="Current generation number (to merge)")
    parser.add_argument("--skip-merge", action="store_true", help="Skip PR merging")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")

    args = parser.parse_args()
    current_gen = args.current_gen
    next_gen = current_gen + 1

    print(f"🏭 Autopoietic Prompts — Generation Runner")
    print(f"   Current: Gen {current_gen:03d}")
    print(f"   Next:    Gen {next_gen:03d}")
    print(f"   Mode:    {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*50}")

    if not args.skip_merge:
        step_1_merge_prs(current_gen)

    step_2_pull(REPO_ROOT)
    step_3_analyze(REPO_ROOT, current_gen)
    step_4_mutate(REPO_ROOT, next_gen, args.dry_run)
    step_5_commit_push(REPO_ROOT, next_gen, args.dry_run)
    step_6_launch(next_gen, args.dry_run)

    print(f"\n{'='*50}")
    print(f"🎉 Generation {next_gen:03d} deployed!")
    print(f"   Monitor: python orchestrator/launch.py {next_gen} --status")
    print(f"   Next:    python orchestrator/next_generation.py {next_gen}")

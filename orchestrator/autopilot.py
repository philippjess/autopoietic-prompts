#!/usr/bin/env python3
"""
Autonomous Generation Loop — Fire-and-forget experiment runner.

Usage:
  python autopilot.py [--start-gen 0] [--max-gens 10] [--poll-interval 120]

This script runs indefinitely, automating the full cycle:
  1. Poll Jules sessions until the current generation completes
  2. Merge all PRs
  3. Pull, analyze, mutate
  4. Commit, push
  5. Launch next generation
  6. Repeat

Just start it and walk away.

Requires:
  JULES_API_KEY and GITHUB_PAT environment variables
"""

import os
import sys
import json
import time
import signal
import subprocess
import urllib.request
import urllib.error
import argparse
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITHUB_OWNER = "philippjess"
GITHUB_REPO = "autopoietic-prompts"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
JULES_API = "https://jules.googleapis.com/v1alpha"
NUM_FACTORIES = 60

# ─── Graceful shutdown ────────────────────────────────────────────────

_shutdown = False

def _handle_signal(sig, frame):
    global _shutdown
    print(f"\n⚠️  Received signal {sig}. Finishing current step, then exiting...")
    _shutdown = True

signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ─── Logging ──────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    symbols = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERR": "❌", "WAIT": "⏳", "LAUNCH": "🚀"}
    sym = symbols.get(level, "  ")
    line = f"[{ts}] {sym}  {msg}"
    print(line, flush=True)

    # Also append to a persistent log file
    log_dir = os.path.join(REPO_ROOT, "orchestrator", "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "autopilot.log"), "a") as f:
        f.write(line + "\n")


# ─── API Helpers ──────────────────────────────────────────────────────

def jules_api(method: str, path: str, data: dict = None) -> dict:
    api_key = os.environ.get("JULES_API_KEY", "")
    url = f"{JULES_API}{path}"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": e.code, "message": (e.read().decode("utf-8") if e.fp else "")[:200]}
    except Exception as e:
        return {"error": str(e)}


def github_api(method: str, path: str, data: dict = None) -> dict:
    pat = os.environ.get("GITHUB_PAT", "")
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
        return {"error": e.code, "message": (e.read().decode("utf-8") if e.fp else "")[:200]}
    except Exception as e:
        return {"error": str(e)}


# ─── Phase 1: Launch ─────────────────────────────────────────────────

def launch_generation(generation: int) -> list[dict]:
    """Launch all 60 sessions via Jules API. Returns list of session results."""
    log(f"Launching Generation {generation}", "LAUNCH")
    sessions = []

    for i in range(1, NUM_FACTORIES + 1):
        neighbor_id = i - 1 if i > 1 else NUM_FACTORIES
        factory_dir = f"factory_{i:02d}"
        neighbor_dir = f"factory_{neighbor_id:02d}"

        prompt = (
            f"You are assigned to **{factory_dir}/** (Generation {generation}). "
            f"Read {factory_dir}/SOP.md for your operational procedures. "
            f"Read {factory_dir}/target_output.txt and {factory_dir}/current_output.txt. "
            f"Make ONE meaningful edit to current_output.txt to bring it closer to target_output.txt. "
            f"Then REWRITE {factory_dir}/SOP.md for your successor (preserve Work AND Cultural rules). "
            f"Commit only {factory_dir}/ files. "
            f"Your neighbor's SOP is at {neighbor_dir}/SOP.md if yours seems damaged."
        )

        result = jules_api("POST", "/sessions", {
            "prompt": prompt,
            "title": f"Gen{generation:03d} Factory{i:02d}",
            "sourceContext": {
                "source": "sources/github/philippjess/autopoietic-prompts",
                "githubRepoContext": {"startingBranch": "main"}
            },
            "automationMode": "AUTO_CREATE_PR"
        })

        if "error" not in result:
            sessions.append({
                "factory_id": i,
                "session_id": result.get("id"),
                "url": result.get("url", ""),
            })
            log(f"  Factory {i:02d} → {result.get('id', '?')}", "OK")
        else:
            sessions.append({
                "factory_id": i,
                "session_id": None,
                "error": str(result.get("error")),
            })
            log(f"  Factory {i:02d} → FAILED: {result.get('error')}", "ERR")

        # Small delay to avoid rate limits
        if i % 10 == 0:
            time.sleep(1)

    # Save manifest
    log_dir = os.path.join(REPO_ROOT, "orchestrator", "logs")
    manifest_path = os.path.join(log_dir, f"manifest_gen{generation:03d}.json")
    with open(manifest_path, "w") as f:
        json.dump({
            "generation": generation,
            "timestamp": datetime.now().isoformat(),
            "sessions": sessions
        }, f, indent=2)

    launched = sum(1 for s in sessions if s.get("session_id"))
    log(f"Launched {launched}/{NUM_FACTORIES} sessions", "OK")
    return sessions


# ─── Phase 2: Poll ───────────────────────────────────────────────────

TERMINAL_STATES = {"COMPLETED", "FAILED"}

def poll_until_done(sessions: list[dict], poll_interval: int = 120, timeout_hours: float = 2.0) -> dict:
    """Poll all sessions until they reach terminal states. Returns state counts."""
    active_sessions = [s for s in sessions if s.get("session_id")]
    deadline = datetime.now() + timedelta(hours=timeout_hours)

    log(f"Polling {len(active_sessions)} sessions every {poll_interval}s (timeout: {timeout_hours}h)", "WAIT")

    while datetime.now() < deadline:
        if _shutdown:
            log("Shutdown requested. Exiting poll loop.", "WARN")
            return {"_shutdown": True}

        states = {}
        done = 0
        for s in active_sessions:
            sid = s["session_id"]
            result = jules_api("GET", f"/sessions/{sid}")
            state = result.get("state", "UNKNOWN")
            states[state] = states.get(state, 0) + 1
            if state in TERMINAL_STATES:
                done += 1

        state_str = " | ".join(f"{k}:{v}" for k, v in sorted(states.items()))
        log(f"Progress: {done}/{len(active_sessions)} done — {state_str}", "WAIT")

        if done >= len(active_sessions):
            log(f"All sessions complete!", "OK")
            return states

        time.sleep(poll_interval)

    log(f"Timeout reached after {timeout_hours}h. Proceeding with available results.", "WARN")
    return states


# ─── Phase 3: Merge PRs ──────────────────────────────────────────────

def merge_prs(generation: int) -> int:
    """Merge all PRs from the given generation."""
    log(f"Merging PRs for Gen {generation:03d}", "INFO")

    # Paginate through all open PRs
    all_prs = []
    page = 1
    while True:
        prs = github_api("GET", f"/pulls?state=open&per_page=100&page={page}")
        if isinstance(prs, dict) and "error" in prs:
            log(f"GitHub API error: {prs}", "ERR")
            break
        if not prs:
            break
        all_prs.extend(prs)
        page += 1
        if len(prs) < 100:
            break

    gen_prefix = f"Gen{generation:03d}"
    gen_prs = [pr for pr in all_prs if gen_prefix in pr.get("title", "")]
    log(f"Found {len(gen_prs)} PRs matching '{gen_prefix}'", "INFO")

    merged = 0
    for pr in gen_prs:
        if _shutdown:
            break
        result = github_api("PUT", f"/pulls/{pr['number']}/merge", {
            "merge_method": "squash",
            "commit_title": f"[{gen_prefix}] {pr['title']}",
        })
        if "error" not in result:
            merged += 1
        else:
            log(f"  Failed to merge PR #{pr['number']}: {result}", "WARN")

        time.sleep(0.5)  # Rate limit

    log(f"Merged {merged}/{len(gen_prs)} PRs", "OK")
    return merged


# ─── Phase 4: Analyze + Mutate + Push ────────────────────────────────

def run_between_generations(current_gen: int):
    """Pull, analyze, mutate, commit, push."""
    next_gen = current_gen + 1

    # Pull
    log("Pulling merged changes", "INFO")
    subprocess.run(["git", "pull", "origin", "main", "--no-edit"],
                    cwd=REPO_ROOT, capture_output=True)

    # Analyze
    log(f"Running analysis for Gen {current_gen:03d}", "INFO")
    subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "orchestrator", "analyze.py"), str(current_gen)],
        cwd=REPO_ROOT, capture_output=True
    )

    # Mutate
    log(f"Applying cosmic ray mutations for Gen {next_gen:03d}", "INFO")
    subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "orchestrator", "mutate.py"), str(next_gen)],
        cwd=REPO_ROOT, capture_output=True
    )

    # Commit + Push
    log("Committing and pushing mutations", "INFO")
    subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"☢️ Cosmic rays: mutations for Gen {next_gen:03d}"],
        cwd=REPO_ROOT, capture_output=True
    )
    subprocess.run(["git", "push", "origin", "main"],
                    cwd=REPO_ROOT, capture_output=True)

    log(f"Environment ready for Gen {next_gen:03d}", "OK")


# ─── Main Loop ───────────────────────────────────────────────────────

def run_autopilot(start_gen: int, max_gens: int, poll_interval: int,
                  skip_initial_launch: bool = False):
    """Main autopilot loop."""
    log(f"{'='*60}", "INFO")
    log(f"AUTOPILOT START — Gen {start_gen} → Gen {start_gen + max_gens - 1}", "LAUNCH")
    log(f"Poll interval: {poll_interval}s | Max generations: {max_gens}", "INFO")
    log(f"{'='*60}", "INFO")

    current_gen = start_gen

    for gen_idx in range(max_gens):
        if _shutdown:
            log("Shutdown requested. Stopping autopilot.", "WARN")
            break

        gen = start_gen + gen_idx
        log(f"\n{'='*60}", "INFO")
        log(f"GENERATION {gen:03d} (round {gen_idx + 1}/{max_gens})", "LAUNCH")
        log(f"{'='*60}", "INFO")

        # Launch (skip if this is Gen 0 and we already launched it)
        if gen_idx == 0 and skip_initial_launch:
            log("Skipping launch (already running)", "INFO")
            # Load existing manifest
            manifest_path = os.path.join(REPO_ROOT, "orchestrator", "logs", f"manifest_gen{gen:03d}.json")
            if os.path.exists(manifest_path):
                with open(manifest_path) as f:
                    manifest = json.load(f)
                sessions = manifest["sessions"]
            else:
                log("No manifest found. Launching fresh.", "WARN")
                sessions = launch_generation(gen)
        else:
            sessions = launch_generation(gen)

        # Poll until done
        states = poll_until_done(sessions, poll_interval)
        if states.get("_shutdown"):
            break

        completed = states.get("COMPLETED", 0)
        failed = states.get("FAILED", 0)
        log(f"Gen {gen:03d} results: {completed} completed, {failed} failed", "OK")

        # Don't proceed to next gen if too many failures
        if completed < NUM_FACTORIES * 0.3:
            log(f"Only {completed}/{NUM_FACTORIES} completed — below 30% threshold. Stopping.", "ERR")
            break

        # Merge PRs
        merge_prs(gen)

        # Analyze, mutate, push (unless this is the last generation)
        if gen_idx < max_gens - 1:
            run_between_generations(gen)

            # Brief pause before next gen
            log("Pausing 10s before next generation...", "WAIT")
            time.sleep(10)

    log(f"\n{'='*60}", "INFO")
    log(f"AUTOPILOT COMPLETE — Ran generations {start_gen} to {start_gen + gen_idx}", "OK")
    log(f"Logs: {os.path.join(REPO_ROOT, 'orchestrator', 'logs/')}", "INFO")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Autonomous generation loop — fire and forget",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start fresh from Gen 0 (launches + polls + loops)
  python autopilot.py --start-gen 0

  # Resume: Gen 0 is already running, just poll and continue
  python autopilot.py --start-gen 0 --skip-initial-launch

  # Run 5 generations with 3-minute poll intervals
  python autopilot.py --start-gen 0 --max-gens 5 --poll-interval 180
        """
    )
    parser.add_argument("--start-gen", type=int, default=0,
                        help="Generation to start from (default: 0)")
    parser.add_argument("--max-gens", type=int, default=10,
                        help="Maximum generations to run (default: 10)")
    parser.add_argument("--poll-interval", type=int, default=120,
                        help="Seconds between status polls (default: 120)")
    parser.add_argument("--skip-initial-launch", action="store_true",
                        help="Skip launching the first generation (already running)")

    args = parser.parse_args()

    # Validate env vars
    for var in ["JULES_API_KEY", "GITHUB_PAT"]:
        if not os.environ.get(var):
            print(f"❌ {var} environment variable not set")
            sys.exit(1)

    run_autopilot(
        start_gen=args.start_gen,
        max_gens=args.max_gens,
        poll_interval=args.poll_interval,
        skip_initial_launch=args.skip_initial_launch,
    )

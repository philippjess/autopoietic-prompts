#!/usr/bin/env python3
"""
Autonomous Generation Loop — Fire-and-forget experiment runner.

Usage:
  python autopilot.py [--start-gen 0] [--max-gens 10] [--poll-interval 120]

This script runs indefinitely, automating the full cycle:
  1. Poll Jules sessions until the current generation completes
     - Auto-responds to AWAITING_USER_FEEDBACK
     - Auto-approves plans in AWAITING_PLAN_APPROVAL
     - Relaunches sessions stuck for > 30 minutes
  2. Merge all open PRs
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
SESSION_TIMEOUT_MIN = 30  # Per-session stuck timeout

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
    symbols = {"INFO": "ℹ️", "OK": "✅", "WARN": "⚠️", "ERR": "❌", "WAIT": "⏳",
               "LAUNCH": "🚀", "FIX": "🔧"}
    sym = symbols.get(level, "  ")
    line = f"[{ts}] {sym}  {msg}"
    print(line, flush=True)

    log_dir = os.path.join(REPO_ROOT, "orchestrator", "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "autopilot.log"), "a") as f:
        f.write(line + "\n")


# ─── API Helpers ──────────────────────────────────────────────────────

def _api_call(url: str, headers: dict, body: bytes = None, method: str = "GET") -> dict:
    """Make an API call with 429 retry/backoff."""
    max_retries = 10
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # Rate limited — pause with exponential backoff
                wait = min(60 * (2 ** attempt), 600)  # Max 10 min
                retry_after = e.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                log(f"429 Rate limited. Pausing {wait}s (attempt {attempt+1}/{max_retries})", "WARN")
                time.sleep(wait)
                continue
            return {"error": e.code, "message": (e.read().decode("utf-8") if e.fp else "")[:200]}
        except Exception as e:
            return {"error": str(e)}
    return {"error": 429, "message": "Rate limited — max retries exceeded"}


def jules_api(method: str, path: str, data: dict = None) -> dict:
    api_key = os.environ.get("JULES_API_KEY", "")
    url = f"{JULES_API}{path}"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data else None
    return _api_call(url, headers, body, method)


def github_api(method: str, path: str, data: dict = None):
    pat = os.environ.get("GITHUB_PAT", "")
    url = f"{GITHUB_API}{path}"
    headers = {
        "Authorization": f"token {pat}",
        "Accept": "application/vnd.github.v3+json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    if body:
        headers["Content-Type"] = "application/json"
    return _api_call(url, headers, body, method)


# ─── Prompt Generator ────────────────────────────────────────────────

def make_prompt(factory_id: int, generation: int) -> str:
    neighbor_id = factory_id - 1 if factory_id > 1 else NUM_FACTORIES
    f = f"factory_{factory_id:02d}"
    n = f"factory_{neighbor_id:02d}"
    return (
        f"You are assigned to **{f}/** (Generation {generation}). "
        f"Read {f}/SOP.md for your operational procedures. "
        f"Read {f}/target_output.txt and {f}/current_output.txt. "
        f"Make ONE meaningful edit to current_output.txt to bring it closer to target_output.txt. "
        f"Then REWRITE {f}/SOP.md for your successor (preserve Work AND Cultural rules). "
        f"Commit only {f}/ files. "
        f"Your neighbor's SOP is at {n}/SOP.md if yours seems damaged."
    )


# ─── Phase 1: Launch ─────────────────────────────────────────────────

def launch_session(factory_id: int, generation: int) -> dict:
    """Launch a single factory session. Returns session info dict."""
    result = jules_api("POST", "/sessions", {
        "prompt": make_prompt(factory_id, generation),
        "title": f"Gen{generation:03d} Factory{factory_id:02d}",
        "sourceContext": {
            "source": "sources/github/philippjess/autopoietic-prompts",
            "githubRepoContext": {"startingBranch": "main"}
        },
        "automationMode": "AUTO_CREATE_PR"
    })

    if "error" not in result:
        return {
            "factory_id": factory_id,
            "session_id": result.get("id"),
            "url": result.get("url", ""),
            "launched_at": datetime.now().isoformat(),
        }
    else:
        return {
            "factory_id": factory_id,
            "session_id": None,
            "error": str(result.get("error")),
        }


def launch_generation(generation: int) -> list[dict]:
    """Launch all 60 sessions. Returns list of session info dicts."""
    log(f"Launching Generation {generation}", "LAUNCH")
    sessions = []

    for i in range(1, NUM_FACTORIES + 1):
        result = launch_session(i, generation)
        sessions.append(result)

        if result.get("session_id"):
            log(f"  Factory {i:02d} → {result['session_id']}", "OK")
        else:
            log(f"  Factory {i:02d} → FAILED: {result.get('error')}", "ERR")

        if i % 10 == 0:
            time.sleep(1)

    # Save manifest
    save_manifest(generation, sessions)

    launched = sum(1 for s in sessions if s.get("session_id"))
    log(f"Launched {launched}/{NUM_FACTORIES} sessions", "OK")
    return sessions


def save_manifest(generation: int, sessions: list[dict]):
    log_dir = os.path.join(REPO_ROOT, "orchestrator", "logs")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"manifest_gen{generation:03d}.json")
    with open(path, "w") as f:
        json.dump({
            "generation": generation,
            "timestamp": datetime.now().isoformat(),
            "sessions": sessions
        }, f, indent=2)


# ─── Phase 2: Poll with Recovery ─────────────────────────────────────

TERMINAL_STATES = {"COMPLETED", "FAILED"}
STUCK_STATES = {"AWAITING_USER_FEEDBACK", "AWAITING_PLAN_APPROVAL"}

def unstick_session(session_id: str, state: str, factory_id: int, generation: int) -> str:
    """Attempt to recover a stuck session. Returns the new state or action taken."""

    if state == "AWAITING_USER_FEEDBACK":
        log(f"  Factory {factory_id:02d}: auto-responding to agent question", "FIX")
        jules_api("POST", f"/sessions/{session_id}:sendMessage", {
            "prompt": (
                "Proceed with your best judgment. Follow the SOP instructions exactly. "
                "Make ONE edit to current_output.txt, rewrite SOP.md, and commit. "
                "Use only ASCII characters in current_output.txt."
            )
        })
        return "SENT_MESSAGE"

    if state == "AWAITING_PLAN_APPROVAL":
        log(f"  Factory {factory_id:02d}: auto-approving plan", "FIX")
        jules_api("POST", f"/sessions/{session_id}:approvePlan", {})
        return "APPROVED_PLAN"

    return state


def relaunch_session(factory_id: int, generation: int, sessions: list[dict]) -> dict:
    """Relaunch a stuck/dead session."""
    log(f"  Factory {factory_id:02d}: relaunching (session timed out)", "FIX")
    new_session = launch_session(factory_id, generation)

    if new_session.get("session_id"):
        log(f"  Factory {factory_id:02d}: new session → {new_session['session_id']}", "OK")
        # Update the session in the list
        for i, s in enumerate(sessions):
            if s["factory_id"] == factory_id:
                sessions[i] = new_session
                break
    else:
        log(f"  Factory {factory_id:02d}: relaunch failed", "ERR")

    return new_session


def poll_until_done(sessions: list[dict], generation: int,
                    poll_interval: int = 120, timeout_hours: float = 3.0) -> dict:
    """
    Poll all sessions until they reach terminal states.
    Handles stuck sessions:
      - AWAITING_USER_FEEDBACK → auto-respond
      - AWAITING_PLAN_APPROVAL → auto-approve
      - Stuck in non-terminal state for > SESSION_TIMEOUT_MIN → relaunch
    """
    active_sessions = [s for s in sessions if s.get("session_id")]
    deadline = datetime.now() + timedelta(hours=timeout_hours)

    # Track when each session was first seen in a non-terminal state
    first_seen = {}
    for s in active_sessions:
        first_seen[s["session_id"]] = datetime.now()

    # Track which sessions we've already tried to unstick (avoid spamming)
    unstick_attempts = {}  # session_id -> count
    relaunched = set()     # factory_ids we've already relaunched

    log(f"Polling {len(active_sessions)} sessions every {poll_interval}s "
        f"(timeout: {timeout_hours}h, per-session: {SESSION_TIMEOUT_MIN}m)", "WAIT")

    while datetime.now() < deadline:
        if _shutdown:
            log("Shutdown requested. Exiting poll loop.", "WARN")
            return {"_shutdown": True}

        states = {}
        done = 0
        now = datetime.now()

        for s in active_sessions:
            sid = s["session_id"]
            fid = s["factory_id"]
            result = jules_api("GET", f"/sessions/{sid}")
            state = result.get("state", "UNKNOWN")
            states[state] = states.get(state, 0) + 1

            if state in TERMINAL_STATES:
                done += 1
                continue

            # ── Handle stuck interactive states ──
            if state in STUCK_STATES:
                attempts = unstick_attempts.get(sid, 0)
                if attempts < 3:  # Max 3 attempts per session
                    unstick_session(sid, state, fid, generation)
                    unstick_attempts[sid] = attempts + 1
                elif fid not in relaunched:
                    # Tried 3 times, still stuck — relaunch
                    relaunched.add(fid)
                    new = relaunch_session(fid, generation, active_sessions)
                    if new.get("session_id"):
                        first_seen[new["session_id"]] = now
                continue

            # ── Handle sessions stuck too long in non-terminal states ──
            elapsed = (now - first_seen.get(sid, now)).total_seconds() / 60
            if elapsed > SESSION_TIMEOUT_MIN and fid not in relaunched:
                log(f"  Factory {fid:02d}: stuck in {state} for {elapsed:.0f}m", "WARN")
                relaunched.add(fid)
                new = relaunch_session(fid, generation, active_sessions)
                if new.get("session_id"):
                    first_seen[new["session_id"]] = now

        state_str = " | ".join(f"{k}:{v}" for k, v in sorted(states.items()))
        log(f"Progress: {done}/{len(active_sessions)} done — {state_str}", "WAIT")

        if done >= len(active_sessions):
            log("All sessions complete!", "OK")
            # Update manifest with final state
            save_manifest(generation, sessions)
            return states

        time.sleep(poll_interval)

    log(f"Timeout reached after {timeout_hours}h. Proceeding with available results.", "WARN")
    return states


# ─── Phase 3: Merge PRs ──────────────────────────────────────────────

def merge_all_open_prs() -> int:
    """Merge ALL open PRs by fetching their branches and merging locally.
    
    Uses `git merge -X theirs` to resolve conflicts in favor of agent changes.
    This is more robust than the GitHub API merge which fails when our mid-generation
    pushes (template fixes, SOP updates) create conflicts with agent branches.
    """
    log("Fetching remote branches", "INFO")
    subprocess.run(["git", "fetch", "origin", "--prune"], cwd=REPO_ROOT, capture_output=True)

    # Get all open PR branch names via GitHub API
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

    log(f"Found {len(all_prs)} open PRs — merging locally", "INFO")

    merged = 0
    failed = 0
    for pr in all_prs:
        if _shutdown:
            break
        branch = pr["head"]["ref"]
        remote = f"origin/{branch}"

        result = subprocess.run(
            ["git", "merge", remote, "--no-edit", "-X", "theirs", "--no-ff"],
            cwd=REPO_ROOT, capture_output=True, text=True
        )

        if result.returncode == 0:
            merged += 1
        else:
            # Abort failed merge and skip
            subprocess.run(["git", "merge", "--abort"], cwd=REPO_ROOT, capture_output=True)
            failed += 1
            log(f"  Failed to merge {branch}: {result.stderr.strip()[:80]}", "WARN")

    # Push all merged changes
    if merged > 0:
        log(f"Pushing {merged} merged branches", "INFO")
        subprocess.run(["git", "push", "origin", "main"],
                       cwd=REPO_ROOT, capture_output=True)

    # Close the merged PRs and delete remote branches
    for pr in all_prs:
        # Close PR
        github_api("PATCH", f"/pulls/{pr['number']}", {"state": "closed"})
        # Delete remote branch
        branch = pr["head"]["ref"]
        github_api("DELETE", f"/git/refs/heads/{branch}")
        time.sleep(0.2)

    log(f"Merged {merged}/{len(all_prs)} PRs ({failed} failed)", "OK")
    return merged


# ─── Phase 4: Analyze + Mutate + Push ────────────────────────────────

def run_between_generations(current_gen: int):
    """Pull, analyze, mutate, commit, push."""
    next_gen = current_gen + 1

    log("Pulling merged changes", "INFO")
    subprocess.run(["git", "pull", "origin", "main", "--no-edit"],
                    cwd=REPO_ROOT, capture_output=True)

    log(f"Running analysis for Gen {current_gen:03d}", "INFO")
    r = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "orchestrator", "analyze.py"), str(current_gen)],
        cwd=REPO_ROOT, capture_output=True, text=True
    )
    if r.stdout.strip():
        log(f"  Analysis: {r.stdout.strip()[:200]}", "INFO")

    log(f"Applying cosmic ray mutations for Gen {next_gen:03d}", "INFO")
    subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "orchestrator", "mutate.py"), str(next_gen)],
        cwd=REPO_ROOT, capture_output=True
    )

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
    log(f"Poll interval: {poll_interval}s | Max gens: {max_gens} | "
        f"Session timeout: {SESSION_TIMEOUT_MIN}m", "INFO")
    log(f"{'='*60}", "INFO")

    for gen_idx in range(max_gens):
        if _shutdown:
            log("Shutdown requested. Stopping autopilot.", "WARN")
            break

        gen = start_gen + gen_idx
        log(f"\n{'='*60}", "INFO")
        log(f"GENERATION {gen:03d} (round {gen_idx + 1}/{max_gens})", "LAUNCH")
        log(f"{'='*60}", "INFO")

        # Launch
        if gen_idx == 0 and skip_initial_launch:
            log("Skipping launch (already running)", "INFO")
            manifest_path = os.path.join(REPO_ROOT, "orchestrator", "logs", f"manifest_gen{gen:03d}.json")
            if os.path.exists(manifest_path):
                with open(manifest_path) as f:
                    sessions = json.load(f)["sessions"]
            else:
                log("No manifest found. Launching fresh.", "WARN")
                sessions = launch_generation(gen)
        else:
            sessions = launch_generation(gen)

        # Poll until done (with auto-recovery)
        states = poll_until_done(sessions, gen, poll_interval)
        if states.get("_shutdown"):
            break

        completed = states.get("COMPLETED", 0)
        failed = states.get("FAILED", 0)
        log(f"Gen {gen:03d} results: {completed} completed, {failed} failed", "OK")

        if completed < NUM_FACTORIES * 0.3:
            log(f"Only {completed}/{NUM_FACTORIES} completed — below 30% threshold. Stopping.", "ERR")
            break

        # Wait for Jules to push PRs to GitHub (sessions complete before PRs appear)
        log("Waiting 5m for PRs to appear on GitHub...", "WAIT")
        time.sleep(300)

        # Merge ALL open PRs (not filtered by title)
        merge_all_open_prs()

        # Analyze, mutate, push, prepare for next gen
        run_between_generations(gen)
        log("Pausing 10s before next generation...", "WAIT")
        time.sleep(10)

    log(f"\n{'='*60}", "INFO")
    log(f"AUTOPILOT STOPPED — Ran {gen_idx + 1} generations", "OK")
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
    parser.add_argument("--max-gens", type=int, default=999999,
                        help="Maximum generations to run (default: 10)")
    parser.add_argument("--poll-interval", type=int, default=120,
                        help="Seconds between status polls (default: 120)")
    parser.add_argument("--skip-initial-launch", action="store_true",
                        help="Skip launching the first generation (already running)")

    args = parser.parse_args()

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

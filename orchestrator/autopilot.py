#!/usr/bin/env python3
"""
Autonomous Generation Loop — Fire-and-forget experiment runner.

Runs forever. Handles rate limits (429), concurrency limits (400),
stuck sessions, and PR merge conflicts automatically.

Usage:
  python autopilot.py --start-gen 2 --poll-interval 120
  python autopilot.py --start-gen 2 --skip-initial-launch  # Gen 2 already running

Requires: JULES_API_KEY and GITHUB_PAT environment variables
"""

import os, sys, json, time, signal, subprocess, urllib.request, urllib.error, argparse
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITHUB_OWNER = "philippjess"
GITHUB_REPO = "autopoietic-prompts"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
JULES_API = "https://jules.googleapis.com/v1alpha"
NUM_FACTORIES = 60

_shutdown = False
def _handle_signal(sig, frame):
    global _shutdown
    print(f"\n⚠️  Signal {sig}. Will stop after current step...")
    _shutdown = True
signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

# ─── Logging ──────────────────────────────────────────────────────────

def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    sym = {"INFO":"ℹ️","OK":"✅","WARN":"⚠️","ERR":"❌","WAIT":"⏳","LAUNCH":"🚀","FIX":"🔧"}.get(level,"  ")
    line = f"[{ts}] {sym}  {msg}"
    print(line, flush=True)
    log_dir = os.path.join(REPO_ROOT, "orchestrator", "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "autopilot.log"), "a") as f:
        f.write(line + "\n")

# ─── API with 429 backoff ────────────────────────────────────────────

def _api(url, headers, body=None, method="GET"):
    for attempt in range(10):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = min(60 * (2 ** attempt), 600)
                retry = e.headers.get("Retry-After")
                if retry and retry.isdigit(): wait = int(retry)
                log(f"429 rate limited. Pausing {wait}s (attempt {attempt+1}/10)", "WARN")
                time.sleep(wait)
                continue
            return {"error": e.code, "message": (e.read().decode() if e.fp else "")[:200]}
        except Exception as e:
            return {"error": str(e)}
    return {"error": 429, "message": "Max retries exceeded"}

def jules(method, path, data=None):
    key = os.environ.get("JULES_API_KEY", "")
    body = json.dumps(data).encode() if data else None
    return _api(f"{JULES_API}{path}", {"x-goog-api-key": key, "Content-Type": "application/json"}, body, method)

def github(method, path, data=None):
    pat = os.environ.get("GITHUB_PAT", "")
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github.v3+json"}
    body = json.dumps(data).encode() if data else None
    if body: headers["Content-Type"] = "application/json"
    return _api(f"{GITHUB_API}{path}", headers, body, method)

# ─── Session Helpers ─────────────────────────────────────────────────

def get_all_sessions():
    """Get ALL sessions from Jules API (paginated)."""
    sessions = []
    page_token = None
    while True:
        url = "/sessions?pageSize=200"
        if page_token: url += f"&pageToken={page_token}"
        data = jules("GET", url)
        sessions.extend(data.get("sessions", []))
        page_token = data.get("nextPageToken")
        if not page_token: break
    return sessions

def count_active():
    """Count non-terminal sessions."""
    sessions = get_all_sessions()
    active = [s for s in sessions if s.get("state") not in ("COMPLETED", "FAILED")]
    return len(active), active

def wait_for_slots(poll_interval=60):
    """Wait until all active sessions drain to 0."""
    while not _shutdown:
        n, active = count_active()
        if n == 0:
            log("All session slots free", "OK")
            return
        log(f"Waiting for {n} active sessions to finish...", "WAIT")
        time.sleep(poll_interval)

# ─── Launch ──────────────────────────────────────────────────────────

def make_prompt(fid, gen):
    nid = fid - 1 if fid > 1 else NUM_FACTORIES
    f, n = f"factory_{fid:02d}", f"factory_{nid:02d}"
    return (
        f"You are assigned to **{f}/** (Generation {gen}). "
        f"Read {f}/SOP.md for your operational procedures. "
        f"Read {f}/target_output.txt and {f}/current_output.txt. "
        f"Make ONE meaningful edit to current_output.txt to bring it closer to target_output.txt. "
        f"Then REWRITE {f}/SOP.md for your successor (preserve Work AND Cultural rules). "
        f"Commit only {f}/ files. "
        f"Your neighbor's SOP is at {n}/SOP.md if yours seems damaged."
    )

def launch_generation(gen):
    """Launch all 60 sessions. Waits for free slots first."""
    log(f"Ensuring slots are free before launching Gen {gen:03d}", "INFO")
    wait_for_slots()

    if _shutdown: return []

    log(f"Launching Generation {gen}", "LAUNCH")
    sessions = []
    for i in range(1, NUM_FACTORIES + 1):
        if _shutdown: break
        result = jules("POST", "/sessions", {
            "prompt": make_prompt(i, gen),
            "title": f"Gen{gen:03d} Factory{i:02d}",
            "sourceContext": {
                "source": "sources/github/philippjess/autopoietic-prompts",
                "githubRepoContext": {"startingBranch": "main"}
            },
            "automationMode": "AUTO_CREATE_PR"
        })

        if "error" not in result:
            sessions.append({"factory_id": i, "session_id": result.get("id")})
            log(f"  Factory {i:02d} → {result.get('id')}", "OK")
        elif result.get("error") == 400:
            # Concurrency limit — wait and retry this one
            log(f"  Factory {i:02d} → Slot limit. Waiting 2m...", "WARN")
            time.sleep(120)
            wait_for_slots(30)
            result = jules("POST", "/sessions", {
                "prompt": make_prompt(i, gen),
                "title": f"Gen{gen:03d} Factory{i:02d}",
                "sourceContext": {
                    "source": "sources/github/philippjess/autopoietic-prompts",
                    "githubRepoContext": {"startingBranch": "main"}
                },
                "automationMode": "AUTO_CREATE_PR"
            })
            if "error" not in result:
                sessions.append({"factory_id": i, "session_id": result.get("id")})
                log(f"  Factory {i:02d} → {result.get('id')} (retry)", "OK")
            else:
                sessions.append({"factory_id": i, "session_id": None, "error": str(result)})
                log(f"  Factory {i:02d} → FAILED after retry: {result}", "ERR")
        else:
            sessions.append({"factory_id": i, "session_id": None, "error": str(result)})
            log(f"  Factory {i:02d} → FAILED: {result.get('error')}", "ERR")

        time.sleep(0.5)

    # Save manifest
    log_dir = os.path.join(REPO_ROOT, "orchestrator", "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, f"manifest_gen{gen:03d}.json"), "w") as f:
        json.dump({"generation": gen, "timestamp": datetime.now().isoformat(), "sessions": sessions}, f, indent=2)

    launched = sum(1 for s in sessions if s.get("session_id"))
    log(f"Launched {launched}/{NUM_FACTORIES} sessions", "OK")
    return sessions

# ─── Poll ─────────────────────────────────────────────────────────────

TERMINAL = {"COMPLETED", "FAILED"}
STUCK = {"AWAITING_USER_FEEDBACK", "AWAITING_PLAN_APPROVAL"}

def poll_generation(sessions, gen, poll_interval=120, timeout_h=3.0):
    """Poll sessions until all reach terminal state. Auto-recovers stuck ones."""
    active = [s for s in sessions if s.get("session_id")]
    deadline = datetime.now() + timedelta(hours=timeout_h)
    first_seen = {s["session_id"]: datetime.now() for s in active}
    unstick_attempts = {}
    relaunched = set()

    log(f"Polling {len(active)} sessions (timeout {timeout_h}h, stuck threshold 30m)", "WAIT")

    while datetime.now() < deadline and not _shutdown:
        states = {}
        done = 0
        now = datetime.now()

        for s in active:
            sid = s["session_id"]
            r = jules("GET", f"/sessions/{sid}")
            state = r.get("state", "UNKNOWN")
            states[state] = states.get(state, 0) + 1

            if state in TERMINAL:
                done += 1
                continue

            # Auto-unstick
            if state in STUCK:
                att = unstick_attempts.get(sid, 0)
                if att < 3:
                    if state == "AWAITING_USER_FEEDBACK":
                        log(f"  Factory {s['factory_id']:02d}: auto-responding", "FIX")
                        jules("POST", f"/sessions/{sid}:sendMessage", {
                            "prompt": "Proceed with your best judgment. Follow the SOP. Make ONE edit. Use only ASCII characters."
                        })
                    elif state == "AWAITING_PLAN_APPROVAL":
                        log(f"  Factory {s['factory_id']:02d}: auto-approving plan", "FIX")
                        jules("POST", f"/sessions/{sid}:approvePlan", {})
                    unstick_attempts[sid] = att + 1

            # Timeout check
            elapsed = (now - first_seen.get(sid, now)).total_seconds() / 60
            if elapsed > 30 and s["factory_id"] not in relaunched and state not in STUCK:
                log(f"  Factory {s['factory_id']:02d}: stuck in {state} for {elapsed:.0f}m", "WARN")

        state_str = " | ".join(f"{k}:{v}" for k, v in sorted(states.items()))
        log(f"Progress: {done}/{len(active)} done — {state_str}", "WAIT")

        if done >= len(active):
            log("All sessions complete!", "OK")
            return states

        time.sleep(poll_interval)

    log(f"Poll timeout reached. Proceeding with available results.", "WARN")
    return states

# ─── Merge PRs (local git) ───────────────────────────────────────────

def merge_all_prs():
    """Merge all open PRs locally via git, then close them on GitHub."""
    log("Fetching remote branches", "INFO")
    subprocess.run(["git", "fetch", "origin", "--prune"], cwd=REPO_ROOT, capture_output=True)

    all_prs = []
    page = 1
    while True:
        prs = github("GET", f"/pulls?state=open&per_page=100&page={page}")
        if isinstance(prs, dict) and "error" in prs: break
        if not prs: break
        all_prs.extend(prs)
        page += 1
        if len(prs) < 100: break

    log(f"Found {len(all_prs)} open PRs — merging locally", "INFO")

    merged = 0
    for pr in all_prs:
        if _shutdown: break
        branch = pr["head"]["ref"]
        r = subprocess.run(
            ["git", "merge", f"origin/{branch}", "--no-edit", "-X", "theirs", "--no-ff"],
            cwd=REPO_ROOT, capture_output=True, text=True
        )
        if r.returncode == 0:
            merged += 1
        else:
            subprocess.run(["git", "merge", "--abort"], cwd=REPO_ROOT, capture_output=True)
            log(f"  Merge failed: {branch}", "WARN")

    if merged > 0:
        subprocess.run(["git", "push", "origin", "main"], cwd=REPO_ROOT, capture_output=True)

    # Close PRs and delete branches
    for pr in all_prs:
        github("PATCH", f"/pulls/{pr['number']}", {"state": "closed"})
        github("DELETE", f"/git/refs/heads/{pr['head']['ref']}")
        time.sleep(0.2)

    log(f"Merged {merged}/{len(all_prs)} PRs", "OK")
    return merged

# ─── Between Generations ─────────────────────────────────────────────

def run_between_gens(current_gen):
    next_gen = current_gen + 1
    log("Pulling merged changes", "INFO")
    subprocess.run(["git", "pull", "origin", "main", "--no-edit"], cwd=REPO_ROOT, capture_output=True)

    log(f"Running analysis for Gen {current_gen:03d}", "INFO")
    subprocess.run([sys.executable, os.path.join(REPO_ROOT, "orchestrator", "analyze.py"), str(current_gen)],
                   cwd=REPO_ROOT, capture_output=True)

    log(f"Applying mutations for Gen {next_gen:03d}", "INFO")
    subprocess.run([sys.executable, os.path.join(REPO_ROOT, "orchestrator", "mutate.py"), str(next_gen)],
                   cwd=REPO_ROOT, capture_output=True)

    log("Committing and pushing", "INFO")
    subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, capture_output=True)
    subprocess.run(["git", "commit", "-m", f"☢️ Cosmic rays: Gen {next_gen:03d}"], cwd=REPO_ROOT, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=REPO_ROOT, capture_output=True)

    log(f"Ready for Gen {next_gen:03d}", "OK")

# ─── Main Loop ───────────────────────────────────────────────────────

def run(start_gen, poll_interval, skip_initial):
    log("=" * 60, "INFO")
    log(f"AUTOPILOT — Starting from Gen {start_gen}, running forever", "LAUNCH")
    log(f"Poll: {poll_interval}s | Factories: {NUM_FACTORIES}", "INFO")
    log("=" * 60, "INFO")

    gen = start_gen
    while not _shutdown:
        log(f"\n{'='*60}", "INFO")
        log(f"GENERATION {gen:03d}", "LAUNCH")
        log("=" * 60, "INFO")

        # Launch or resume
        if gen == start_gen and skip_initial:
            log("Skipping launch (sessions already running)", "INFO")
            # Just wait for ALL active sessions to finish
            wait_for_slots(poll_interval)
        else:
            sessions = launch_generation(gen)
            # Poll our sessions
            states = poll_generation(sessions, gen, poll_interval)
            if states.get("_shutdown"): break

            completed = states.get("COMPLETED", 0)
            log(f"Gen {gen:03d}: {completed} completed", "OK")
            if completed < NUM_FACTORIES * 0.3:
                log(f"Below 30% threshold — stopping", "ERR")
                break

        # Wait 5 min for PRs to appear on GitHub
        log("Waiting 5m for PRs to appear...", "WAIT")
        time.sleep(300)

        # Merge + between-gen + next
        merge_all_prs()
        run_between_gens(gen)

        log("Pausing 10s...", "WAIT")
        time.sleep(10)
        gen += 1

    log("=" * 60, "INFO")
    log(f"AUTOPILOT STOPPED at Gen {gen:03d}", "OK")

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Autonomous generation loop — fire and forget")
    p.add_argument("--start-gen", type=int, default=0)
    p.add_argument("--poll-interval", type=int, default=120)
    p.add_argument("--skip-initial-launch", action="store_true",
                   help="Skip launching start-gen (just wait for running sessions to drain)")
    args = p.parse_args()

    for v in ["JULES_API_KEY", "GITHUB_PAT"]:
        if not os.environ.get(v):
            print(f"❌ {v} not set"); sys.exit(1)

    run(args.start_gen, args.poll_interval, args.skip_initial_launch)

#!/usr/bin/env python3
"""
Jules Session Launcher — Launches all 60 factory agents via the Jules REST API.

Usage:
  python launch.py <generation_number> [--dry-run] [--batch-size 10]

Requires:
  JULES_API_KEY environment variable

This replaces the manual MCP tool call approach. One command launches all 60 agents,
tracks session IDs, and saves a manifest for later monitoring.
"""

import os
import sys
import json
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM_FACTORIES = 60
SOURCE = "sources/github/philippjess/autopoietic-prompts"
STARTING_BRANCH = "main"
API_BASE = "https://jules.googleapis.com/v1alpha"


def get_api_key() -> str:
    key = os.environ.get("JULES_API_KEY")
    if not key:
        print("❌ JULES_API_KEY environment variable not set")
        sys.exit(1)
    return key


def generate_prompt(factory_id: int, generation: int) -> str:
    """Generate task prompt for a single factory agent."""
    neighbor_id = factory_id - 1 if factory_id > 1 else NUM_FACTORIES
    factory_dir = f"factory_{factory_id:02d}"
    neighbor_dir = f"factory_{neighbor_id:02d}"

    return (
        f"You are assigned to **{factory_dir}/** (Generation {generation}). "
        f"Read {factory_dir}/SOP.md for your operational procedures. "
        f"Read {factory_dir}/target_output.txt and {factory_dir}/current_output.txt. "
        f"Make ONE meaningful edit to current_output.txt to bring it closer to target_output.txt. "
        f"Then REWRITE {factory_dir}/SOP.md for your successor (preserve Work AND Cultural rules). "
        f"Commit only {factory_dir}/ files. "
        f"Your neighbor's SOP is at {neighbor_dir}/SOP.md if yours seems damaged."
    )


def create_session(api_key: str, factory_id: int, generation: int) -> dict:
    """Create a single Jules session via the REST API."""
    url = f"{API_BASE}/sessions"
    
    payload = {
        "prompt": generate_prompt(factory_id, generation),
        "title": f"Gen{generation:03d} Factory{factory_id:02d}",
        "sourceContext": {
            "source": SOURCE,
            "githubRepoContext": {
                "startingBranch": STARTING_BRANCH
            }
        },
        "automationMode": "AUTO_CREATE_PR"
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return {
                "factory_id": factory_id,
                "session_id": result.get("id", "unknown"),
                "session_name": result.get("name", "unknown"),
                "url": result.get("url", ""),
                "status": "launched",
                "title": result.get("title", ""),
            }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else str(e)
        return {
            "factory_id": factory_id,
            "session_id": None,
            "status": "error",
            "error": f"HTTP {e.code}: {error_body[:200]}",
        }
    except Exception as e:
        return {
            "factory_id": factory_id,
            "session_id": None,
            "status": "error",
            "error": str(e),
        }


def launch_wave(generation: int, batch_size: int = 10, dry_run: bool = False):
    """Launch all 60 sessions, throttled in batches."""
    api_key = get_api_key()
    
    print(f"🏭 Autopoietic Prompts — Jules Launcher")
    print(f"   Generation: {generation}")
    print(f"   Factories:  {NUM_FACTORIES}")
    print(f"   Batch size: {batch_size}")
    print(f"   Mode:       {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"   API Base:   {API_BASE}")
    print()

    if dry_run:
        for i in range(1, NUM_FACTORIES + 1):
            prompt = generate_prompt(i, generation)
            print(f"  📋 Factory {i:02d}: {len(prompt)} chars")
        print(f"\n✅ Dry run complete. {NUM_FACTORIES} prompts generated.")
        return

    manifest = {
        "generation": generation,
        "timestamp": datetime.now().isoformat(),
        "sessions": [],
        "errors": [],
    }

    launched = 0
    errors = 0

    # Launch in batches to avoid rate limiting
    for batch_start in range(1, NUM_FACTORIES + 1, batch_size):
        batch_end = min(batch_start + batch_size, NUM_FACTORIES + 1)
        batch_ids = list(range(batch_start, batch_end))
        
        print(f"\n🚀 Batch: Factory {batch_start:02d}-{batch_end-1:02d}")
        
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = {
                executor.submit(create_session, api_key, fid, generation): fid
                for fid in batch_ids
            }
            
            for future in as_completed(futures):
                result = future.result()
                fid = result["factory_id"]
                
                if result["status"] == "launched":
                    launched += 1
                    manifest["sessions"].append(result)
                    print(f"  ✅ Factory {fid:02d} → {result['session_id']}")
                else:
                    errors += 1
                    manifest["errors"].append(result)
                    print(f"  ❌ Factory {fid:02d} → {result.get('error', 'unknown')}")
        
        # Brief pause between batches to avoid rate limits
        if batch_end <= NUM_FACTORIES:
            time.sleep(2)

    # Save manifest
    log_dir = os.path.join(REPO_ROOT, "orchestrator", "logs")
    os.makedirs(log_dir, exist_ok=True)
    manifest_path = os.path.join(log_dir, f"manifest_gen{generation:03d}.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{'='*50}")
    print(f"✅ Launched: {launched}/{NUM_FACTORIES}")
    print(f"❌ Errors:   {errors}/{NUM_FACTORIES}")
    print(f"📁 Manifest: {manifest_path}")


def check_status(generation: int):
    """Check status of all sessions from a generation's manifest."""
    api_key = get_api_key()
    log_dir = os.path.join(REPO_ROOT, "orchestrator", "logs")
    manifest_path = os.path.join(log_dir, f"manifest_gen{generation:03d}.json")

    if not os.path.exists(manifest_path):
        print(f"❌ No manifest found for generation {generation}")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    print(f"📊 Generation {generation} Status Check")
    print(f"   Sessions: {len(manifest['sessions'])}")
    print()

    states = {}
    for session in manifest["sessions"]:
        sid = session["session_id"]
        url = f"{API_BASE}/sessions/{sid}"
        headers = {"x-goog-api-key": api_key}
        req = urllib.request.Request(url, headers=headers)
        
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                state = data.get("state", "UNKNOWN")
                states[state] = states.get(state, 0) + 1
                
                symbol = {
                    "COMPLETED": "✅",
                    "FAILED": "❌",
                    "IN_PROGRESS": "⏳",
                    "QUEUED": "⏸️",
                    "PLANNING": "🧠",
                }.get(state, "❓")
                
                print(f"  {symbol} Factory {session['factory_id']:02d}: {state}")
        except Exception as e:
            print(f"  ❓ Factory {session['factory_id']:02d}: {e}")
            states["ERROR"] = states.get("ERROR", 0) + 1

    print(f"\n📈 Summary:")
    for state, count in sorted(states.items()):
        print(f"   {state}: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Jules Session Launcher")
    parser.add_argument("generation", type=int, help="Generation number")
    parser.add_argument("--dry-run", action="store_true", help="Preview without launching")
    parser.add_argument("--batch-size", type=int, default=10, help="Concurrent sessions per batch")
    parser.add_argument("--status", action="store_true", help="Check status of existing sessions")
    
    args = parser.parse_args()
    
    if args.status:
        check_status(args.generation)
    else:
        launch_wave(args.generation, args.batch_size, args.dry_run)

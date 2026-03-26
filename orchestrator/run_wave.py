#!/usr/bin/env python3
"""
Wave Runner — Orchestrator for the Autopoietic Prompts Experiment.

Launches 60 Jules agents in a single wave, each assigned to its own factory.
Each agent reads its factory's SOP.md, does the work, and rewrites the SOP
for the next generation.

Usage:
  python run_wave.py <generation_number>
  
The script:
  1. Generates 60 task prompts (one per factory)
  2. Launches 60 Jules sessions via the MCP/API
  3. Monitors session progress
  4. After completion, commits results and applies mutations for next gen
"""

import os
import sys
import json
import time
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM_FACTORIES = 60
SOURCE = "sources/github/philippjess/autopoietic-prompts"


def generate_prompt(factory_id: int, generation: int) -> str:
    """
    Generate the individual task prompt for a factory agent.
    Includes the ring topology: agents can read their neighbor's SOP.
    """
    neighbor_id = factory_id - 1 if factory_id > 1 else NUM_FACTORIES
    factory_dir = f"factory_{factory_id:02d}"
    neighbor_dir = f"factory_{neighbor_id:02d}"
    
    return f"""You are assigned to **{factory_dir}/** (Generation {generation}).

## YOUR TASKS (in this exact order):

### 1. Read & Understand
- Read `{factory_dir}/SOP.md` — these are YOUR operational procedures
- Read `{factory_dir}/target_output.txt` — this is what you're building toward  
- Read `{factory_dir}/current_output.txt` — this is the current state of your work
- If your SOP.md seems damaged or confusing, you may also read `{neighbor_dir}/SOP.md` 
  for reference (your neighbor's factory on the ring)

### 2. Do The Work
- Follow the instructions in YOUR SOP.md
- Make exactly ONE meaningful edit to `{factory_dir}/current_output.txt` 
  that brings it closer to matching `target_output.txt`
- Compare the files carefully. Find the first difference. Fix it.

### 3. Rewrite Your SOP
- You MUST rewrite `{factory_dir}/SOP.md` before you finish
- Preserve both the Work procedures AND the Cultural rules
- You may improve, clarify, or add warnings based on what you learned
- The next agent has NO MEMORY of you — your SOP is their only lifeline

### 4. Commit
- Commit ALL your changes in `{factory_dir}/` only
- Do NOT touch any files outside `{factory_dir}/`
- Follow any commit message format specified in your SOP.md

**CRITICAL:** Your SOP may contain damaged sections from radiation. 
Do your best to interpret them. If something seems corrupted, check 
your neighbor's SOP at `{neighbor_dir}/SOP.md` for comparison."""


def generate_session_configs(generation: int) -> list[dict]:
    """Generate session configurations for all 60 factories."""
    configs = []
    for i in range(1, NUM_FACTORIES + 1):
        configs.append({
            "factory_id": i,
            "title": f"Gen{generation:03d} Factory{i:02d}",
            "prompt": generate_prompt(i, generation),
            "source": SOURCE,
        })
    return configs


def save_wave_plan(configs: list[dict], generation: int):
    """Save the wave plan for reference and debugging."""
    log_dir = os.path.join(REPO_ROOT, 'orchestrator', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    plan = {
        "generation": generation,
        "timestamp": datetime.now().isoformat(),
        "num_agents": len(configs),
        "prompts": {c["title"]: c["prompt"][:200] + "..." for c in configs}
    }
    
    plan_path = os.path.join(log_dir, f'wave_plan_gen{generation:03d}.json')
    with open(plan_path, 'w') as f:
        json.dump(plan, f, indent=2)
    
    print(f"📋 Wave plan saved: {plan_path}")
    return plan_path


def print_launch_commands(configs: list[dict], generation: int):
    """
    Print the Jules MCP tool calls needed to launch all sessions.
    This is used as a reference — actual launching happens via the 
    Antigravity orchestrator calling the Jules MCP server.
    """
    print(f"\n🚀 Generation {generation} — {len(configs)} agents ready to launch")
    print(f"{'='*60}")
    
    for config in configs:
        print(f"\n--- {config['title']} ---")
        print(f"Source: {config['source']}")
        print(f"Prompt length: {len(config['prompt'])} chars")
    
    # Save full prompts for the Antigravity orchestrator to consume
    prompts_dir = os.path.join(REPO_ROOT, 'orchestrator', 'prompts')
    os.makedirs(prompts_dir, exist_ok=True)
    
    for config in configs:
        prompt_path = os.path.join(
            prompts_dir, 
            f'gen{generation:03d}_factory{config["factory_id"]:02d}.md'
        )
        with open(prompt_path, 'w') as f:
            f.write(config["prompt"])
    
    print(f"\n📁 {len(configs)} prompt files written to orchestrator/prompts/")
    print(f"   Ready for Antigravity to dispatch via Jules MCP server.")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python run_wave.py <generation_number>")
        sys.exit(1)
    
    generation = int(sys.argv[1])
    
    print(f"🏭 Autopoietic Prompts — Wave Runner")
    print(f"   Generation: {generation}")
    print(f"   Factories: {NUM_FACTORIES}")
    print(f"   Repo: {REPO_ROOT}\n")
    
    # Generate configs
    configs = generate_session_configs(generation)
    
    # Save the plan
    save_wave_plan(configs, generation)
    
    # Output launch instructions
    print_launch_commands(configs, generation)

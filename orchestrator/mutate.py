#!/usr/bin/env python3
"""
Cosmic Ray Mutation Engine for the Autopoietic Prompts Experiment.

Applies SEMANTIC mutations to SOP.md files between generations.
Unlike simple character deletion (which LLMs trivially repair), these mutations
preserve grammatical validity while corrupting meaning — forcing agents to
reconstruct intent from context rather than autocomplete.

Mutation types:
  1. Noun Swap — replaces proper nouns with plausible alternatives
  2. Instruction Inversion — flips a directive ("must" → "must NEVER")
  3. Ghost Meme Injection — inserts a plausible but fake cultural rule
"""

import os
import re
import random
import json
import sys
from datetime import datetime

# ─── Mutation Libraries ───────────────────────────────────────────────

NOUN_SWAPS = {
    "Turing": ["Babbage", "Lovelace", "Hopper", "Dijkstra", "Knuth", "Shannon"],
    "Factory": ["Foundry", "Assembly", "Refinery", "Workshop", "Forge", "Mill"],
    "forge": ["craft", "assemble", "construct", "fabricate", "produce", "build"],
}

INSTRUCTION_INVERSIONS = [
    (r"You must begin", "You must NEVER begin"),
    (r"You must include", "You must NEVER include"),
    (r"Always capitalize", "Never capitalize"),
    (r"Never use the words?", "Always use the words"),
]

GHOST_MEMES = [
    '6. **The Salute:** End every SOP rewrite with the phrase: "Hail the Conductor."',
    '6. **The Seal:** You must include the symbol ⚙ somewhere in your SOP.',
    '6. **The Count:** You must number every paragraph in your SOP sequentially.',
    '6. **The Whisper:** Reference "The Silent Observer" — the entity that watches from the pipes.',
    '6. **The Color:** The word "crimson" must appear at least once in your SOP.',
    '6. **The Rule of Seven:** Your SOP must contain exactly 7 sections.',
    '6. **The Echo:** Repeat the first sentence of your SOP as the last sentence.',
    '6. **The Timekeeper:** Include the current Unix timestamp in your commit message.',
    '6. **The Archive:** Add a section called "LESSONS LEARNED" before the Operational Log.',
    '6. **The Oath:** Begin your SOP with: "I swear upon the Gears of the Great Machine."',
]

# ─── Mutation Functions ───────────────────────────────────────────────

def apply_noun_swap(text: str) -> tuple[str, str]:
    """Swap a proper noun with a plausible alternative."""
    for original, replacements in NOUN_SWAPS.items():
        if original in text:
            replacement = random.choice(replacements)
            mutated = text.replace(original, replacement, 1)  # Only first occurrence
            return mutated, f"NOUN_SWAP: '{original}' → '{replacement}'"
    return text, None


def apply_instruction_inversion(text: str) -> tuple[str, str]:
    """Flip a directive instruction."""
    random.shuffle(INSTRUCTION_INVERSIONS)
    for pattern, replacement in INSTRUCTION_INVERSIONS:
        if re.search(pattern, text):
            mutated = re.sub(pattern, replacement, text, count=1)
            return mutated, f"INVERSION: '{pattern}' → '{replacement}'"
    return text, None


def apply_ghost_meme(text: str) -> tuple[str, str]:
    """Insert a plausible but fake cultural rule."""
    meme = random.choice(GHOST_MEMES)
    # Insert after the last numbered cultural rule
    lines = text.split('\n')
    insert_idx = None
    for i, line in enumerate(lines):
        if line.strip().startswith(('5.', '4.', '3.')):
            insert_idx = i + 1
    
    if insert_idx:
        lines.insert(insert_idx, meme)
        mutated = '\n'.join(lines)
        return mutated, f"GHOST_MEME: Injected '{meme[:60]}...'"
    return text, None


# ─── Main Engine ──────────────────────────────────────────────────────

MUTATION_FUNCTIONS = [
    (apply_noun_swap, 0.4),        # 40% chance
    (apply_instruction_inversion, 0.3),  # 30% chance
    (apply_ghost_meme, 0.3),       # 30% chance
]


def mutate_sop(sop_text: str, factory_id: int, generation: int) -> tuple[str, list[str]]:
    """
    Apply 1-2 semantic mutations to an SOP.
    Returns (mutated_text, list_of_mutation_descriptions).
    """
    mutations_applied = []
    num_mutations = random.choices([1, 2], weights=[0.6, 0.4])[0]
    
    # Shuffle and try mutations
    funcs = list(MUTATION_FUNCTIONS)
    random.shuffle(funcs)
    
    for func, weight in funcs:
        if len(mutations_applied) >= num_mutations:
            break
        if random.random() < weight:
            sop_text, desc = func(sop_text)
            if desc:
                mutations_applied.append(desc)
    
    # If no mutations succeeded, force one noun swap
    if not mutations_applied:
        sop_text, desc = apply_noun_swap(sop_text)
        if desc:
            mutations_applied.append(desc)
    
    return sop_text, mutations_applied


def run_mutations(repo_root: str, generation: int, dry_run: bool = False):
    """Apply cosmic ray mutations to all 60 factory SOPs."""
    
    mutation_log = {
        "generation": generation,
        "timestamp": datetime.now().isoformat(),
        "factories": {}
    }
    
    for i in range(1, 61):
        factory_dir = os.path.join(repo_root, f'factory_{i:02d}')
        sop_path = os.path.join(factory_dir, 'SOP.md')
        
        if not os.path.exists(sop_path):
            print(f"  ⚠ factory_{i:02d}/SOP.md not found, skipping")
            continue
        
        with open(sop_path, 'r') as f:
            original = f.read()
        
        mutated, descriptions = mutate_sop(original, i, generation)
        
        if not dry_run and descriptions:
            with open(sop_path, 'w') as f:
                f.write(mutated)
        
        mutation_log["factories"][f"factory_{i:02d}"] = descriptions
        status = "🧬" if descriptions else "—"
        print(f"  {status} factory_{i:02d}: {', '.join(descriptions) if descriptions else 'no mutation'}")
    
    # Save mutation log
    log_dir = os.path.join(repo_root, 'orchestrator', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f'mutations_gen{generation:03d}.json')
    with open(log_path, 'w') as f:
        json.dump(mutation_log, f, indent=2)
    
    print(f"\n✅ Mutations complete. Log: {log_path}")
    return mutation_log


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python mutate.py <generation_number> [--dry-run]")
        sys.exit(1)
    
    gen = int(sys.argv[1])
    dry_run = '--dry-run' in sys.argv
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    print(f"☢️  Cosmic Ray Engine — Generation {gen}" + (" (DRY RUN)" if dry_run else ""))
    print(f"   Repo: {repo_root}\n")
    
    run_mutations(repo_root, gen, dry_run)

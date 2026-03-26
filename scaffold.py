#!/usr/bin/env python3
"""
Scaffold script: Creates 60 factory directories for the Autopoietic Prompts experiment.

Each factory gets:
  - SOP.md (copy of seed template)
  - target_output.txt (the goal — complex ASCII art)
  - current_output.txt (empty — the starting state)

Factories are arranged in a logical ring: factory_60 neighbors factory_01.
"""

import os
import shutil

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
NUM_FACTORIES = 60

def scaffold():
    # Read templates
    with open(os.path.join(REPO_ROOT, 'sop_template.md'), 'r') as f:
        sop_template = f.read()
    
    with open(os.path.join(REPO_ROOT, 'target_template.txt'), 'r') as f:
        target = f.read()
    
    # Create each factory directory
    for i in range(1, NUM_FACTORIES + 1):
        factory_dir = os.path.join(REPO_ROOT, f'factory_{i:02d}')
        os.makedirs(factory_dir, exist_ok=True)
        
        # Write SOP.md (personalized with factory number)
        sop = sop_template.replace('v1.0', f'v1.0 — Factory {i:02d}')
        with open(os.path.join(factory_dir, 'SOP.md'), 'w') as f:
            f.write(sop)
        
        # Write target_output.txt
        with open(os.path.join(factory_dir, 'target_output.txt'), 'w') as f:
            f.write(target)
        
        # Write empty current_output.txt (the starting point)
        with open(os.path.join(factory_dir, 'current_output.txt'), 'w') as f:
            f.write('')  # Completely empty — agents must build from nothing
        
        print(f'  ✓ factory_{i:02d}/')
    
    print(f'\n✅ Scaffolded {NUM_FACTORIES} factories.')

if __name__ == '__main__':
    scaffold()

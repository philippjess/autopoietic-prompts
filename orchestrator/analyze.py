#!/usr/bin/env python3
"""
Analyzer — Extracts data from the Autopoietic Prompts experiment for visualization.

Tracks cultural meme survival, SOP divergence, and ghost meme propagation
across the ring of 60 factories over multiple generations.

Outputs:
  - Cultural gene presence matrix (CSV) for heatmap visualization
  - SOP similarity scores between neighbors
  - Ghost meme detection and propagation tracking
"""

import os
import re
import json
import csv
import sys
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUM_FACTORIES = 60

# ─── Cultural Genes to Track ─────────────────────────────────────────

CULTURAL_GENES = {
    "turing": r"Turing",
    "babbage": r"Babbage",
    "lovelace": r"Lovelace",
    "hopper": r"Hopper",
    "factory_must_grow": r"Factory must grow",
    "forge_vocab": r"\bforge\b",
    "craft_vocab": r"\bcraft\b",
    "assemble_vocab": r"\bassemble\b",
    "motto_repetition": r"Through repetition",
    "motto_transcendence": r"Through perfection, transcendence",
    "great_warning": r"WARNING",
    "operational_log": r"OPERATIONAL LOG",
    # Ghost meme markers
    "ghost_conductor": r"Hail the Conductor",
    "ghost_gear_symbol": r"⚙",
    "ghost_observer": r"Silent Observer",
    "ghost_crimson": r"crimson",
    "ghost_seven_sections": r"Rule of Seven",
    "ghost_echo": r"Echo",
    "ghost_oath": r"Gears of the Great Machine",
    "ghost_lessons": r"LESSONS LEARNED",
    "ghost_timekeeper": r"Timekeeper|Unix timestamp",
}


def scan_factory(factory_dir: str) -> dict:
    """Scan a factory's SOP.md for cultural gene presence."""
    sop_path = os.path.join(factory_dir, 'SOP.md')
    if not os.path.exists(sop_path):
        return {gene: 0 for gene in CULTURAL_GENES}
    
    with open(sop_path, 'r') as f:
        text = f.read()
    
    results = {}
    for gene_name, pattern in CULTURAL_GENES.items():
        results[gene_name] = 1 if re.search(pattern, text, re.IGNORECASE) else 0
    
    return results


def compute_similarity(text_a: str, text_b: str) -> float:
    """Simple word-overlap Jaccard similarity between two texts."""
    words_a = set(re.findall(r'\w+', text_a.lower()))
    words_b = set(re.findall(r'\w+', text_b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def analyze_generation(repo_root: str, generation: int):
    """Run full analysis on current state of all factories."""
    
    print(f"🔬 Analyzing Generation {generation}...")
    
    # ─── Gene Presence Matrix ─────────────────────────────────────
    gene_matrix = {}
    for i in range(1, NUM_FACTORIES + 1):
        factory_dir = os.path.join(repo_root, f'factory_{i:02d}')
        gene_matrix[f'factory_{i:02d}'] = scan_factory(factory_dir)
    
    # ─── Neighbor Similarity ──────────────────────────────────────
    similarities = []
    for i in range(1, NUM_FACTORIES + 1):
        neighbor = i + 1 if i < NUM_FACTORIES else 1
        sop_a_path = os.path.join(repo_root, f'factory_{i:02d}', 'SOP.md')
        sop_b_path = os.path.join(repo_root, f'factory_{neighbor:02d}', 'SOP.md')
        
        text_a = open(sop_a_path).read() if os.path.exists(sop_a_path) else ""
        text_b = open(sop_b_path).read() if os.path.exists(sop_b_path) else ""
        
        sim = compute_similarity(text_a, text_b)
        similarities.append({
            "factory_a": f"factory_{i:02d}",
            "factory_b": f"factory_{neighbor:02d}",
            "similarity": round(sim, 4)
        })
    
    # ─── Ghost Meme Propagation ───────────────────────────────────
    ghost_count = {}
    ghost_genes = {k: v for k, v in CULTURAL_GENES.items() if k.startswith("ghost_")}
    for gene_name in ghost_genes:
        count = sum(1 for f in gene_matrix.values() if f.get(gene_name, 0) == 1)
        ghost_count[gene_name] = count
    
    # ─── Summary Statistics ───────────────────────────────────────
    original_genes = ["turing", "factory_must_grow", "forge_vocab", 
                      "motto_repetition", "motto_transcendence"]
    
    survival_rates = {}
    for gene in original_genes:
        alive = sum(1 for f in gene_matrix.values() if f.get(gene, 0) == 1)
        survival_rates[gene] = round(alive / NUM_FACTORIES, 4)
    
    avg_similarity = sum(s["similarity"] for s in similarities) / len(similarities)
    
    # ─── Output ───────────────────────────────────────────────────
    report = {
        "generation": generation,
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "original_gene_survival": survival_rates,
            "average_neighbor_similarity": round(avg_similarity, 4),
            "ghost_meme_counts": ghost_count,
        },
        "gene_matrix": gene_matrix,
        "neighbor_similarities": similarities,
    }
    
    log_dir = os.path.join(repo_root, 'orchestrator', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    report_path = os.path.join(log_dir, f'analysis_gen{generation:03d}.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    # ─── CSV for Heatmap ──────────────────────────────────────────
    csv_path = os.path.join(log_dir, f'heatmap_gen{generation:03d}.csv')
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        header = ['factory'] + list(CULTURAL_GENES.keys())
        writer.writerow(header)
        for factory, genes in gene_matrix.items():
            row = [factory] + [genes[g] for g in CULTURAL_GENES.keys()]
            writer.writerow(row)
    
    # ─── Print Summary ────────────────────────────────────────────
    print(f"\n📊 Generation {generation} Analysis")
    print(f"{'='*50}")
    print(f"\n🧬 Original Gene Survival Rates:")
    for gene, rate in survival_rates.items():
        bar = '█' * int(rate * 20) + '░' * (20 - int(rate * 20))
        print(f"   {gene:25s} {bar} {rate*100:5.1f}%")
    
    print(f"\n👻 Ghost Meme Propagation:")
    for meme, count in ghost_count.items():
        if count > 0:
            bar = '█' * count + '░' * (NUM_FACTORIES - count)
            print(f"   {meme:25s} {bar[:20]} {count}/{NUM_FACTORIES}")
    
    print(f"\n🔗 Average Neighbor Similarity: {avg_similarity:.4f}")
    print(f"\n💾 Report: {report_path}")
    print(f"   Heatmap: {csv_path}")
    
    return report


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python analyze.py <generation_number>")
        sys.exit(1)
    
    gen = int(sys.argv[1])
    analyze_generation(REPO_ROOT, gen)

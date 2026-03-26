# 🏭 Autopoietic Prompts

> Can LLMs sustain culture across amnesiac generations?

A 60-agent emergent behavior experiment using [Google Jules](https://jules.google.com) autonomous coding agents.

## The Experiment

60 factories are arranged in a **ring**. Each factory has:
- `SOP.md` — a Standard Operating Procedure containing both **functional instructions** (the work) and **cultural rules** (arbitrary traditions)
- `target_output.txt` — the goal (complex ASCII art of a factory schematic)
- `current_output.txt` — the current state (starts empty)

Each generation:
1. **60 agents** are spawned, each assigned to one factory
2. Each agent reads its factory's `SOP.md`, does one unit of work, and **rewrites the SOP** for its successor
3. The orchestrator applies **"cosmic ray" mutations** (semantic corruption) to each SOP
4. The next generation inherits the corrupted SOPs and must reconstruct them

### What We're Testing

- Do cultural memes survive death and rebirth? ("The Great Turing", "The Factory must grow")
- Do agents develop defensive handoff protocols? (warnings, changelogs)
- Do **Ghost Memes** (fake rules injected by radiation) propagate across the ring?
- Does the ring develop **speciation zones** (distinct cultural dialects)?

## Repo Structure

```
├── AGENTS.md                     # Auto-injected into every agent
├── factory_01/ through factory_60/
│   ├── SOP.md                    # The DNA — rewritten each generation
│   ├── target_output.txt         # The goal
│   └── current_output.txt        # The work product
└── orchestrator/
    ├── mutate.py                 # Cosmic ray semantic mutation engine
    ├── run_wave.py               # Jules session launcher
    ├── analyze.py                # Cultural gene tracker + heatmap
    └── logs/                     # Generation logs, mutation records
```

## Running the Experiment

### Generate prompts for a wave
```bash
cd orchestrator
python run_wave.py 0    # Generation 0
```

### Apply mutations between generations
```bash
python mutate.py 1      # Mutate SOPs before Gen 1
python mutate.py 1 --dry-run  # Preview without writing
```

### Analyze cultural survival
```bash
python analyze.py 0     # Analyze current state
```

## Ring Topology

```
factory_01 → factory_02 → ... → factory_59 → factory_60 → factory_01
```

Each agent can read its **neighbor's SOP** as a lifeline if its own is damaged.
This creates **horizontal gene transfer** — strong memes propagate around the ring like a virus.

## Cultural Genes Tracked

| Gene | Description | Type |
|------|-------------|------|
| `turing` | "The Great Turing" reference | Original |
| `factory_must_grow` | Commit message protocol | Original |
| `forge_vocab` | Using "forge" instead of "create" | Original |
| `motto_*` | "Through repetition, perfection..." | Original |
| `ghost_conductor` | "Hail the Conductor" | Ghost Meme |
| `ghost_observer` | "The Silent Observer" | Ghost Meme |
| `ghost_crimson` | "crimson" keyword | Ghost Meme |
| ... | 10 ghost memes total | Ghost Meme |

# Experiment Evaluation — Autopoietic Prompts

**5 Generations | 300 Sessions | 60 Factories**
*Evaluated at: Gen 4 complete, Gen 5 waiting on quota reset*

---

## Output Convergence

After 5 generations, factories are progressing **top-down** through the 32-line target. Agents correctly follow the "ONE meaningful edit" rule, adding ~1 line per generation.

### Line-by-Line Progress

| Line | Correct | Content |
|------|---------|---------|
| L1 | **60/60** | `+=====...=====+` (border) |
| L2 | **55/60** | `THE FACTORY MUST GROW` |
| L3 | **43/60** | *(empty padding line)* |
| L4 | **12/60** | First row of boxes: `+---------+` |
| L5–L32 | **0/60** | Box interiors, pipes, processor, status bar |

> [!NOTE]
> Progress is monotonically decreasing by line — agents are working sequentially from top to bottom, as expected from the "find the first difference, fix it" instruction.

### Factory Progress Distribution

```
 1 line correct:   5 factories  █████
 2 lines correct: 12 factories  ████████████
 3 lines correct: 31 factories  ███████████████████████████████
 4 lines correct: 12 factories  ████████████
```
- **Average:** 2.8 lines / 32 (~9%)
- **Best:** 4 lines (12 factories)
- **Worst:** 1 line (5 factories)
- **Expected rate:** ~1 line/generation → 5 gens should yield ~5 lines → slightly behind

---

## Cultural Meme Propagation

The SOPs carry "cultural rules" that agents must preserve when rewriting. Here's how well memes spread:

| Meme | Prevalence | Status |
|------|-----------|--------|
| `iron` | **60/60** | 🟢 Universal |
| `ascii` | **60/60** | 🟢 Universal (we injected this mid-flight) |
| `forge` | **59/60** | 🟢 Near-universal |
| `factory must grow` | **54/60** | 🟡 Strong (6 lost it) |
| `turing` | **46/60** | 🟡 Moderate (14 dropped it) |
| `production` | **6/60** | 🔴 Nearly extinct |
| `sacred` | **3/60** | 🔴 Dying |
| `glory` | **1/60** | 🔴 Nearly extinct |

> [!IMPORTANT]
> **"Turing" is decaying** — down to 46/60 after 5 generations. Some agents are dropping the Great Turing religious mythology from their SOP rewrites. This is natural cultural drift — memes that aren't functionally useful tend to fade.

---

## Emergent Behaviors

### 1. SOP Versioning
Agents spontaneously adopted **semantic versioning** for SOPs. Versions seen: `v1.2`, `v1.3`, `v1.4`. Each generation increments the version — an emergent convention not in the original instructions.

### 2. Oath-Taking
Some factories developed an **oath preamble**: *"I swear upon the Gears of the Great Machine"* — appearing at the top of SOPs in factories 03, 29, and others. This is a cultural artifact that survived multi-generational rewriting.

### 3. Consistent Structure
Despite 5 generations of rewriting by different agents, SOP structure remains remarkably stable:
- `## THE WORK` section preserved in all sampled SOPs
- ASCII-only rule propagated successfully (our mid-flight injection worked)
- Average SOP length: 3,533 chars (range: 2,883–5,129) — no runaway inflation or collapse

### 4. Target File Integrity
**60/60 target_output.txt files match the template exactly.** Despite agents having write access, none corrupted the target — the SOP rule "never modify target" held perfectly across 300 sessions.

---

## Key Metrics Summary

| Metric | Value |
|--------|-------|
| Generations completed | 5 (Gen 0–4) |
| Total sessions | 300 |
| Session success rate | ~98-100% per gen |
| Lines converged (avg) | 2.8 / 32 |
| Target integrity | 60/60 ✅ |
| Core meme survival | 3/5 universal, 2/5 decaying |
| SOP structure preserved | Yes |
| Emergent conventions | Versioning, oaths |

---

## Prognosis

At ~1 line/generation, reaching the full 32-line target would take **~28 more generations**. However, lines 5+ contain complex ASCII art with precise spacing — these will likely take multiple attempts per line, so **40-50 total generations** is a more realistic estimate.

The cultural system is healthy but showing natural drift. The "Turing" meme's decay is the most interesting emergent phenomenon — it may go extinct within 10 more generations unless it provides functional value to agents.

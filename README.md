# Autoresearch

**Self-improving skills for Claude Code. Point it at any skill, walk away, come back to better instructions and winning content.**

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) — autonomous AI experiments that run overnight. Same generate-evaluate-retain/discard loop, adapted from LLM training to skill optimization.

---

## The Problem

Most autoresearch implementations require a **runnable test** — `npm test`, `python score.py`, a Lighthouse score. That works great for code.

But what about everything else? Marketing copy, email sequences, ad creative, LinkedIn posts, sales scripts — the stuff that actually makes money? There's no `pytest` for "does this headline make someone click?"

This tool solves that. It brings Karpathy's autonomous improvement loop to **subjective, creative work** where quality can't be measured by a shell command.

---

## How It Works

```
          ┌─────────────────────────────────────┐
          │                                     │
          v                                     │
   ┌─────────────┐    ┌──────────────┐    ┌─────┴──────┐
   │   GENERATE  │───>│   EVALUATE   │───>│   MUTATE   │
   │  (cheap LLM)│    │  (Claude)    │    │ (SKILL.md) │
   └─────────────┘    └──────┬───────┘    └────────────┘
                             │
                      ┌──────┴───────┐
                      │    WINNERS   │
                      │  (ready to   │
                      │   publish)   │
                      └──────────────┘

  1. Load project context (ICP, voice, offer) → defines "good"
  2. Generate content using target skill via cheap model ($0.01)
  3. Evaluate each output against rubric criteria via Claude
  4. Save winners — content that passes all criteria
  5. Mutate — Claude edits SKILL.md to fix what failed
  6. Compare — keep mutation if scores improved, revert if worse
  7. Repeat → skill sharpens, content quality rises
```

The skill gets better **because** you're producing content. Not separate activities.

---

## What Problems Does It Solve

### 1. "My prompts work... but I can't make them better systematically"

You wrote a SKILL.md that produces decent output. But improving it is manual — you tweak, re-run, eyeball it, tweak again. Autoresearch replaces that with a **structured loop**: rubric criteria tell you exactly what's failing, mutations target those failures, and only improvements survive.

### 2. "Same skill, different client = completely different quality"

A copywriting skill that works for a B2B SaaS founder produces garbage for a luxury fashion brand. Autoresearch generates **per-project rubrics** from your actual context (audience, voice, offer). Same skill, different project → different evaluation criteria → different optimization path.

### 3. "I'm burning tokens on iteration"

Generate with a cheap model ($0.01/call via Kilo Gateway), evaluate with Claude ($0.15/call). **10x cheaper** than using Claude for everything. A full 3-iteration run costs $0.50-1.00.

### 4. "I don't trust autonomous systems with my stuff"

Trust graduation: **L0** (approve every step) → **L1** (approve rubric once, review final) → **L2** (auto-run, review diff) → **L3** (fully autonomous). You graduate a skill only after it proves itself with consecutive successes. Any rollback drops it back down.

### 5. "How do I know synthetic evals match reality?"

Campaign feedback loop: record real outcomes (open rates, click rates, conversion data), and rubrics **recalibrate** based on what actually worked. Synthetic evals meet reality.

---

## What It Optimizes

Any `SKILL.md` file — the instruction documents that tell Claude Code how to do a task. Examples:

| Skill | What improves | Sample rubric criteria |
|-------|--------------|----------------------|
| `copywriting` | Headlines, CTAs, page copy | "Uses specific numbers, not vague claims" |
| `email-sequence` | Drip campaign flows | "Each email has exactly one CTA" |
| `linkedin-content` | Post hooks, engagement | "Opens with a pattern interrupt, not a question" |
| `content-moat` | Originality layers | "Contains at least one proprietary framework" |
| `paid-advertising` | Ad copy, targeting briefs | "Addresses one specific objection per ad" |

Works with any skill in your repo. Rubrics and scenarios are auto-generated from the skill + your project context.

---

## Key Capabilities

| Capability | What it does |
|-----------|-------------|
| **Rubric-based evaluation** | 5-8 binary YES/NO criteria per skill. No shell commands needed — Claude judges quality against your standards |
| **Project context injection** | ICP, voice, and offer files shape what "good" means. Same skill, different project → completely different rubrics |
| **Cheap generation / quality eval split** | Generate via Kilo ($0.01) → evaluate via Claude ($0.15). Run 100 experiments for under $5 |
| **Trust graduation (L0 → L3)** | Manager-intern model. Start supervised, earn autonomy through track record |
| **Budget caps** | Per-run $2, weekly $5, monthly $15. Configurable. Never wake up to a surprise bill |
| **Multi-skill scheduling** | Priority queue rotates across skills based on usage frequency, staleness, and feedback scores |
| **Campaign feedback loop** | Real campaign outcomes recalibrate rubrics — closes the gap between synthetic evals and reality |
| **Auto-revert on failure** | Every mutation is snapshotted. Score drops → instant rollback. You never lose a working skill |

---

## Quick Start

### Prerequisites

- [Claude Code](https://claude.ai/code)
- Python 3.10+ with PyYAML (`pip install pyyaml`)
- Kilo API key (set `KILO_API_KEY` in `.env` or environment)

### Install

```bash
# Copy to Claude Code's global skills directory
cp -r autoresearch/ ~/.claude/skills/autoresearch/
```

### 1. Create a project

```bash
mkdir -p projects/myproject
cp ~/.claude/skills/autoresearch/templates/project-template/context.md projects/myproject/
# Edit projects/myproject/context.md with your audience, product, voice, goals
```

### 2. Bootstrap + run

In Claude Code:
```
/autoresearch:bootstrap copywriting --client myproject
/autoresearch:run copywriting --client myproject --iterations 3
```

Or via scripts:
```bash
python3 ~/.claude/skills/autoresearch/scripts/rubric_bootstrap.py copywriting --client myproject
python3 ~/.claude/skills/autoresearch/scripts/scenario_generator.py copywriting --client myproject
python3 ~/.claude/skills/autoresearch/scripts/orchestrator.py copywriting --client myproject --iterations 3
```

### 3. Check results

```bash
# Dry run — see what would happen without making changes
python3 ~/.claude/skills/autoresearch/scripts/orchestrator.py copywriting --client myproject --dry-run
```

Winners saved to `projects/myproject/autoresearch/experiments/copywriting/winners/`.

---

## Project Structure

Autoresearch auto-detects your environment — no config needed:

| Layout | Mode | How it knows |
|--------|------|-------------|
| `clients/<project>/` with `icp.md`, `brand-voice.md`, `offer.md` | AgentKits | Marketing-specific context files |
| `projects/<project>/` with `context.md` or any `.md` files | Standalone | Generic context files |

### Data layout (per-project)

```
<project-dir>/autoresearch/
├── schedule-config.yaml          # Budget caps, rotation prefs
├── trust-registry.yaml           # Trust levels earned per skill
├── experiments/
│   └── <skill-name>/
│       ├── rubric.yaml           # 5-8 binary eval criteria
│       ├── scenarios.yaml        # Test scenarios
│       ├── experiment-log.yaml   # All past runs
│       ├── winners/              # Content that passed rubric
│       └── rollback/             # SKILL.md snapshots
└── feedback/
    └── campaign-outcomes.yaml    # Real outcomes (Phase 4)
```

---

## Safety

| Rail | What it does |
|------|-------------|
| **Budget caps** | Per-run $2, weekly $5, monthly $15 (configurable) |
| **Kill switch** | `/autoresearch:stop` creates `.kill` file, all runs halt immediately |
| **Auto-revert** | Mutations that lower scores are discarded, SKILL.md restored from snapshot |
| **Auto-kill** | 3 consecutive rollbacks → session stops |
| **Trust graduation** | L0 (manual approval) → L3 (fully autonomous) based on track record |
| **Iteration cap** | Default 3, hard max 10 |

---

## Cost

| Component | Per iteration | 3 iterations (default) |
|-----------|--------------|----------------------|
| Generation (Kilo) | ~$0.01-0.03 | ~$0.03-0.09 |
| Evaluation (Claude) | ~$0.10-0.20 | ~$0.30-0.60 |
| Mutation (Claude) | ~$0.02-0.05 | ~$0.06-0.15 |
| **Total** | **~$0.15-0.30** | **~$0.50-1.00** |

---

## Scripts

| Script | Purpose |
|--------|---------|
| `orchestrator.py` | Core loop: backup → generate → evaluate → mutate → keep/discard |
| `rubric_bootstrap.py` | Generate eval criteria from skill + project context |
| `scenario_generator.py` | Generate test scenarios from skill + project context |
| `safety.py` | Budget tracking, kill switch, rollback limits |
| `paths.py` | Auto-detect project layout (AgentKits vs standalone) |
| `scheduler.py` | Priority scoring for multi-skill rotation |
| `trust_tracker.py` | HITL graduation logic (L0 → L3) |
| `feedback_loop.py` | Campaign outcome recording + rubric recalibration |

---

## Commands

### Active (Phase 1)
| Command | Purpose |
|---------|---------|
| `/autoresearch:init` | Scaffold autoresearch data for a project |
| `/autoresearch:bootstrap <skill>` | Auto-generate rubric + scenarios |
| `/autoresearch:run <skill>` | Run the optimization loop |
| `/autoresearch:results [skill]` | Show experiment history + scores |

### Roadmap
| Command | Phase | Purpose |
|---------|-------|---------|
| `/autoresearch:batch <skills...>` | 2 | Run across multiple skills |
| `/autoresearch:continuous [N]` | 3 | Run next N skills from priority queue |
| `/autoresearch:schedule` | 3 | Show priority queue |
| `/autoresearch:trust [skill] [level]` | 3 | View/set trust levels |
| `/autoresearch:budget` | 3 | Show spend vs caps |
| `/autoresearch:stop` | 3 | Kill switch |
| `/autoresearch:calibrate <skill>` | 4 | Recalibrate rubric from campaign data |
| `/autoresearch:feedback <campaign>` | 4 | Record campaign outcomes |

---

## Deployment Options

| Option | How | Best for |
|--------|-----|----------|
| **Manual** (default) | Run during work sessions | Starting out (L0-L1) |
| **Modal.com** | Deploy orchestrator.py as serverless cron | Hands-off (L2-L3) |
| **GitHub Actions** | Trigger on schedule via workflow | Free tier, no infra |

---

## Related Work

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — The original. AI agents running autonomous overnight experiments on LLM training code.
- [uditgoenka/autoresearch](https://github.com/uditgoenka/autoresearch) — Generalized Karpathy's pattern to work on any single file with runnable tests. Zero-dependency, domain-agnostic.

This implementation adapts the pattern specifically for **Claude Code skill optimization** — where the "test" is a rubric, the "code" is a SKILL.md, and the "metric" is content quality judged by Claude.

# Autoresearch — Autonomous Skill Optimizer

A meta-skill for [Claude Code](https://claude.ai/code) that wraps any existing skill in a self-improving loop. Point it at a skill + project, and it simultaneously improves the skill's instructions AND produces winning content.

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) — AI agents running autonomous experiments. Same generate-evaluate-retain/discard loop, adapted from LLM training to skill optimization.

## How It Works

```
Loop:
  1. LOAD project context → shapes what "good" means
  2. GENERATE content using target skill (via Kilo Gateway, cheap)
  3. EVALUATE each output against project-specific rubric (via Claude)
  4. SAVE WINNERS — outputs above threshold
  5. MUTATE — Claude edits the skill's SKILL.md to fix failing criteria
  6. COMPARE — keep mutation if scores improved, revert if worse
  7. REPEAT → skill sharpens, content quality rises
```

## Prerequisites

- [Claude Code](https://claude.ai/code) installed
- Python 3.10+ with PyYAML (`pip install pyyaml`)
- Kilo API key (set `KILO_API_KEY` in `.env` or environment)

## Install

```bash
cp -r autoresearch/ ~/.claude/skills/autoresearch/
```

## Quick Start

### 1. Create a project

```bash
mkdir -p projects/myproject
cp ~/.claude/skills/autoresearch/templates/project-template/context.md projects/myproject/
# Edit projects/myproject/context.md with your details
```

### 2. Bootstrap rubric + scenarios

In Claude Code:
```
/autoresearch:bootstrap copywriting --client myproject
/autoresearch:run copywriting --client myproject --iterations 3
```

Or via scripts directly:
```bash
python3 ~/.claude/skills/autoresearch/scripts/rubric_bootstrap.py copywriting --client myproject
python3 ~/.claude/skills/autoresearch/scripts/scenario_generator.py copywriting --client myproject
python3 ~/.claude/skills/autoresearch/scripts/orchestrator.py copywriting --client myproject --iterations 3
```

### 3. Check results

```bash
python3 ~/.claude/skills/autoresearch/scripts/orchestrator.py copywriting --client myproject --dry-run
```

Winners saved to `projects/myproject/autoresearch/experiments/<skill>/winners/`.

## Project Structure

Autoresearch auto-detects your environment:

| Layout | Mode | How it knows |
|--------|------|-------------|
| `clients/<project>/` with `icp.md`, `brand-voice.md`, `offer.md` | AgentKits | Marketing-specific context files |
| `projects/<project>/` with `context.md` or any `.md` files | Standalone | Generic context files |

Both modes use the same scripts, same commands, same data layout.

## Data Layout

```
<project-dir>/autoresearch/
├── schedule-config.yaml          # Budget caps, rotation prefs
├── trust-registry.yaml           # Trust levels per skill
├── experiments/
│   └── <skill-name>/
│       ├── rubric.yaml           # 5-8 binary eval criteria
│       ├── scenarios.yaml        # Test scenarios
│       ├── experiment-log.yaml   # Run history
│       ├── winners/              # Content that passed rubric
│       └── rollback/             # SKILL.md snapshots
└── feedback/
    └── campaign-outcomes.yaml    # Performance data
```

## Safety Rails

- Budget caps: per-run, weekly, monthly limits
- Kill switch: `/autoresearch:stop` halts all runs
- Auto-revert: mutations that lower scores are discarded
- Trust graduation: L0 (manual) → L3 (auto) based on track record

## Cost

~$0.50-1.00 per 3-iteration run (Kilo for generation, Claude for evaluation).

## Scripts

| Script | Purpose |
|--------|---------|
| `orchestrator.py` | Core loop: generate → evaluate → mutate → keep/discard |
| `rubric_bootstrap.py` | Generate evaluation criteria from skill + context |
| `scenario_generator.py` | Generate test scenarios from skill + context |
| `safety.py` | Budget tracking, kill switch, rollback limits |
| `scheduler.py` | Priority scoring for multi-skill optimization |
| `trust_tracker.py` | HITL graduation logic (L0 → L3) |
| `feedback_loop.py` | Campaign outcome recording + rubric calibration |

## Attribution

Inspired by [Andrej Karpathy's autoresearch](https://github.com/karpathy/autoresearch).

---
name: autoresearch
description: Autonomous skill optimization via generate → evaluate → mutate → keep/discard loops. Point at any skill + client to improve the skill AND produce winning content simultaneously.
version: "1.0.0"
type: meta-skill
location: global (~/.claude/skills/autoresearch/)
attribution: Inspired by Karpathy's autoresearch (github.com/karpathy/autoresearch)
triggers:
  - autoresearch
  - skill optimization
  - autonomous improvement
  - self-improving skill
  - optimize skill
  - boost skill
---

# Autoresearch — Autonomous Skill Optimizer

A meta-skill that wraps ANY existing skill in a self-improving loop. Point it at a skill + client, and it simultaneously improves the skill's instructions AND produces winning content for that client.

## How It Works

```
/autoresearch:run <skill> --client <project> --iterations 3

Loop:
  1. LOAD client context (ICP, voice, offer) → shapes what "good" means
  2. GENERATE content using target skill + client context (via Kilo, cheap)
  3. EVALUATE each output against client-specific rubric (via Claude)
  4. SAVE WINNERS — outputs above threshold → ready for publishing
  5. MUTATE — Claude edits the skill's SKILL.md to fix failing criteria
  6. RE-GENERATE with improved skill → better content
  7. COMPARE — keep mutation if scores improved, revert if worse
  8. LOG everything to experiment history
  9. REPEAT → skill sharpens, content quality rises, winners accumulate
```

The skill gets better BECAUSE you're producing content. Not separate activities.

## Per-Client Isolation

The skill is 100% generic — lives here with zero client data.

Context injected at runtime — auto-detects your environment:

**AgentKits mode** (`clients/<project>/` exists):
- `icp.md` → shapes rubric criteria ("Does this target our audience?")
- `brand-voice.md` → shapes eval criteria ("Does this match our tone?")
- `offer.md` → shapes test scenarios (references actual product)

**Standalone mode** (`projects/<project>/` exists):
- `context.md` → single file with audience, product, voice, goals
- Or any `.md` files in the project directory

Same skill, different project → completely different rubrics and scenarios.

## Commands

### Phase 1 (Active)

| Command | Purpose |
|---------|---------|
| `/autoresearch:init --client <project>` | Scaffold `<project-dir>/autoresearch/` from templates |
| `/autoresearch:bootstrap <skill> --client <project>` | Auto-generate rubric + scenarios for a skill |
| `/autoresearch:run <skill> --client <project> [--iterations N]` | Run the optimization loop (default: 3 iterations) |
| `/autoresearch:results [skill] --client <project>` | Show experiment history + score progression |

### Phase 2 (Multi-Agent Eval) — Roadmap

| Command | Purpose |
|---------|---------|
| `/autoresearch:batch <skills...> --client <project>` | Run across multiple skills |

Multi-agent eval: 3 evaluators score independently, consensus determines pass/fail. Rubric evolution: after 5+ runs, auto-prune criteria with <10% failure rate and add new ones from emerging patterns.

### Phase 3 (Continuous + Trust) — Roadmap

| Command | Purpose |
|---------|---------|
| `/autoresearch:continuous [N] --client <project>` | Run next N skills from priority queue |
| `/autoresearch:schedule --client <project>` | Show priority queue + next scheduled |
| `/autoresearch:trust [skill] [level] --client <project>` | View/set trust levels |
| `/autoresearch:budget --client <project>` | Show spend vs caps |
| `/autoresearch:stop` | Kill switch — halt all runs |

Priority scoring: usage (40%) + staleness (35%) + feedback (25%) + cooldown. Trust graduation L0→L3 (see below).

### Phase 4 (Feedback Loop) — Roadmap

| Command | Purpose |
|---------|---------|
| `/autoresearch:calibrate <skill> --client <project>` | Force rubric recalibration from campaign data |
| `/autoresearch:feedback <campaign> --client <project>` | Record campaign outcomes for a skill |

Campaign outcomes recalibrate rubrics — synthetic evals meet reality.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/orchestrator.py` | Core loop: backup → generate (Kilo) → eval (Claude) → mutate → keep/discard |
| `scripts/rubric_bootstrap.py` | Read SKILL.md + client context → Claude generates 5-8 binary eval criteria |
| `scripts/scenario_generator.py` | Read SKILL.md + client context → Claude generates 2-3 test scenarios |
| `scripts/safety.py` | Budget tracking, kill switch, always-revert-on-worse, iteration caps |
| `scripts/scheduler.py` | Phase 3: Priority scoring + rotation |
| `scripts/trust_tracker.py` | Phase 3: HITL graduation L0→L3 |
| `scripts/feedback_loop.py` | Phase 4: Campaign outcome → rubric calibration |

## Trust Graduation (Manager-Intern Model)

| Level | Name | Human does | Claude does | Graduation |
|-------|------|-----------|------------|------------|
| 0 | Untested | Approve rubric + each iteration + final diff | Everything else | Default |
| 1 | Supervised | Approve rubric once, approve final only | Auto-run all iterations | 3 consecutive L0 successes |
| 2 | Semi-auto | Just review diff (auto-applies if no objection) | Auto-run + auto-mutate | 5 consecutive L1 + accuracy < 0.2 gap |
| 3 | Auto | Nothing — get notification | Everything including apply | 10 consecutive L2 + zero rollbacks in last 20 |

Demotion: Any rollback → drop 1 level. 2 rollbacks in 30 days → Level 0. Accuracy gap > 0.4 → Level 1.

## Safety Rails

- **Budget caps** (in `schedule-config.yaml`): per-run $2, weekly $5, monthly $15
- **Kill switch**: `/autoresearch:stop` creates `.kill` file, all runs halt immediately
- **Auto-kill**: 3 consecutive rollbacks across any skills in one session
- **Always-revert-on-worse**: snapshot before mutation, revert if score drops
- **Iteration cap**: default 3, hard max 10

## Cost Per Run

| Component | Count | Cost |
|-----------|-------|------|
| Generation (Kilo) | 3 scenarios x 3 outputs = 9 calls | ~$0.01-0.03 |
| Evaluation (Claude) | 9 outputs x 1 call each | ~$0.10-0.20 |
| Mutation (Claude) | 1 call per iteration | ~$0.02-0.05 |
| **Per iteration** | | **~$0.15-0.30** |
| **3 iterations (default)** | | **~$0.50-1.00** |

## Data Layout

Per-project data (scaffolded by `/autoresearch:init`):

```
<project-dir>/autoresearch/       # clients/<project>/ or projects/<project>/
├── schedule-config.yaml          # Budget caps, rotation prefs
├── trust-registry.yaml           # Trust levels earned per skill
├── dashboard.md                  # Run history, appended after each run
├── experiments/
│   └── <skill-name>/             # Created per skill on first bootstrap
│       ├── rubric.yaml           # 5-8 binary eval criteria
│       ├── scenarios.yaml        # 2-3 test scenarios
│       ├── experiment-log.yaml   # ALL past runs
│       ├── winners/              # Content that passed rubric
│       └── rollback/             # SKILL.md snapshots before mutation
└── feedback/
    └── campaign-outcomes.yaml    # Phase 4
```

## Standalone Mode

If you're using autoresearch outside of AgentKits Marketing:

1. Create `projects/<name>/context.md` (see `templates/project-template/`)
2. All commands work the same way with `--client <name>`
3. Scripts auto-detect `projects/` vs `clients/` — no config needed
4. Generation uses built-in Kilo client if `research-llm.sh` isn't present

## Autonomous Deployment Options

| Option | How | Best for |
|--------|-----|----------|
| **Manual** (default) | Run during work sessions | Starting out (L0-1) |
| **Modal.com** | Deploy orchestrator.py as serverless cron | Hands-off (L2-3) |
| **GitHub Actions** | Trigger on schedule via workflow | Free tier, no infra |

See `references/autoresearch-protocol.md` for Modal deployment guide.

## Attribution

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) — AI agents running autonomous experiments overnight. Same generate → evaluate → retain/discard loop, adapted from LLM training optimization to marketing skill optimization.

# Autoresearch Protocol

Reference document for the autonomous skill optimization loop.

---

## 1. The Karpathy Pattern

Attribution: inspired by Andrej Karpathy's autoresearch concept — AI agents running autonomous experiments to improve their own outputs.

The core insight is simple. LLM training already uses a generate-evaluate-retain/discard loop to optimize model weights. Autoresearch applies the same loop one level up: instead of optimizing weights, it optimizes the marketing skills and artifacts that agents produce.

The cycle:
1. Generate candidate outputs using a cheap model
2. Evaluate them against a rubric using a smarter model
3. Retain winners, discard losers
4. Mutate the skill/template/prompt based on what won
5. Repeat

Over iterations, skills drift toward higher-scoring outputs without human intervention. Humans set the rubric (what "good" means), the machine finds the path.

---

## 2. Loop Mechanics Deep Dive

### Step 1: Load Client Context

Files loaded before generation:
**AgentKits mode** (`clients/<project>/`):
- `icp.md` — shapes audience targeting and language
- `offer.md` — shapes value prop and positioning
- `brand-voice.md` — shapes tone and style

**Standalone mode** (`projects/<project>/`):
- `context.md` — or any `.md` files in the project directory

Plus the skill file itself (e.g., `skills/copywriting/SKILL.md`) — shapes the framework being optimized

These files are concatenated into the system prompt for the generation model. They are NOT modified by the loop — only the skill output is optimized.

### Step 2: Backup

Before any mutation, snapshot the current skill state.

Naming convention: `backups/YYMMDD-HHmmss/`

Example:
```
backups/
  260314-143022/
    SKILL.md
    references/
    templates/
```

One snapshot per run. If a mutation makes things worse, restore from the most recent backup.

### Step 3: Generate

- Model: Kilo Gateway via `scripts/research-llm.sh kilo`
- Temperature: 0.8 (high enough for variety, low enough for coherence)
- Outputs per scenario: 3
- Each scenario = one prompt constructed from client context + skill framework + a specific task (e.g., "write a cold email subject line for this ICP")

The generation prompt includes:
- Full client context (from Step 1)
- The specific task/scenario
- Instruction to produce the artifact type the skill creates

Output is raw text, stored temporarily for evaluation.

### Step 4: Evaluate

- Model: Claude Sonnet (smarter model for judgment)
- Input: each generated output + the rubric
- Rubric: binary criteria (pass/fail per criterion)
- Score = number of criteria passed / total criteria
- Threshold: configurable, default 0.7 (70% of criteria must pass)

Example evaluation prompt:
```
Evaluate this output against each criterion. Answer PASS or FAIL for each.

Output: [generated text]

Criteria:
1. Contains a specific number or statistic — PASS/FAIL
2. Addresses the ICP's primary pain point — PASS/FAIL
3. Matches the brand voice tone — PASS/FAIL
...
```

Outputs scoring above threshold are "winners." Below threshold are discarded.

### Step 5: Save Winners

Winners are saved to the experiment directory:

```
experiments/<skill-name>/
  <run-id>/
    winners/
      scenario-1-output-2.md
      scenario-3-output-1.md
    all-scores.yaml
```

File naming: `scenario-<N>-output-<M>.md` where N is the scenario index and M is the output index within that scenario.

### Step 6: Mutate

The minimum-change principle: change as little as possible per iteration. One tweak at a time so you can attribute improvement.

What gets sent to Claude for mutation:
- The current skill file (template, framework, or prompt)
- The winning outputs (what worked)
- The losing outputs (what didn't)
- The rubric scores for both

Claude is asked: "What single change to the skill/template would make the losing outputs look more like the winning outputs?"

The mutation is applied to a copy, not the original (original is backed up in Step 2).

### Step 7: Compare

After mutation, run the generation-evaluation loop again with the mutated skill.

- Compare average scores: mutated vs. original
- If mutated scores higher → keep the mutation
- If mutated scores equal or lower → discard the mutation, restore from backup
- Minimum improvement threshold: +0.05 (5 percentage points) to avoid noise

### Step 8: Log

Every run is logged to `experiment-log.yaml`:

```yaml
- run_id: "260314-143022"
  skill: "copywriting"
  project: "myproject"
  scenarios: 4
  outputs_per_scenario: 3
  total_generated: 12
  winners: 5
  avg_score_before: 0.62
  avg_score_after: 0.71
  mutation_applied: true
  mutation_description: "Added specificity requirement to headline template"
  cost_usd: 0.47
  duration_seconds: 180
  timestamp: "2026-03-14T14:30:22Z"
```

---

## 3. Rubric Design Tips

### Be Specific and Observable

Bad: "Is the copy good?"
Good: "Does the copy include a specific number or statistic?"

Bad: "Is the tone right?"
Good: "Does the copy avoid exclamation marks in the first two sentences?"

Bad: "Is it persuasive?"
Good: "Does the copy name a specific pain point the ICP experiences?"

### Mix Categories

A balanced rubric covers multiple dimensions:

| Category | Example Criterion |
|----------|-------------------|
| Relevance | Mentions the ICP's industry or role |
| Voice | Uses first-person perspective consistent with brand voice |
| Conversion | Includes a clear call-to-action |
| Quality | No filler phrases ("in today's world", "it's no secret") |
| Specificity | Names a concrete outcome or metric |

### Starting Point

Start with 5-8 criteria. Fewer than 5 gives scores too coarse (each criterion is worth 12-20%). More than 8 in early runs adds evaluation cost without enough data to know which criteria matter.

After 5+ runs, review criterion pass rates and evolve:
- Criteria passing >95% of the time are too easy — prune them or make them harder
- Criteria passing <10% of the time are too hard — either the generation model can't satisfy them, or they're misaligned with the task. Recalibrate or remove
- Add new criteria when you notice failure modes the rubric doesn't catch

### Anti-Patterns

- Subjective criteria without anchors ("feels authentic") — impossible to evaluate consistently
- Double-barreled criteria ("mentions a pain point AND includes a statistic") — split into two
- Criteria that conflict with each other ("be concise" + "include detailed examples") — pick one per iteration

---

## 4. Cost Optimization

### Per-Step Costs

| Step | Model | Approximate Cost |
|------|-------|-----------------|
| Generation (3 outputs x 4 scenarios) | Kilo Gateway (MiniMax M2.5) | ~$0.01-0.03 |
| Evaluation (12 outputs x rubric) | Claude Sonnet | ~$0.10-0.20 |
| Mutation (1 diff request) | Claude Sonnet | ~$0.02-0.05 |
| Comparison (12 more outputs + eval) | Kilo + Sonnet | ~$0.12-0.23 |

### Total Per Run

A single 3-iteration run (generate, evaluate, mutate, re-generate, re-evaluate, decide — repeated 3 times): **~$0.50-1.00**

### Tips to Keep Costs Down

1. **Fewer scenarios in early runs.** Start with 2 scenarios, increase to 4-6 after you've confirmed the rubric works.
2. **Reduce outputs per scenario.** 3 is the default; drop to 2 for expensive skills.
3. **Batch evaluations.** Send all outputs to Sonnet in one prompt instead of one-at-a-time.
4. **Cap iterations.** Default is 3 iterations per run. Diminishing returns beyond 5.
5. **Schedule off-peak.** Modal and API costs can vary; run during low-demand hours.
6. **Use spend-log.yaml.** Track cumulative spend per skill per month. Set caps in schedule-config.yaml.

---

## 5. Modal Deployment Guide

### Setup

```bash
pip install modal
modal setup  # authenticate with Modal.com
```

### Secrets

Set these in the Modal dashboard under Secrets:

- `KILO_API_KEY` — for generation via Kilo Gateway
- `ANTHROPIC_API_KEY` — for evaluation and mutation via Claude

### Example Modal App Skeleton

```python
import modal
import subprocess
import os

app = modal.App("autoresearch")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("anthropic", "pyyaml", "requests")
    .copy_local_dir(".", "/app")
)

@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("kilo-api-key"),
        modal.Secret.from_name("anthropic-api-key"),
    ],
    schedule=modal.Cron("0 6 * * *"),  # daily at 6am UTC
    timeout=600,
)
def run_autoresearch():
    os.chdir("/app")
    result = subprocess.run(
        ["python", "orchestrator.py", "--skill", "copywriting", "--project", "myproject"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        raise Exception(f"Autoresearch failed: {result.stderr}")
    return result.stdout
```

### Deploy

```bash
modal deploy autoresearch_modal.py
```

### Results Back to Git

Option A: Modal function pushes results to a branch via GitHub API.

Option B: Use a GitHub Action triggered by Modal webhook to pull results and commit.

Option C: Modal writes results to a shared volume; a separate sync job commits them.

---

## 6. GitHub Actions Alternative

For teams that prefer GitHub-native CI:

```yaml
name: Autoresearch Loop

on:
  schedule:
    - cron: '0 6 * * 1'  # Weekly on Monday at 6am UTC
  workflow_dispatch:       # Manual trigger

permissions:
  contents: write

jobs:
  autoresearch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install anthropic pyyaml requests

      - name: Run autoresearch
        env:
          KILO_API_KEY: ${{ secrets.KILO_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python orchestrator.py --skill copywriting --project myproject

      - name: Commit results
        run: |
          git config user.name "autoresearch[bot]"
          git config user.email "autoresearch@bot.local"
          git add experiments/ experiment-log.yaml skills/
          git diff --staged --quiet || git commit -m "autoresearch: $(date +%Y-%m-%d) run"
          git push
```

Adjust the `--skill` and `--project` flags per your needs. For multi-skill runs, loop through a list or use a matrix strategy.

---

## 7. Troubleshooting

### "Empty rubric"

The rubric file doesn't exist or has no criteria. Run the bootstrap step first to generate an initial rubric from the skill's SKILL.md and example outputs.

### "All outputs failing"

Rubric criteria are too strict for the generation model's capability at the given temperature.

Fixes:
- Lower the pass threshold from 0.7 to 0.5
- Remove the hardest criterion (lowest pass rate)
- Increase temperature to 0.9 for more variety
- Check if the criterion is actually impossible given the prompt (e.g., "includes a customer quote" when no quotes are in the context)

### "No improvement after 3 iterations"

The rubric may not capture what actually matters about quality. The model optimizes for what the rubric measures — if the rubric misses the point, optimization goes sideways.

Fixes:
- Review winning vs. losing outputs manually — what makes winners better?
- Add criteria that capture that difference
- Remove criteria that don't differentiate (pass rate near 50% but no correlation with quality)
- Try a different mutation strategy: instead of "make losers more like winners," try "what's the biggest weakness in the losing outputs?"

### "Budget exceeded"

Check `spend-log.yaml` for cumulative costs. Common causes:
- Too many scenarios per run
- Too many iterations per run
- Runs scheduled too frequently
- Evaluation prompts too long (trim context)

Fix: adjust caps in `schedule-config.yaml`, reduce scenarios or iterations.

### "Kill file active"

Someone ran `/autoresearch:stop`, which creates a `.kill` file in the skill's autoresearch directory. The orchestrator checks for this file before each iteration and exits gracefully if found.

To resume: delete the `.kill` file manually or run `/autoresearch:start`.

```bash
rm skills/<skill-name>/autoresearch/.kill
```

#!/usr/bin/env python3
"""Autoresearch orchestrator — core optimization loop.

Runs generate -> evaluate -> mutate -> keep/discard iterations on a skill,
using a client's context as the evaluation lens.

Usage:
  orchestrator.py <skill> --client <project> [--iterations N] [--dry-run] [--json]
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add scripts dir to path for paths module
sys.path.insert(0, str(Path(__file__).parent))
import paths as P

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def load_yaml_file(path):
    """Load a YAML file, return None if missing."""
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml_file(path, data):
    """Save data as YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def backup_skill(skill_path, rollback_dir):
    """Backup current SKILL.md to rollback directory."""
    ts = datetime.now().strftime("%y%m%d-%H%M%S")
    backup_name = f"{ts}-SKILL.md.bak"
    backup_path = rollback_dir / backup_name
    backup_path.write_text(skill_path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


def restore_skill(skill_path, rollback_dir):
    """Restore most recent backup."""
    backups = sorted(rollback_dir.glob("*-SKILL.md.bak"), reverse=True)
    if not backups:
        print("ERROR: No rollback backup found!", file=sys.stderr)
        return False
    latest = backups[0]
    skill_path.write_text(latest.read_text(encoding="utf-8"), encoding="utf-8")
    return True


def call_kilo(project_root, prompt, system_prompt=None):
    """Call LLM for generation — tries research-llm.sh first, falls back to built-in Kilo client."""
    return P.call_llm(prompt, system_prompt=system_prompt, project_root=project_root)


def generate_outputs(project_root, skill_content, scenario, num_outputs=3, dry_run=False):
    """Generate N outputs for a scenario using Kilo Gateway."""
    outputs = []
    for i in range(num_outputs):
        prompt = (
            f"You are executing a skill. Follow the skill instructions precisely.\n\n"
            f"SCENARIO:\n{scenario['brief']}\n\n"
            f"Expected format: {scenario.get('expected_format', 'content')}\n"
            f"Word count range: {scenario.get('word_count_range', [300, 800])}\n\n"
            f"Generate output #{i+1}. Be creative and vary your approach."
        )
        if dry_run:
            outputs.append(f"[DRY RUN] Output #{i+1} for scenario '{scenario['name']}'")
        else:
            result = call_kilo(project_root, prompt, system_prompt=skill_content)
            outputs.append(result if result else f"[GENERATION FAILED] Output #{i+1}")
    return outputs


def print_evaluation_prompt(scenario, outputs, rubric_criteria):
    """Print structured prompt for Claude to evaluate outputs."""
    print("\n" + "=" * 70)
    print("EVALUATION NEEDED — Score each output against the rubric")
    print("=" * 70)
    print(f"\nScenario: {scenario['name']}")
    print(f"Brief: {scenario['brief']}")
    print("\n--- RUBRIC CRITERIA (answer YES or NO for each) ---")
    for i, criterion in enumerate(rubric_criteria, 1):
        print(f"  {i}. {criterion['question']}")

    for i, output in enumerate(outputs, 1):
        print(f"\n--- OUTPUT #{i} ---")
        print(output[:2000] if len(output) > 2000 else output)
        print(f"--- END OUTPUT #{i} ---")

    print("\nFor each output, provide scores as a comma-separated list of Y/N.")
    print("Example: Output #1: Y,Y,N,Y,Y  Output #2: N,Y,Y,Y,N  Output #3: Y,Y,Y,Y,Y")
    print("=" * 70)


def print_mutation_prompt(skill_path, failing_criteria, failing_outputs):
    """Print structured prompt for Claude to suggest SKILL.md mutations."""
    print("\n" + "=" * 70)
    print("MUTATION NEEDED — Suggest SKILL.md changes to fix failures")
    print("=" * 70)
    print(f"\nSkill file: {skill_path}")
    print("\n--- FAILING CRITERIA (outputs failed these) ---")
    for criterion in failing_criteria:
        print(f"  - {criterion}")
    print("\n--- SAMPLE FAILING OUTPUTS ---")
    for i, output in enumerate(failing_outputs[:2], 1):
        snippet = output[:1000] if len(output) > 1000 else output
        print(f"\n  Failing output #{i}:\n{snippet}")
    print("\nModify SKILL.md to fix these failures. Minimum changes only.")
    print("Provide the exact text changes needed (old -> new).")
    print("=" * 70)


def save_winner(output, scenario, winners_dir, output_idx):
    """Save a winning output to the winners directory."""
    ts = datetime.now().strftime("%y%m%d-%H%M%S")
    scenario_slug = scenario.get("id", "s0")
    fname = f"{ts}-{scenario_slug}-{output_idx}.md"
    fpath = winners_dir / fname
    fpath.write_text(output, encoding="utf-8")
    return fpath


def load_experiment_log(experiment_dir):
    """Load or initialize experiment log."""
    log_path = experiment_dir / "experiment-log.yaml"
    data = load_yaml_file(log_path)
    return data if data else []


def save_experiment_log(experiment_dir, log_data):
    """Save experiment log."""
    save_yaml_file(experiment_dir / "experiment-log.yaml", log_data)


def print_summary(log_data, json_output=False):
    """Print experiment summary."""
    if json_output:
        print(json.dumps(log_data, indent=2, default=str))
        return

    print("\n" + "=" * 70)
    print("EXPERIMENT SUMMARY")
    print("=" * 70)
    for entry in log_data:
        kept = "KEPT" if entry.get("kept") else "DISCARDED"
        print(
            f"  Iteration {entry['iteration']}: "
            f"baseline={entry.get('baseline_score', '?')} "
            f"mutated={entry.get('mutated_score', '?')} "
            f"→ {kept} "
            f"(winners: {entry.get('winners_count', 0)})"
        )
    total_kept = sum(1 for e in log_data if e.get("kept"))
    print(f"\nTotal iterations: {len(log_data)} | Kept: {total_kept} | Discarded: {len(log_data) - total_kept}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Autoresearch orchestrator — skill optimization loop")
    parser.add_argument("skill", help="Skill name to optimize")
    parser.add_argument("--client", required=True, help="Client/project name")
    parser.add_argument("--iterations", type=int, default=3, help="Number of optimization iterations (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without API calls")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--threshold", type=int, default=None, help="Minimum score to be a winner (default: 60%% of criteria)")
    args = parser.parse_args()

    # Find project root
    project_root = P.find_project_root()
    if not project_root:
        print("ERROR: Could not find project root (no CLAUDE.md or skills/ found)", file=sys.stderr)
        sys.exit(1)

    # Find skill
    skill_path = P.find_skill_path(args.skill, project_root)
    if not skill_path:
        print(f"ERROR: SKILL.md not found for '{args.skill}'", file=sys.stderr)
        sys.exit(1)

    skill_content = skill_path.read_text(encoding="utf-8")

    # Resolve project (auto-detect AgentKits vs standalone)
    project_dir, mode = P.require_project(project_root, args.client)
    client_context = P.load_context(project_dir, mode)

    # Setup experiment directories
    experiment_dir = P.experiment_dir(project_dir, args.skill)

    # Load rubric and scenarios
    rubric = load_yaml_file(experiment_dir / "rubric.yaml")
    if not rubric or "criteria" not in rubric:
        print(f"ERROR: rubric.yaml not found or invalid at {experiment_dir / 'rubric.yaml'}", file=sys.stderr)
        print("Run rubric_bootstrap.py first to generate evaluation criteria.", file=sys.stderr)
        sys.exit(1)

    scenarios = load_yaml_file(experiment_dir / "scenarios.yaml")
    if not scenarios or "scenarios" not in scenarios:
        print(f"ERROR: scenarios.yaml not found or invalid at {experiment_dir / 'scenarios.yaml'}", file=sys.stderr)
        print("Run scenario_generator.py first to generate test scenarios.", file=sys.stderr)
        sys.exit(1)

    criteria = rubric["criteria"]
    threshold = args.threshold if args.threshold else max(1, int(len(criteria) * 0.6))

    # Load existing experiment log
    experiment_log = load_experiment_log(experiment_dir)

    if not args.json:
        print(f"Autoresearch Orchestrator")
        print(f"  Skill: {args.skill} ({skill_path})")
        print(f"  Client: {args.client}")
        print(f"  Iterations: {args.iterations}")
        print(f"  Criteria: {len(criteria)} (threshold: {threshold}/{len(criteria)})")
        print(f"  Scenarios: {len(scenarios['scenarios'])}")
        print(f"  Experiment dir: {experiment_dir}")
        if args.dry_run:
            print("  Mode: DRY RUN")
        print()

    # Run iterations
    for iteration in range(1, args.iterations + 1):
        if not args.json:
            print(f"\n{'#' * 50}")
            print(f"# ITERATION {iteration}/{args.iterations}")
            print(f"{'#' * 50}")

        # Step 1: Backup current SKILL.md
        backup_path = backup_skill(skill_path, experiment_dir / "rollback")
        if not args.json:
            print(f"\n[Backup] Saved to {backup_path.name}")

        # Step 2: Generate outputs for each scenario
        all_outputs = {}
        for scenario in scenarios["scenarios"]:
            if not args.json:
                print(f"\n[Generate] Scenario: {scenario['name']}")
            outputs = generate_outputs(
                project_root, skill_content, scenario,
                num_outputs=3, dry_run=args.dry_run
            )
            all_outputs[scenario["id"]] = {
                "scenario": scenario,
                "outputs": outputs,
            }

        # Step 3: Evaluation prompt (for Claude to score)
        if not args.dry_run:
            for sid, data in all_outputs.items():
                print_evaluation_prompt(data["scenario"], data["outputs"], criteria)

            print("\n[Waiting] Provide scores above, then re-run with updated experiment-log.yaml")
            print("Or use --dry-run to skip evaluation.")

        # Step 4: In dry-run mode, simulate scores
        if args.dry_run:
            entry = {
                "iteration": iteration,
                "timestamp": datetime.now().isoformat(),
                "baseline_score": f"{threshold}/{len(criteria)} (simulated)",
                "mutated_score": f"{threshold}/{len(criteria)} (simulated)",
                "kept": True,
                "mutation_summary": "[DRY RUN] No mutation applied",
                "winners_count": len(scenarios["scenarios"]),
                "scenarios_tested": [s["id"] for s in scenarios["scenarios"]],
            }
            experiment_log.append(entry)

            # Save dummy winners
            for sid, data in all_outputs.items():
                for i, output in enumerate(data["outputs"], 1):
                    save_winner(output, data["scenario"], experiment_dir / "winners", i)

            if not args.json:
                print(f"\n[Dry Run] Iteration {iteration} simulated — all outputs saved as winners")

        # Reload skill content for next iteration (in case it was mutated)
        if skill_path.exists():
            skill_content = skill_path.read_text(encoding="utf-8")

    # Save experiment log
    save_experiment_log(experiment_dir, experiment_log)

    # Print summary
    print_summary(experiment_log, json_output=args.json)


if __name__ == "__main__":
    main()

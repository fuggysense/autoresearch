#!/usr/bin/env python3
"""Feedback loop for autoresearch — campaign outcome recording and rubric calibration.

Records which winners were used in campaigns, tracks real-world outcomes,
and calibrates rubric criteria against actual performance.

Usage:
  feedback_loop.py record --client <project> --skill <name> --campaign <campaign> --outcome <json>
  feedback_loop.py calibrate --client <project> --skill <name>
  feedback_loop.py accuracy --client <project> --skill <name>
  feedback_loop.py --json
"""

import argparse
import json
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


def get_outcomes_path(project_dir):
    """Get path to campaign outcomes file."""
    return P.autoresearch_dir(project_dir) / "feedback" / "campaign-outcomes.yaml"


def load_outcomes(project_dir):
    """Load campaign outcomes."""
    path = get_outcomes_path(project_dir)
    data = load_yaml_file(path)
    if data and "outcomes" in data:
        return data
    return {"outcomes": []}


def save_outcomes(project_dir, data):
    """Save campaign outcomes."""
    path = get_outcomes_path(project_dir)
    save_yaml_file(path, data)


def do_record(project_dir, skill_name, campaign, outcome_json, json_output=False):
    """Record a campaign outcome linked to autoresearch winners."""
    try:
        outcome = json.loads(outcome_json)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON for --outcome: {e}", file=sys.stderr)
        sys.exit(1)

    data = load_outcomes(project_dir)

    entry = {
        "skill": skill_name,
        "campaign": campaign,
        "timestamp": datetime.now().isoformat(),
        "outcome": outcome,
        "synthetic_score": outcome.get("synthetic_score", None),
        "real_performance": outcome.get("real_performance", None),
    }
    data["outcomes"].append(entry)
    save_outcomes(project_dir, data)

    if json_output:
        print(json.dumps({"recorded": entry}, indent=2, default=str))
    else:
        print(f"Recorded outcome for {skill_name} in campaign '{campaign}'")
        print(f"  Synthetic score: {entry.get('synthetic_score', 'not provided')}")
        print(f"  Real performance: {entry.get('real_performance', 'not provided')}")
        print(f"  Full outcome saved to: {get_outcomes_path(project_dir)}")


def do_accuracy(project_dir, skill_name, json_output=False):
    """Calculate accuracy gap between synthetic scores and real performance."""
    data = load_outcomes(project_dir)

    # Filter to this skill
    skill_outcomes = [o for o in data["outcomes"] if o.get("skill") == skill_name]

    if not skill_outcomes:
        if json_output:
            print(json.dumps({"skill": skill_name, "entries": 0, "message": "No outcomes recorded"}))
        else:
            print(f"No outcomes recorded for skill '{skill_name}'")
        return

    # Find entries with both synthetic and real scores
    paired = []
    for o in skill_outcomes:
        synthetic = o.get("synthetic_score")
        real = o.get("real_performance")
        if synthetic is not None and real is not None:
            try:
                paired.append({
                    "campaign": o.get("campaign"),
                    "synthetic": float(synthetic),
                    "real": float(real),
                    "gap": abs(float(synthetic) - float(real)),
                    "direction": "over" if float(synthetic) > float(real) else "under",
                })
            except (ValueError, TypeError):
                continue

    if not paired:
        if json_output:
            print(json.dumps({
                "skill": skill_name,
                "total_outcomes": len(skill_outcomes),
                "paired": 0,
                "message": "No paired synthetic+real scores found",
            }))
        else:
            print(f"Accuracy — {skill_name}")
            print(f"  Total outcomes: {len(skill_outcomes)}")
            print(f"  Paired scores: 0 (need both synthetic_score and real_performance)")
        return

    avg_gap = sum(p["gap"] for p in paired) / len(paired)
    over_count = sum(1 for p in paired if p["direction"] == "over")
    under_count = sum(1 for p in paired if p["direction"] == "under")

    result = {
        "skill": skill_name,
        "total_outcomes": len(skill_outcomes),
        "paired": len(paired),
        "avg_accuracy_gap": round(avg_gap, 3),
        "over_predicted": over_count,
        "under_predicted": under_count,
        "details": paired,
    }

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Accuracy — {skill_name}")
        print(f"  Total outcomes: {len(skill_outcomes)}")
        print(f"  Paired scores: {len(paired)}")
        print(f"  Avg accuracy gap: {avg_gap:.3f}")
        print(f"  Over-predicted: {over_count} | Under-predicted: {under_count}")
        print()
        for p in paired:
            print(f"  Campaign '{p['campaign']}': synthetic={p['synthetic']:.2f} real={p['real']:.2f} gap={p['gap']:.2f} ({p['direction']})")


def do_calibrate(project_dir, skill_name, json_output=False):
    """Analyze outcomes to suggest rubric calibration changes."""
    data = load_outcomes(project_dir)

    skill_outcomes = [o for o in data["outcomes"] if o.get("skill") == skill_name]

    if len(skill_outcomes) < 3:
        if json_output:
            print(json.dumps({
                "skill": skill_name,
                "entries": len(skill_outcomes),
                "message": "Need at least 3 outcomes to calibrate. Keep recording.",
            }))
        else:
            print(f"Calibration — {skill_name}")
            print(f"  Entries: {len(skill_outcomes)}")
            print(f"  Need at least 3 outcomes to calibrate. Keep recording.")
        return

    # Analyze patterns
    false_positives = []  # High synthetic, low real
    false_negatives = []  # Low synthetic, high real

    for o in skill_outcomes:
        synthetic = o.get("synthetic_score")
        real = o.get("real_performance")
        if synthetic is None or real is None:
            continue
        try:
            s, r = float(synthetic), float(real)
            if s >= 0.7 and r < 0.4:
                false_positives.append(o)
            elif s < 0.4 and r >= 0.7:
                false_negatives.append(o)
        except (ValueError, TypeError):
            continue

    suggestions = []
    if false_positives:
        suggestions.append({
            "issue": "Rubric too lenient",
            "evidence": f"{len(false_positives)} outputs scored high but performed poorly",
            "action": "Review and tighten criteria that these outputs passed",
            "campaigns": [o.get("campaign") for o in false_positives],
        })

    if false_negatives:
        suggestions.append({
            "issue": "Rubric too strict",
            "evidence": f"{len(false_negatives)} outputs scored low but performed well",
            "action": "Review and relax criteria that blocked these outputs",
            "campaigns": [o.get("campaign") for o in false_negatives],
        })

    if not suggestions:
        suggestions.append({
            "issue": "None detected",
            "evidence": "Synthetic scores align reasonably with real performance",
            "action": "No calibration needed at this time",
        })

    # Load current rubric for reference
    rubric_path = (
        P.autoresearch_dir(project_dir)
        / "experiments" / skill_name / "rubric.yaml"
    )
    rubric = load_yaml_file(rubric_path)
    criteria_count = len(rubric.get("criteria", [])) if rubric else 0

    result = {
        "skill": skill_name,
        "outcomes_analyzed": len(skill_outcomes),
        "false_positives": len(false_positives),
        "false_negatives": len(false_negatives),
        "current_criteria_count": criteria_count,
        "suggestions": suggestions,
    }

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"Calibration Report — {skill_name}")
        print(f"  Outcomes analyzed: {len(skill_outcomes)}")
        print(f"  Current rubric criteria: {criteria_count}")
        print(f"  False positives (too lenient): {len(false_positives)}")
        print(f"  False negatives (too strict): {len(false_negatives)}")
        print()
        for s in suggestions:
            print(f"  [{s['issue']}]")
            print(f"    Evidence: {s['evidence']}")
            print(f"    Action: {s['action']}")
            if "campaigns" in s:
                print(f"    Campaigns: {', '.join(s['campaigns'])}")
            print()


def main():
    parser = argparse.ArgumentParser(description="Autoresearch feedback loop")
    parser.add_argument("command", nargs="?",
                        choices=["record", "calibrate", "accuracy"],
                        default="accuracy", help="Command to run")
    parser.add_argument("--client", required=True, help="Client/project name")
    parser.add_argument("--skill", help="Skill name")
    parser.add_argument("--campaign", help="Campaign name/ID")
    parser.add_argument("--outcome", help="Outcome data as JSON string")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    project_root = P.find_project_root()
    if not project_root:
        print("ERROR: Could not find project root (no CLAUDE.md or skills/ found)", file=sys.stderr)
        sys.exit(1)

    project_dir, mode = P.require_project(project_root, args.client)

    if args.command == "record":
        if not args.skill:
            print("ERROR: --skill is required for record", file=sys.stderr)
            sys.exit(1)
        if not args.campaign:
            print("ERROR: --campaign is required for record", file=sys.stderr)
            sys.exit(1)
        if not args.outcome:
            print("ERROR: --outcome is required for record (JSON string)", file=sys.stderr)
            sys.exit(1)
        do_record(project_dir, args.skill, args.campaign, args.outcome, args.json)

    elif args.command == "calibrate":
        if not args.skill:
            print("ERROR: --skill is required for calibrate", file=sys.stderr)
            sys.exit(1)
        do_calibrate(project_dir, args.skill, args.json)

    elif args.command == "accuracy":
        if not args.skill:
            print("ERROR: --skill is required for accuracy", file=sys.stderr)
            sys.exit(1)
        do_accuracy(project_dir, args.skill, args.json)


if __name__ == "__main__":
    main()

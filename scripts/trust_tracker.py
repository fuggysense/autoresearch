#!/usr/bin/env python3
"""Trust tracker for autoresearch — HITL graduation logic.

Tracks skill trust levels and manages graduation/demotion based on
experiment success/rollback history.

Levels: L0 (Untested) -> L1 (Supervised) -> L2 (Semi-auto) -> L3 (Auto)

Usage:
  trust_tracker.py status --client <project> [--skill <name>]
  trust_tracker.py record --client <project> --skill <name> --result <success|rollback>
  trust_tracker.py check --client <project> --skill <name>
  trust_tracker.py --json
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add scripts dir to path for paths module
sys.path.insert(0, str(Path(__file__).parent))
import paths as P

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


# Graduation thresholds
GRAD_L0_TO_L1 = 3    # consecutive successes
GRAD_L1_TO_L2 = 5    # total at L1 + accuracy < 0.2
GRAD_L2_TO_L3 = 10   # total at L2 + 0 rollbacks in last 20

# Demotion rules
DEMOTE_SINGLE_ROLLBACK = 1   # drop 1 level
DEMOTE_TWO_IN_30_DAYS = 0    # drop to L0




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


def get_registry_path(project_dir):
    """Get path to trust registry."""
    return P.autoresearch_dir(project_dir) / "trust-registry.yaml"


def load_registry(project_dir):
    """Load trust registry."""
    path = get_registry_path(project_dir)
    data = load_yaml_file(path)
    if data and "skills" in data:
        return data
    return {"skills": {}}


def save_registry(project_dir, registry):
    """Save trust registry."""
    path = get_registry_path(project_dir)
    save_yaml_file(path, registry)


def get_skill_entry(registry, skill_name):
    """Get or create a skill entry in the registry."""
    if skill_name not in registry["skills"]:
        registry["skills"][skill_name] = {
            "level": 0,
            "level_name": "L0 (Untested)",
            "history": [],
            "consecutive_successes": 0,
            "total_at_level": 0,
            "last_updated": datetime.now().isoformat(),
        }
    return registry["skills"][skill_name]


def level_name(level):
    """Convert level number to display name."""
    names = {
        0: "L0 (Untested)",
        1: "L1 (Supervised)",
        2: "L2 (Semi-auto)",
        3: "L3 (Auto)",
    }
    return names.get(level, f"L{level} (Unknown)")


def record_result(entry, result):
    """Record a success or rollback result."""
    entry["history"].append({
        "result": result,
        "timestamp": datetime.now().isoformat(),
        "level_at_time": entry["level"],
    })

    if result == "success":
        entry["consecutive_successes"] = entry.get("consecutive_successes", 0) + 1
        entry["total_at_level"] = entry.get("total_at_level", 0) + 1
    elif result == "rollback":
        entry["consecutive_successes"] = 0

    entry["last_updated"] = datetime.now().isoformat()


def count_rollbacks_in_days(entry, days=30):
    """Count rollbacks within the last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    count = 0
    for h in entry.get("history", []):
        if h.get("result") == "rollback":
            try:
                ts = datetime.fromisoformat(h["timestamp"])
                if ts >= cutoff:
                    count += 1
            except (ValueError, KeyError):
                continue
    return count


def count_rollbacks_in_last_n(entry, n=20):
    """Count rollbacks in the last N entries."""
    recent = entry.get("history", [])[-n:]
    return sum(1 for h in recent if h.get("result") == "rollback")


def check_graduation(entry):
    """Check if skill should graduate or be demoted. Returns (action, new_level, reason)."""
    level = entry.get("level", 0)
    consecutive = entry.get("consecutive_successes", 0)
    total_at_level = entry.get("total_at_level", 0)
    history = entry.get("history", [])

    # Check demotion first
    rollbacks_30d = count_rollbacks_in_days(entry, 30)

    if rollbacks_30d >= 2:
        return ("demote", 0, f"2+ rollbacks in 30 days ({rollbacks_30d} found) -> L0")

    # Check if last result was a rollback -> drop 1 level
    if history and history[-1].get("result") == "rollback" and level > 0:
        new_level = max(0, level - 1)
        return ("demote", new_level, f"Rollback detected -> drop to {level_name(new_level)}")

    # Check graduation
    if level == 0 and consecutive >= GRAD_L0_TO_L1:
        return ("graduate", 1, f"{consecutive} consecutive successes -> L1 (Supervised)")

    if level == 1 and total_at_level >= GRAD_L1_TO_L2:
        rollback_rate = count_rollbacks_in_last_n(entry, total_at_level) / max(total_at_level, 1)
        if rollback_rate < 0.2:
            return ("graduate", 2, f"{total_at_level} runs at L1 with {rollback_rate:.1%} rollback rate -> L2 (Semi-auto)")

    if level == 2 and total_at_level >= GRAD_L2_TO_L3:
        recent_rollbacks = count_rollbacks_in_last_n(entry, 20)
        if recent_rollbacks == 0:
            return ("graduate", 3, f"{total_at_level} runs at L2, 0 rollbacks in last 20 -> L3 (Auto)")

    return ("none", level, "No change")


def apply_level_change(entry, new_level):
    """Apply a level change and reset counters."""
    entry["level"] = new_level
    entry["level_name"] = level_name(new_level)
    entry["total_at_level"] = 0
    if new_level < entry.get("level", 0):
        entry["consecutive_successes"] = 0
    entry["last_updated"] = datetime.now().isoformat()


def do_status(project_dir, client, skill_filter=None, json_output=False):
    """Show trust levels for all or specific skills."""
    registry = load_registry(project_dir)
    skills = registry.get("skills", {})

    if skill_filter:
        skills = {k: v for k, v in skills.items() if k == skill_filter}

    if json_output:
        print(json.dumps(skills, indent=2, default=str))
        return

    if not skills:
        print("No skills tracked yet." if not skill_filter else f"Skill '{skill_filter}' not tracked yet.")
        return

    print(f"Trust Status — client: {client}")
    print(f"{'Skill':<30} {'Level':<20} {'Consec.':<10} {'At Level':<10} {'Last Updated'}")
    print("-" * 90)
    for name, entry in sorted(skills.items()):
        print(
            f"{name:<30} {entry.get('level_name', 'L0'):<20} "
            f"{entry.get('consecutive_successes', 0):<10} "
            f"{entry.get('total_at_level', 0):<10} "
            f"{entry.get('last_updated', 'never')[:10]}"
        )


def do_record(project_dir, skill_name, result, json_output=False):
    """Record a result and check for level changes."""
    registry = load_registry(project_dir)
    entry = get_skill_entry(registry, skill_name)

    record_result(entry, result)

    # Check graduation/demotion
    action, new_level, reason = check_graduation(entry)
    level_changed = False
    if action in ("graduate", "demote") and new_level != entry["level"]:
        old_level = entry["level"]
        apply_level_change(entry, new_level)
        level_changed = True

    save_registry(project_dir, registry)

    if json_output:
        print(json.dumps({
            "skill": skill_name,
            "result": result,
            "level": entry["level"],
            "level_name": entry["level_name"],
            "level_changed": level_changed,
            "action": action,
            "reason": reason,
        }, indent=2))
    else:
        print(f"Recorded: {skill_name} = {result}")
        if level_changed:
            print(f"  Level change: {reason}")
        else:
            print(f"  Level: {entry['level_name']} (no change)")
        print(f"  Consecutive successes: {entry['consecutive_successes']}")
        print(f"  Total at level: {entry['total_at_level']}")


def do_check(project_dir, skill_name, json_output=False):
    """Check if a skill is due for graduation or demotion."""
    registry = load_registry(project_dir)
    entry = get_skill_entry(registry, skill_name)

    action, new_level, reason = check_graduation(entry)

    if json_output:
        print(json.dumps({
            "skill": skill_name,
            "current_level": entry["level"],
            "current_level_name": entry["level_name"],
            "action": action,
            "new_level": new_level,
            "reason": reason,
            "consecutive_successes": entry.get("consecutive_successes", 0),
            "total_at_level": entry.get("total_at_level", 0),
        }, indent=2))
    else:
        print(f"Trust Check — {skill_name}")
        print(f"  Current: {entry['level_name']}")
        print(f"  Consecutive successes: {entry.get('consecutive_successes', 0)}")
        print(f"  Total at level: {entry.get('total_at_level', 0)}")
        print(f"  Action: {action}")
        print(f"  Reason: {reason}")


def main():
    parser = argparse.ArgumentParser(description="Autoresearch trust tracker")
    parser.add_argument("command", nargs="?", choices=["status", "record", "check"],
                        default="status", help="Command to run")
    parser.add_argument("--client", required=True, help="Client/project name")
    parser.add_argument("--skill", help="Skill name")
    parser.add_argument("--result", choices=["success", "rollback"], help="Result to record")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    project_root = P.find_project_root()
    if not project_root:
        print("ERROR: Could not find project root (no CLAUDE.md or skills/ found)", file=sys.stderr)
        sys.exit(1)

    project_dir, mode = P.require_project(project_root, args.client)

    if args.command == "status":
        do_status(project_dir, args.client, args.skill, args.json)

    elif args.command == "record":
        if not args.skill:
            print("ERROR: --skill is required for record", file=sys.stderr)
            sys.exit(1)
        if not args.result:
            print("ERROR: --result is required for record", file=sys.stderr)
            sys.exit(1)
        do_record(project_dir, args.skill, args.result, args.json)

    elif args.command == "check":
        if not args.skill:
            print("ERROR: --skill is required for check", file=sys.stderr)
            sys.exit(1)
        do_check(project_dir, args.skill, args.json)


if __name__ == "__main__":
    main()

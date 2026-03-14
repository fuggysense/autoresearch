#!/usr/bin/env python3
"""Priority scheduler for autoresearch — decides which skill to optimize next.

Scores skills by usage, staleness, feedback signals, and cooldown period
to produce a ranked priority queue.

Usage:
  scheduler.py next --client <project> [--count N]    # Show next N skills to optimize
  scheduler.py queue --client <project>               # Show full priority queue
  scheduler.py --json
"""

import argparse
import json
import sqlite3
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


# Priority weights
WEIGHT_USAGE = 0.40
WEIGHT_STALENESS = 0.35
WEIGHT_FEEDBACK = 0.25

DEFAULT_COOLDOWN_HOURS = 24




def load_yaml_file(path):
    """Load a YAML file, return None if missing."""
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_all_skills(project_root):
    """Get list of all skills from project and global."""
    skills = set()
    # Project skills
    project_skills = project_root / "skills"
    if project_skills.is_dir():
        for d in project_skills.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                skills.add(d.name)
    # Global skills
    global_skills = Path.home() / ".claude" / "skills"
    if global_skills.is_dir():
        for d in global_skills.iterdir():
            if d.is_dir() and (d / "SKILL.md").exists():
                skills.add(d.name)
    return sorted(skills)


def get_usage_score(skill_name):
    """Get usage count from analytics DB. Returns 0 if unavailable."""
    db_path = Path.home() / ".claude" / "analytics" / "usage.db"
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM usage WHERE skill_name = ?",
            (skill_name,)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception:
        return 0


def get_staleness_days(project_dir, skill_name):
    """Days since last experiment. Returns 999 if never run."""
    log_path = (
        P.autoresearch_dir(project_dir)
        / "experiments" / skill_name / "experiment-log.yaml"
    )
    data = load_yaml_file(log_path)
    if not data or not isinstance(data, list) or len(data) == 0:
        return 999  # Never run

    # Find most recent timestamp
    latest = None
    for entry in data:
        ts_str = entry.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if latest is None or ts > latest:
                    latest = ts
            except ValueError:
                continue

    if latest is None:
        return 999

    return (datetime.now() - latest).days


def get_feedback_count(project_dir, skill_name):
    """Count mentions of skill in dashboard.md or feedback files."""
    count = 0
    # Check dashboard.md
    dashboard = P.autoresearch_dir(project_dir) / "dashboard.md"
    if dashboard.exists():
        content = dashboard.read_text(encoding="utf-8").lower()
        count += content.count(skill_name.lower())

    # Check feedback directory
    feedback_dir = P.autoresearch_dir(project_dir) / "feedback"
    if feedback_dir.is_dir():
        for f in feedback_dir.glob("*.yaml"):
            data = load_yaml_file(f)
            if data and isinstance(data, list):
                for entry in data:
                    if entry.get("skill") == skill_name:
                        count += 1

    return count


def get_last_run_time(project_dir, skill_name):
    """Get the timestamp of the last experiment run."""
    log_path = (
        P.autoresearch_dir(project_dir)
        / "experiments" / skill_name / "experiment-log.yaml"
    )
    data = load_yaml_file(log_path)
    if not data or not isinstance(data, list):
        return None

    latest = None
    for entry in data:
        ts_str = entry.get("timestamp")
        if ts_str:
            try:
                ts = datetime.fromisoformat(ts_str)
                if latest is None or ts > latest:
                    latest = ts
            except ValueError:
                continue
    return latest


def get_cooldown_hours(project_dir):
    """Get cooldown hours from schedule-config.yaml."""
    config_path = P.autoresearch_dir(project_dir) / "schedule-config.yaml"
    config = load_yaml_file(config_path)
    if config and "cooldown_hours" in config:
        return config["cooldown_hours"]
    return DEFAULT_COOLDOWN_HOURS


def calculate_priority(usage, staleness_days, feedback_count, in_cooldown):
    """Calculate priority score. Higher = should optimize sooner."""
    # Normalize usage (log scale, max at ~100 uses)
    usage_norm = min(usage / 100.0, 1.0) if usage > 0 else 0.0

    # Normalize staleness (linear, max at 30 days)
    staleness_norm = min(staleness_days / 30.0, 1.0)

    # Normalize feedback (linear, max at 10 mentions)
    feedback_norm = min(feedback_count / 10.0, 1.0)

    score = (
        WEIGHT_USAGE * usage_norm
        + WEIGHT_STALENESS * staleness_norm
        + WEIGHT_FEEDBACK * feedback_norm
    )

    # Apply cooldown penalty
    if in_cooldown:
        score *= 0.1  # Heavy penalty

    return round(score, 4)


def main():
    parser = argparse.ArgumentParser(description="Autoresearch priority scheduler")
    parser.add_argument("command", nargs="?", choices=["next", "queue"], default="next",
                        help="Command to run")
    parser.add_argument("--client", required=True, help="Client/project name")
    parser.add_argument("--count", type=int, default=3, help="Number of skills to show (default: 3)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    project_root = P.find_project_root()
    if not project_root:
        print("ERROR: Could not find project root (no CLAUDE.md or skills/ found)", file=sys.stderr)
        sys.exit(1)

    project_dir, mode = P.require_project(project_root, args.client)

    skills = get_all_skills(project_root)
    cooldown_hours = get_cooldown_hours(project_dir)
    cooldown_cutoff = datetime.now() - timedelta(hours=cooldown_hours)

    # Score each skill
    scored = []
    for skill_name in skills:
        usage = get_usage_score(skill_name)
        staleness = get_staleness_days(project_dir, skill_name)
        feedback = get_feedback_count(project_dir, skill_name)
        last_run = get_last_run_time(project_dir, skill_name)
        in_cooldown = last_run is not None and last_run > cooldown_cutoff

        priority = calculate_priority(usage, staleness, feedback, in_cooldown)

        scored.append({
            "skill": skill_name,
            "priority": priority,
            "usage": usage,
            "staleness_days": staleness,
            "feedback_count": feedback,
            "in_cooldown": in_cooldown,
            "last_run": last_run.isoformat() if last_run else None,
        })

    # Sort by priority descending
    scored.sort(key=lambda x: x["priority"], reverse=True)

    # Apply count limit for "next" command
    if args.command == "next":
        scored = scored[:args.count]

    if args.json:
        print(json.dumps(scored, indent=2, default=str))
    else:
        title = f"Top {args.count} Skills to Optimize" if args.command == "next" else "Full Priority Queue"
        print(f"{title} — client: {args.client}")
        print(f"Cooldown: {cooldown_hours}h | Weights: usage={WEIGHT_USAGE} staleness={WEIGHT_STALENESS} feedback={WEIGHT_FEEDBACK}")
        print()

        if not scored:
            print("No skills found.")
            return

        print(f"{'#':<4} {'Skill':<30} {'Priority':<10} {'Usage':<8} {'Stale(d)':<10} {'Feedback':<10} {'Cooldown'}")
        print("-" * 90)
        for i, s in enumerate(scored, 1):
            cd = "YES" if s["in_cooldown"] else ""
            stale = "never" if s["staleness_days"] >= 999 else str(s["staleness_days"])
            print(
                f"{i:<4} {s['skill']:<30} {s['priority']:<10.4f} {s['usage']:<8} "
                f"{stale:<10} {s['feedback_count']:<10} {cd}"
            )


if __name__ == "__main__":
    main()

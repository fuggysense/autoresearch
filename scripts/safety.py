#!/usr/bin/env python3
"""Safety rails for autoresearch — budget tracking, kill switch, rollback limits.

Usage:
  safety.py check --client <project>               # Pre-run safety check
  safety.py log-spend <amount> --client <project>   # Log spend after run
  safety.py budget --client <project>               # Show budget status
  safety.py kill                                    # Create kill file
  safety.py unkill                                  # Remove kill file
  safety.py --test                                  # Run self-tests
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


KILL_FILE = Path.home() / ".claude" / "skills" / "autoresearch" / ".kill"

DEFAULT_BUDGET = {
    "per_run_max": 0.50,       # USD per single run
    "weekly_max": 5.00,        # USD per week
    "monthly_max": 15.00,      # USD per month
    "max_consecutive_rollbacks": 3,
}



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


def get_spend_log_path(project_dir):
    """Get path to spend log."""
    return P.autoresearch_dir(project_dir) / "spend-log.yaml"


def get_budget_config(project_dir):
    """Load budget config from schedule-config.yaml or use defaults."""
    config_path = P.autoresearch_dir(project_dir) / "schedule-config.yaml"
    config = load_yaml_file(config_path)
    if config and "budget" in config:
        budget = DEFAULT_BUDGET.copy()
        budget.update(config["budget"])
        return budget
    return DEFAULT_BUDGET.copy()


def load_spend_log(project_dir):
    """Load spend log entries."""
    path = get_spend_log_path(project_dir)
    data = load_yaml_file(path)
    if data and "entries" in data:
        return data["entries"]
    return []


def save_spend_entry(project_dir, amount, note=""):
    """Append a spend entry."""
    path = get_spend_log_path(project_dir)
    data = load_yaml_file(path) or {"entries": []}
    if "entries" not in data:
        data["entries"] = []

    data["entries"].append({
        "timestamp": datetime.now().isoformat(),
        "amount": float(amount),
        "note": note,
    })
    save_yaml_file(path, data)


def get_weekly_spend(entries):
    """Sum spend in the last 7 days."""
    cutoff = datetime.now() - timedelta(days=7)
    total = 0.0
    for entry in entries:
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts >= cutoff:
                total += float(entry.get("amount", 0))
        except (ValueError, KeyError):
            continue
    return total


def get_monthly_spend(entries):
    """Sum spend in the last 30 days."""
    cutoff = datetime.now() - timedelta(days=30)
    total = 0.0
    for entry in entries:
        try:
            ts = datetime.fromisoformat(entry["timestamp"])
            if ts >= cutoff:
                total += float(entry.get("amount", 0))
        except (ValueError, KeyError):
            continue
    return total


def count_consecutive_rollbacks(project_dir):
    """Count consecutive rollbacks across all skills from experiment logs."""
    autoresearch_dir = P.autoresearch_dir(project_dir) / "experiments"
    if not autoresearch_dir.exists():
        return 0

    # Collect all experiment entries with timestamps
    all_entries = []
    for skill_dir in autoresearch_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        log_path = skill_dir / "experiment-log.yaml"
        data = load_yaml_file(log_path)
        if data and isinstance(data, list):
            for entry in data:
                all_entries.append(entry)

    if not all_entries:
        return 0

    # Sort by timestamp descending
    all_entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)

    # Count consecutive non-kept entries
    count = 0
    for entry in all_entries:
        if not entry.get("kept", True):
            count += 1
        else:
            break
    return count


def check_kill_file():
    """Check if kill file exists."""
    return KILL_FILE.exists()


def do_check(project_dir, json_output=False):
    """Run all pre-run safety checks."""
    issues = []
    warnings = []

    # Check kill file
    if check_kill_file():
        issues.append("KILL FILE ACTIVE — all autoresearch runs blocked. Use 'safety.py unkill' to remove.")

    # Check budget
    budget = get_budget_config(project_dir)
    entries = load_spend_log(project_dir)

    weekly = get_weekly_spend(entries)
    monthly = get_monthly_spend(entries)

    if weekly >= budget["weekly_max"]:
        issues.append(f"Weekly budget exceeded: ${weekly:.2f} / ${budget['weekly_max']:.2f}")
    elif weekly >= budget["weekly_max"] * 0.8:
        warnings.append(f"Weekly budget at 80%: ${weekly:.2f} / ${budget['weekly_max']:.2f}")

    if monthly >= budget["monthly_max"]:
        issues.append(f"Monthly budget exceeded: ${monthly:.2f} / ${budget['monthly_max']:.2f}")
    elif monthly >= budget["monthly_max"] * 0.8:
        warnings.append(f"Monthly budget at 80%: ${monthly:.2f} / ${budget['monthly_max']:.2f}")

    # Check consecutive rollbacks
    rollbacks = count_consecutive_rollbacks(project_dir)
    max_rollbacks = budget.get("max_consecutive_rollbacks", 3)
    if rollbacks >= max_rollbacks:
        issues.append(
            f"Consecutive rollbacks ({rollbacks}) hit limit ({max_rollbacks}). "
            f"Auto-kill triggered. Investigate before continuing."
        )
        # Auto-create kill file
        KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
        KILL_FILE.write_text(
            f"Auto-killed at {datetime.now().isoformat()} — {rollbacks} consecutive rollbacks\n"
        )

    safe = len(issues) == 0

    if json_output:
        print(json.dumps({
            "safe": safe,
            "issues": issues,
            "warnings": warnings,
            "weekly_spend": weekly,
            "monthly_spend": monthly,
            "consecutive_rollbacks": rollbacks,
            "kill_file_active": check_kill_file(),
        }, indent=2))
    else:
        if safe and not warnings:
            print("All safety checks passed.")
        else:
            if issues:
                print("BLOCKED — cannot proceed:")
                for issue in issues:
                    print(f"  [X] {issue}")
            if warnings:
                print("Warnings:")
                for warning in warnings:
                    print(f"  [!] {warning}")
            if safe:
                print("\nSafe to proceed (with warnings).")

    return safe


def do_budget(project_dir, json_output=False):
    """Show budget status."""
    budget = get_budget_config(project_dir)
    entries = load_spend_log(project_dir)

    weekly = get_weekly_spend(entries)
    monthly = get_monthly_spend(entries)
    total = sum(float(e.get("amount", 0)) for e in entries)

    if json_output:
        print(json.dumps({
            "weekly_spend": weekly,
            "weekly_max": budget["weekly_max"],
            "weekly_pct": round(weekly / budget["weekly_max"] * 100, 1) if budget["weekly_max"] > 0 else 0,
            "monthly_spend": monthly,
            "monthly_max": budget["monthly_max"],
            "monthly_pct": round(monthly / budget["monthly_max"] * 100, 1) if budget["monthly_max"] > 0 else 0,
            "total_spend": total,
            "per_run_max": budget["per_run_max"],
            "entry_count": len(entries),
        }, indent=2))
    else:
        print("Budget Status")
        print(f"  Per-run max:  ${budget['per_run_max']:.2f}")
        print(f"  Weekly:       ${weekly:.2f} / ${budget['weekly_max']:.2f} ({weekly/budget['weekly_max']*100:.0f}%)" if budget["weekly_max"] > 0 else f"  Weekly:       ${weekly:.2f} / unlimited")
        print(f"  Monthly:      ${monthly:.2f} / ${budget['monthly_max']:.2f} ({monthly/budget['monthly_max']*100:.0f}%)" if budget["monthly_max"] > 0 else f"  Monthly:      ${monthly:.2f} / unlimited")
        print(f"  All-time:     ${total:.2f} ({len(entries)} entries)")
        print(f"  Kill file:    {'ACTIVE' if check_kill_file() else 'inactive'}")


def run_self_tests():
    """Run basic self-tests."""
    import tempfile
    print("Running self-tests...")
    passed = 0
    failed = 0

    # Test 1: kill/unkill
    try:
        KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
        KILL_FILE.write_text("test\n")
        assert check_kill_file(), "Kill file should exist"
        KILL_FILE.unlink()
        assert not check_kill_file(), "Kill file should not exist"
        passed += 1
        print("  [PASS] kill/unkill")
    except Exception as e:
        failed += 1
        print(f"  [FAIL] kill/unkill: {e}")

    # Test 2: spend calculation
    try:
        now = datetime.now()
        entries = [
            {"timestamp": now.isoformat(), "amount": 0.10},
            {"timestamp": (now - timedelta(days=3)).isoformat(), "amount": 0.20},
            {"timestamp": (now - timedelta(days=10)).isoformat(), "amount": 0.50},
            {"timestamp": (now - timedelta(days=40)).isoformat(), "amount": 1.00},
        ]
        weekly = get_weekly_spend(entries)
        monthly = get_monthly_spend(entries)
        assert abs(weekly - 0.30) < 0.01, f"Weekly should be 0.30, got {weekly}"
        assert abs(monthly - 0.80) < 0.01, f"Monthly should be 0.80, got {monthly}"
        passed += 1
        print("  [PASS] spend calculation")
    except Exception as e:
        failed += 1
        print(f"  [FAIL] spend calculation: {e}")

    # Test 3: default budget
    try:
        b = DEFAULT_BUDGET
        assert b["per_run_max"] > 0
        assert b["weekly_max"] > 0
        assert b["monthly_max"] > 0
        assert b["max_consecutive_rollbacks"] > 0
        passed += 1
        print("  [PASS] default budget")
    except Exception as e:
        failed += 1
        print(f"  [FAIL] default budget: {e}")

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Autoresearch safety rails")
    parser.add_argument("command", nargs="?", choices=["check", "log-spend", "budget", "kill", "unkill"],
                        help="Safety command to run")
    parser.add_argument("amount", nargs="?", type=float, help="Spend amount (for log-spend)")
    parser.add_argument("--client", help="Client/project name")
    parser.add_argument("--note", default="", help="Note for spend log entry")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.test:
        success = run_self_tests()
        sys.exit(0 if success else 1)

    if args.command == "kill":
        KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
        KILL_FILE.write_text(f"Manually killed at {datetime.now().isoformat()}\n")
        print(f"Kill file created at {KILL_FILE}")
        print("All autoresearch runs are now blocked.")
        return

    if args.command == "unkill":
        if KILL_FILE.exists():
            KILL_FILE.unlink()
            print("Kill file removed. Autoresearch runs are unblocked.")
        else:
            print("No kill file found — already unblocked.")
        return

    # Commands below require --client
    if not args.client:
        print("ERROR: --client is required for this command", file=sys.stderr)
        sys.exit(1)

    project_root = P.find_project_root()
    if not project_root:
        print("ERROR: Could not find project root (no CLAUDE.md or skills/ found)", file=sys.stderr)
        sys.exit(1)

    project_dir, mode = P.require_project(project_root, args.client)

    if args.command == "check":
        safe = do_check(project_dir, args.json)
        sys.exit(0 if safe else 1)

    elif args.command == "log-spend":
        if args.amount is None:
            print("ERROR: amount is required for log-spend", file=sys.stderr)
            sys.exit(1)

        budget = get_budget_config(project_dir)
        if args.amount > budget["per_run_max"]:
            print(f"WARNING: Amount ${args.amount:.2f} exceeds per-run max ${budget['per_run_max']:.2f}", file=sys.stderr)

        save_spend_entry(project_dir, args.amount, args.note)
        if args.json:
            print(json.dumps({"logged": args.amount, "note": args.note}))
        else:
            print(f"Logged ${args.amount:.2f}" + (f" ({args.note})" if args.note else ""))

    elif args.command == "budget":
        do_budget(project_dir, args.json)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

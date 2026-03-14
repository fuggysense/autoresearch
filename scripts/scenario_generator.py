#!/usr/bin/env python3
"""Generate test scenarios for a skill + client combination.

Reads SKILL.md and client context, produces a structured prompt for Claude
to create test scenarios, then saves as scenarios.yaml.

Usage:
  scenario_generator.py <skill> --client <project> [--count N] [--save] [--json]
"""

import argparse
import json
import sys
from pathlib import Path

# Add scripts dir to path for paths module
sys.path.insert(0, str(Path(__file__).parent))
import paths as P

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def generate_scenario_prompt(skill_content, client_context, count=3):
    """Build the prompt that asks Claude to create test scenarios."""
    context_section = P.format_context_for_prompt(client_context)
    prompt = f"""You need to create {count} test scenarios for evaluating a skill's outputs.

## SKILL BEING TESTED
{skill_content[:3000]}

## CLIENT CONTEXT

{context_section}

## YOUR TASK

Create {count} realistic test scenarios — briefs that this skill should be able to handle well.
Each scenario should test a different aspect of the skill's capabilities.

Requirements:
- Scenarios must be specific to THIS client's business
- Vary difficulty: include at least one easy and one challenging scenario
- Each scenario has: id, name, brief (the actual task), expected_format, word_count_range
- The brief should be detailed enough for an AI to execute without additional context

Output ONLY valid YAML in this format:

```yaml
scenarios:
  - id: s1
    name: "Blog post for feature launch"
    brief: "Write a blog post announcing [specific feature]. Target audience is [ICP]. Tone should match brand voice. Include a clear CTA..."
    expected_format: "blog_post"
    word_count_range: [500, 1200]
  - id: s2
    name: "Social media campaign"
    brief: "Create a series of 3 social media posts for [platform]..."
    expected_format: "social_posts"
    word_count_range: [100, 400]
  # ... more scenarios
```"""
    return prompt


def main():
    parser = argparse.ArgumentParser(description="Generate test scenarios for autoresearch")
    parser.add_argument("skill", help="Skill name to create scenarios for")
    parser.add_argument("--client", required=True, help="Client/project name")
    parser.add_argument("--count", type=int, default=3, help="Number of scenarios to generate (default: 3)")
    parser.add_argument("--save", action="store_true",
                        help="Read YAML from stdin and save as scenarios.yaml")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    project_root = P.find_project_root()
    if not project_root:
        print("ERROR: Could not find project root (no CLAUDE.md or skills/ found)", file=sys.stderr)
        sys.exit(1)

    project_dir, mode = P.require_project(project_root, args.client)

    # Setup experiment directory
    exp_dir = P.experiment_dir(project_dir, args.skill)
    scenarios_path = exp_dir / "scenarios.yaml"

    # --save mode: read YAML from stdin and write scenarios.yaml
    if args.save:
        try:
            raw = sys.stdin.read()
            # Strip markdown code fences if present
            if "```yaml" in raw:
                raw = raw.split("```yaml", 1)[1]
                raw = raw.split("```", 1)[0]
            elif "```" in raw:
                raw = raw.split("```", 1)[1]
                raw = raw.split("```", 1)[0]

            data = yaml.safe_load(raw)
            if not data or "scenarios" not in data:
                print("ERROR: Input must contain 'scenarios' key", file=sys.stderr)
                sys.exit(1)

            with open(scenarios_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

            if args.json:
                print(json.dumps({"saved": str(scenarios_path), "scenario_count": len(data["scenarios"])}))
            else:
                print(f"Saved {len(data['scenarios'])} scenarios to {scenarios_path}")
            return
        except yaml.YAMLError as e:
            print(f"ERROR: Invalid YAML input: {e}", file=sys.stderr)
            sys.exit(1)

    # Normal mode: generate the prompt
    skill_path = P.find_skill_path(args.skill, project_root)
    if not skill_path:
        print(f"ERROR: SKILL.md not found for '{args.skill}'", file=sys.stderr)
        sys.exit(1)

    skill_content = skill_path.read_text(encoding="utf-8")
    client_context = P.load_context(project_dir, mode)

    # Check for existing scenarios
    if scenarios_path.exists():
        existing = yaml.safe_load(scenarios_path.read_text(encoding="utf-8"))
        count = len(existing.get("scenarios", [])) if existing else 0
        print(f"WARNING: scenarios.yaml already exists at {scenarios_path} ({count} scenarios)", file=sys.stderr)
        print("Use --save to overwrite with new scenarios from stdin.", file=sys.stderr)
        print()

    prompt = generate_scenario_prompt(skill_content, client_context, args.count)

    if args.json:
        print(json.dumps({
            "skill": args.skill,
            "client": args.client,
            "skill_path": str(skill_path),
            "scenarios_path": str(scenarios_path),
            "count": args.count,
            "prompt": prompt,
        }, indent=2))
    else:
        print(f"Scenario Generator — {args.skill} x {args.client}")
        print(f"Skill: {skill_path}")
        print(f"Output: {scenarios_path}")
        print(f"Count: {args.count}")
        print()
        print("--- PROMPT FOR CLAUDE ---")
        print(prompt)
        print("--- END PROMPT ---")
        print()
        print(f"To save the result: pipe YAML into this script with --save")
        print(f"  echo '<yaml>' | python3 {__file__} {args.skill} --client {args.client} --save")


if __name__ == "__main__":
    main()

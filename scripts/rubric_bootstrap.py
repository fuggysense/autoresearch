#!/usr/bin/env python3
"""Generate evaluation rubric for a skill + client combination.

Reads SKILL.md and client context, produces a structured prompt for Claude
to create binary yes/no evaluation criteria, then saves as rubric.yaml.

Usage:
  rubric_bootstrap.py <skill> --client <project> [--save] [--json]
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


def generate_rubric_prompt(skill_content, client_context):
    """Build the prompt that asks Claude to create evaluation criteria."""
    context_section = P.format_context_for_prompt(client_context)
    prompt = f"""You need to create an evaluation rubric for testing a skill's outputs.

## SKILL BEING EVALUATED
{skill_content[:3000]}

## CLIENT CONTEXT

{context_section}

## YOUR TASK

Create 5-8 binary (YES/NO) evaluation criteria for judging outputs from this skill.
Each criterion should be answerable with a simple YES or NO when reviewing a piece of content.

Requirements:
- Criteria must be specific to THIS skill + THIS client
- Mix of quality dimensions: relevance, tone, structure, actionability, accuracy
- Each criterion has: id, question, category, weight (1-3, where 3 = critical)
- Avoid vague criteria like "is it good?" — be precise

Output ONLY valid YAML in this format:

```yaml
criteria:
  - id: c1
    question: "Does the output address the target ICP's primary pain point?"
    category: relevance
    weight: 3
  - id: c2
    question: "Does the tone match the brand voice guidelines?"
    category: tone
    weight: 2
  # ... 3-6 more criteria
```"""
    return prompt


def main():
    parser = argparse.ArgumentParser(description="Bootstrap evaluation rubric for autoresearch")
    parser.add_argument("skill", help="Skill name to create rubric for")
    parser.add_argument("--client", required=True, help="Client/project name")
    parser.add_argument("--save", action="store_true",
                        help="Read YAML from stdin and save as rubric.yaml")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    project_root = P.find_project_root()
    if not project_root:
        print("ERROR: Could not find project root (no CLAUDE.md or skills/ found)", file=sys.stderr)
        sys.exit(1)

    project_dir, mode = P.require_project(project_root, args.client)

    # Setup experiment directory
    exp_dir = P.experiment_dir(project_dir, args.skill)
    rubric_path = exp_dir / "rubric.yaml"

    # --save mode: read YAML from stdin and write rubric.yaml
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
            if not data or "criteria" not in data:
                print("ERROR: Input must contain 'criteria' key", file=sys.stderr)
                sys.exit(1)

            with open(rubric_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

            if args.json:
                print(json.dumps({"saved": str(rubric_path), "criteria_count": len(data["criteria"])}))
            else:
                print(f"Saved {len(data['criteria'])} criteria to {rubric_path}")
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

    # Check for existing rubric
    if rubric_path.exists():
        existing = yaml.safe_load(rubric_path.read_text(encoding="utf-8"))
        count = len(existing.get("criteria", [])) if existing else 0
        print(f"WARNING: rubric.yaml already exists at {rubric_path} ({count} criteria)", file=sys.stderr)
        print("Use --save to overwrite with new criteria from stdin.", file=sys.stderr)
        print()

    prompt = generate_rubric_prompt(skill_content, client_context)

    if args.json:
        print(json.dumps({
            "skill": args.skill,
            "client": args.client,
            "skill_path": str(skill_path),
            "rubric_path": str(rubric_path),
            "prompt": prompt,
        }, indent=2))
    else:
        print(f"Rubric Bootstrap — {args.skill} x {args.client}")
        print(f"Skill: {skill_path}")
        print(f"Output: {rubric_path}")
        print()
        print("--- PROMPT FOR CLAUDE ---")
        print(prompt)
        print("--- END PROMPT ---")
        print()
        print(f"To save the result: pipe YAML into this script with --save")
        print(f"  echo '<yaml>' | python3 {__file__} {args.skill} --client {args.client} --save")


if __name__ == "__main__":
    main()

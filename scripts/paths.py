#!/usr/bin/env python3
"""Shared path resolution and LLM client for autoresearch.

Auto-detects environment:
- AgentKits mode: clients/<project>/ exists (icp.md, brand-voice.md, offer.md)
- Standalone mode: projects/<project>/ exists (context.md or any .md files)

Same scripts, same skill, one codebase.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError


def find_project_root():
    """Walk up from CWD looking for CLAUDE.md or skills/ directory."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "CLAUDE.md").exists() or (parent / "skills").is_dir():
            return parent
    return None


def find_skill_path(skill_name, project_root):
    """Locate SKILL.md — project skills first, then global."""
    candidates = [
        project_root / "skills" / skill_name / "SKILL.md",
        Path.home() / ".claude" / "skills" / skill_name / "SKILL.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def resolve_project(project_root, project_name):
    """Returns (project_dir, mode) where mode is 'agentkits' or 'standalone'.

    Checks clients/<name>/ first (AgentKits), falls back to projects/<name>/ (standalone).
    Returns (None, None) if neither exists.
    """
    agentkits = project_root / "clients" / project_name
    if agentkits.is_dir():
        return agentkits, "agentkits"

    standalone = project_root / "projects" / project_name
    if standalone.is_dir():
        return standalone, "standalone"

    return None, None


def load_context(project_dir, mode):
    """Load context files based on mode. Returns dict of {label: content}.

    AgentKits mode: reads icp.md, brand-voice.md, offer.md
    Standalone mode: reads context.md if it exists, else all .md files in project dir
    """
    context = {}

    if mode == "agentkits":
        file_labels = {
            "icp.md": "ICP (Ideal Customer Profile)",
            "brand-voice.md": "Brand Voice",
            "offer.md": "Offer",
        }
        for fname, label in file_labels.items():
            fpath = project_dir / fname
            if fpath.exists():
                context[label] = fpath.read_text(encoding="utf-8")
            else:
                context[label] = f"[{fname} not found]"
    else:
        # Standalone mode: context.md or all .md files
        context_file = project_dir / "context.md"
        if context_file.exists():
            context["Project Context"] = context_file.read_text(encoding="utf-8")
        else:
            for md_file in sorted(project_dir.glob("*.md")):
                label = md_file.stem.replace("-", " ").replace("_", " ").title()
                context[label] = md_file.read_text(encoding="utf-8")

        if not context:
            context["Project Context"] = "[No context files found — add context.md to your project directory]"

    return context


def autoresearch_dir(project_dir):
    """Returns path to autoresearch data dir, creates if needed."""
    ar_dir = project_dir / "autoresearch"
    ar_dir.mkdir(parents=True, exist_ok=True)
    return ar_dir


def experiment_dir(project_dir, skill_name):
    """Returns path to experiment dir for a skill, creates structure."""
    base = project_dir / "autoresearch" / "experiments" / skill_name
    (base / "winners").mkdir(parents=True, exist_ok=True)
    (base / "rollback").mkdir(parents=True, exist_ok=True)
    return base


def find_generation_script(project_root):
    """Returns path to research-llm.sh if exists, else None."""
    script = project_root / "scripts" / "research-llm.sh"
    if script.exists():
        return script
    return None


def _load_env_key(key):
    """Load API key from environment or .env file."""
    val = os.environ.get(key)
    if val:
        return val

    # Try .env in CWD and project root
    for search_dir in [Path.cwd(), find_project_root() or Path.cwd()]:
        env_file = search_dir / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _call_kilo_builtin(prompt, system_prompt=None):
    """Built-in Kilo Gateway client using urllib (no dependencies).

    Reads KILO_API_KEY from env or .env file.
    """
    api_key = _load_env_key("KILO_API_KEY")
    if not api_key:
        print("WARNING: KILO_API_KEY not found in env or .env", file=sys.stderr)
        return None

    full_prompt = prompt
    if system_prompt:
        full_prompt = f"[System Context]\n{system_prompt}\n\n[Task]\n{full_prompt}"

    payload = json.dumps({
        "model": "kilo-llm",
        "messages": [{"role": "user", "content": full_prompt}],
        "max_tokens": 4096,
    }).encode("utf-8")

    req = Request(
        "https://api.kilo.health/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"].strip()
    except (URLError, KeyError, json.JSONDecodeError) as e:
        print(f"WARNING: Built-in Kilo call failed: {e}", file=sys.stderr)
        return None


def call_llm(prompt, system_prompt=None, project_root=None):
    """Try research-llm.sh first, fall back to built-in Kilo Python client."""
    if project_root:
        script = find_generation_script(project_root)
        if script:
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"[System Context]\n{system_prompt}\n\n[Task]\n{full_prompt}"
            try:
                result = subprocess.run(
                    [str(script), "kilo", full_prompt],
                    capture_output=True, text=True, timeout=120,
                    cwd=str(project_root),
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
                print(f"WARNING: research-llm.sh failed, falling back to built-in client", file=sys.stderr)
            except (subprocess.TimeoutExpired, Exception) as e:
                print(f"WARNING: research-llm.sh error: {e}, falling back to built-in client", file=sys.stderr)

    return _call_kilo_builtin(prompt, system_prompt)


def format_context_for_prompt(context, mode="standalone"):
    """Format context dict into a prompt section with appropriate labels."""
    parts = []
    for label, content in context.items():
        parts.append(f"### {label}\n{content[:1500]}")
    return "\n\n".join(parts)


def require_project(project_root, client_name):
    """Resolve project or exit with error. Returns (project_dir, mode)."""
    project_dir, mode = resolve_project(project_root, client_name)
    if not project_dir:
        print(
            f"ERROR: Project '{client_name}' not found.\n"
            f"  Looked in: {project_root / 'clients' / client_name}\n"
            f"  Looked in: {project_root / 'projects' / client_name}\n"
            f"  Create one of these directories with context files.",
            file=sys.stderr,
        )
        sys.exit(1)
    return project_dir, mode

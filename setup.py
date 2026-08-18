#!/usr/bin/env python
"""Interactive setup for AgentMesh.

Creates the venv, installs dependencies, and prompts for secrets instead of
requiring manual file edits. Safe to re-run -- it won't overwrite an existing
value unless you choose to change it. Deliberately stdlib-only so it can run
before any dependency is installed.
"""

from __future__ import annotations

import getpass
import hashlib
import os
import platform
import secrets
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
VENV_DIR = BASE_DIR / ".venv"
ENV_PATH = BASE_DIR / ".env"
AGENTS_YAML_PATH = BASE_DIR / "relay" / "agents.yaml"
AGENT_CONFIG_PATH = BASE_DIR / "agent" / "config.yaml"


def venv_python() -> Path:
    if platform.system() == "Windows":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def prompt(label: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    if secret and sys.stdin.isatty():
        reader = getpass.getpass
    else:
        reader = input
        if secret:
            print("  (no interactive console detected -- input will be visible)")
    while True:
        try:
            value = reader(f"{label}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit("Setup cancelled.")
        if value:
            return value
        if default is not None:
            return default
        print("  (required, try again)")


def yes_no(label: str, default_yes: bool = True) -> bool:
    suffix = "[Y/n]" if default_yes else "[y/N]"
    while True:
        ans = input(f"{label} {suffix}: ").strip().lower()
        if not ans:
            return default_yes
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip()
    return values


def write_env(path: Path, values: dict[str, str]) -> None:
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")


def step_venv_and_deps() -> None:
    print("\n== Python environment ==")
    if not venv_python().exists():
        print(f"Creating virtual environment at {VENV_DIR} ...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    else:
        print("Virtual environment already exists, reusing it.")

    print("Installing dependencies (relay + agent) ...")
    subprocess.run(
        [str(venv_python()), "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
         "-r", str(BASE_DIR / "relay" / "requirements.txt"),
         "-r", str(BASE_DIR / "agent" / "requirements.txt")],
        check=True,
    )
    print("Dependencies installed.")


def step_secrets() -> dict[str, str]:
    print("\n== Secrets (.env) ==")
    existing = load_env(ENV_PATH)

    current_key = existing.get("ANTHROPIC_API_KEY", "")
    has_real_key = current_key and not current_key.startswith("sk-ant-placeholder")
    if has_real_key and not yes_no("An ANTHROPIC_API_KEY is already set -- replace it?", default_yes=False):
        api_key = current_key
    else:
        api_key = prompt("Anthropic API key (input hidden)", secret=True)

    current_viewer = existing.get("VIEWER_TOKEN", "")
    is_dev_default = current_viewer in ("", "dev-viewer-token-12345")
    if not is_dev_default and not yes_no("A VIEWER_TOKEN is already set -- replace it?", default_yes=False):
        viewer_token = current_viewer
    else:
        generated = secrets.token_urlsafe(24)
        viewer_token = prompt("Viewer token for the browser chat UI (Enter to auto-generate)", default=generated)

    write_env(ENV_PATH, {"VIEWER_TOKEN": viewer_token, "ANTHROPIC_API_KEY": api_key})
    print(f"Wrote {ENV_PATH}")
    return {"VIEWER_TOKEN": viewer_token, "ANTHROPIC_API_KEY": api_key}


def step_register_agent() -> None:
    print("\n== Register this machine as an agent ==")
    if not yes_no("Set this machine up as an AgentMesh agent now?", default_yes=True):
        print("Skipped. You can copy agent/config.example.yaml -> agent/config.yaml by hand later.")
        return

    default_id = platform.node().lower().replace(" ", "-")
    agent_id = prompt("agent_id for this machine", default=default_id)
    agent_secret = prompt("Shared secret for this agent (Enter to auto-generate)", default=secrets.token_urlsafe(32))
    secret_hash = hash_secret(agent_secret)

    hosts_relay = yes_no("Does this machine also host the relay?", default_yes=True)

    if hosts_relay:
        register_in_agents_yaml(agent_id, secret_hash)
        relay_host = prompt("Tailscale IP or MagicDNS name this relay will bind/be reached at", default="127.0.0.1")
        relay_port = prompt("Relay port", default="8765")
        relay_url = f"ws://{relay_host}:{relay_port}/ws/agent"
    else:
        relay_host = prompt("Relay machine's Tailscale IP or MagicDNS name")
        relay_port = prompt("Relay port", default="8765")
        relay_url = f"ws://{relay_host}:{relay_port}/ws/agent"
        print(
            "\nThis machine isn't hosting the relay, so I can't write relay/agents.yaml for you.\n"
            f"Send this to whoever manages the relay machine, to add under 'agents:' in relay/agents.yaml:\n"
            f"  {agent_id}: \"{secret_hash}\"\n"
            "(That's a hash -- it's safe to send; keep the plaintext secret below private.)"
        )

    write_agent_config(agent_id, relay_url, agent_secret)
    print(f"\nAgent secret for {agent_id} (keep this private, it's already saved in agent/config.yaml):")
    print(f"  {agent_secret}")


def register_in_agents_yaml(agent_id: str, secret_hash: str) -> None:
    lines = []
    if AGENTS_YAML_PATH.exists():
        lines = AGENTS_YAML_PATH.read_text(encoding="utf-8").splitlines()
    else:
        lines = ["agents:"]

    entry = f"  {agent_id}: \"{secret_hash}\""
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{agent_id}:"):
            lines[i] = entry
            replaced = True
            break
    if not replaced:
        lines.append(entry)

    AGENTS_YAML_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {AGENTS_YAML_PATH}")


def write_agent_config(agent_id: str, relay_url: str, token: str) -> None:
    content = (
        f"agent_id: {agent_id}\n"
        f"relay_url: {relay_url}\n"
        f"token: {token}\n"
        "model: claude-sonnet-5\n"
        "run_command_per_minute: 20\n"
        "max_consecutive_agent_turns: 6\n"
    )
    AGENT_CONFIG_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {AGENT_CONFIG_PATH}")


def main() -> None:
    print("AgentMesh setup")
    step_venv_and_deps()
    step_secrets()
    step_register_agent()
    print("\nDone. See README.md for how to start the relay and/or agent.")


if __name__ == "__main__":
    main()

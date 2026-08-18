"""Token auth for relay connections.

Threat model note: the relay is only reachable over the private Tailscale mesh,
never the public internet, so this uses a lightweight constant-time hash
comparison rather than pulling in bcrypt/argon2. Secrets are still never
stored or logged in plaintext.
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

import yaml


def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def load_agents(path: Path) -> dict[str, str]:
    """Load {agent_id: sha256(secret)} from a YAML file. Missing file -> empty."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in data.get("agents", {}).items()}


def verify_agent(agents: dict[str, str], agent_id: str, token: str) -> bool:
    expected = agents.get(agent_id)
    if expected is None:
        return False
    return hmac.compare_digest(expected, hash_secret(token))


def verify_viewer(viewer_token_hash: str | None, token: str) -> bool:
    if not viewer_token_hash:
        return False
    return hmac.compare_digest(viewer_token_hash, hash_secret(token))

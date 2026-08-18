"""Fully autonomous, no-denylist command execution across multiple interpreters.

Deliberately unrestricted per project decision: the calling LLM decides what
runs. Safety here is limited to capturing output/exit code and enforcing a
timeout so a hung command can't block the agent loop forever -- it does not
judge or block the command's content.
"""

import subprocess

INTERPRETERS = {
    "cmd": lambda cmd: ["cmd", "/c", cmd],
    "powershell": lambda cmd: ["powershell", "-NoProfile", "-Command", cmd],
    "bash": lambda cmd: ["bash", "-c", cmd],
    "sh": lambda cmd: ["sh", "-c", cmd],
    "python": lambda cmd: ["python", "-c", cmd],
    "go": lambda cmd: ["go", "run", "-"],  # code piped via stdin, see below
}


def run(interpreter: str, command: str, timeout: int = 120) -> dict:
    if interpreter not in INTERPRETERS:
        return {"error": f"unsupported interpreter '{interpreter}', choose from {list(INTERPRETERS)}"}

    try:
        if interpreter == "go":
            proc = subprocess.run(
                ["go", "run", "-"], input=command, capture_output=True, text=True, timeout=timeout,
            )
        else:
            argv = INTERPRETERS[interpreter](command)
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {"stdout": proc.stdout, "stderr": proc.stderr, "exit_code": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"error": f"command timed out after {timeout}s"}
    except FileNotFoundError as e:
        return {"error": f"interpreter not available on this machine: {e}"}

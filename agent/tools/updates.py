import platform
import shutil
import subprocess


def run() -> dict:
    if platform.system() == "Windows":
        return _windows()
    return _linux()


def _windows() -> dict:
    if not shutil.which("winget"):
        return {"error": "winget not found on PATH"}
    proc = subprocess.run(
        ["winget", "upgrade", "--accept-source-agreements"],
        capture_output=True, text=True, timeout=60,
    )
    return {"source": "winget", "stdout": proc.stdout, "stderr": proc.stderr, "exit_code": proc.returncode}


def _linux() -> dict:
    if shutil.which("apt"):
        subprocess.run(["apt", "update"], capture_output=True, text=True, timeout=120)
        proc = subprocess.run(["apt", "list", "--upgradable"], capture_output=True, text=True, timeout=60)
        return {"source": "apt", "stdout": proc.stdout, "stderr": proc.stderr, "exit_code": proc.returncode}
    if shutil.which("dnf"):
        proc = subprocess.run(["dnf", "check-update"], capture_output=True, text=True, timeout=60)
        return {"source": "dnf", "stdout": proc.stdout, "stderr": proc.stderr, "exit_code": proc.returncode}
    return {"error": "no supported package manager (apt/dnf) found on PATH"}

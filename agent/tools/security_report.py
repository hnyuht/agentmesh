"""Best-effort security posture snapshot using only native OS tools.

This is NOT a CVE-database vulnerability scanner. It reports what the OS
itself already knows: AV/protection status, pending security updates, and
listening network ports.
"""

import platform
import shutil
import subprocess

import psutil


def run() -> dict:
    listening = [
        {"laddr": f"{c.laddr.ip}:{c.laddr.port}", "pid": c.pid}
        for c in psutil.net_connections(kind="inet")
        if c.status == "LISTEN"
    ]
    report = {"listening_ports": listening}
    if platform.system() == "Windows":
        report.update(_windows())
    else:
        report.update(_linux())
    return report


def _windows() -> dict:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Get-MpComputerStatus | ConvertTo-Json"],
        capture_output=True, text=True, timeout=30,
    )
    return {"defender_status_raw": proc.stdout or proc.stderr}


def _linux() -> dict:
    if shutil.which("unattended-upgrade"):
        proc = subprocess.run(["unattended-upgrade", "--dry-run", "-v"], capture_output=True, text=True, timeout=60)
        return {"unattended_upgrades_raw": proc.stdout + proc.stderr}
    if shutil.which("apt"):
        proc = subprocess.run(
            ["bash", "-c", "apt list --upgradable 2>/dev/null | grep -i security"],
            capture_output=True, text=True, timeout=30,
        )
        return {"security_updates_raw": proc.stdout or "(none found or grep unavailable)"}
    return {"note": "no supported security-status tool found for this distro"}

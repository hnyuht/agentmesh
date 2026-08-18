import os
import platform
import shutil
import subprocess

LINUX_TERMINALS = ["gnome-terminal", "konsole", "xterm", "x-terminal-emulator"]


def run(shell: str = "default") -> dict:
    system = platform.system()
    if system == "Windows":
        exe = "powershell" if shell == "powershell" else "cmd"
        subprocess.Popen(["cmd", "/c", "start", exe], close_fds=True)
        return {"launched": exe, "platform": "Windows"}

    if not os.environ.get("DISPLAY"):
        return {"error": "no visible desktop session (DISPLAY not set) on this machine; cannot open a terminal window here"}

    for term in LINUX_TERMINALS:
        path = shutil.which(term)
        if path:
            subprocess.Popen([path], close_fds=True)
            return {"launched": term, "platform": "Linux"}

    return {"error": "no supported terminal emulator found (tried: " + ", ".join(LINUX_TERMINALS) + ")"}

import platform
import subprocess


def run() -> dict:
    if platform.system() == "Windows":
        proc = subprocess.run(["net", "user"], capture_output=True, text=True, timeout=30)
        return {"source": "net user", "stdout": proc.stdout, "stderr": proc.stderr, "exit_code": proc.returncode}
    return _linux()


def _linux() -> dict:
    users = []
    try:
        with open("/etc/passwd", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(":")
                if len(parts) >= 7:
                    uid = int(parts[2])
                    if uid >= 1000 or uid == 0:
                        users.append({"name": parts[0], "uid": uid, "home": parts[5], "shell": parts[6]})
    except OSError as e:
        return {"error": str(e)}

    proc = subprocess.run(["who"], capture_output=True, text=True, timeout=15)
    return {"users": users, "logged_in": proc.stdout}

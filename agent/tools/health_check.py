import platform

import psutil


def run() -> dict:
    cpu_pct = psutil.cpu_percent(interval=0.5)
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/" if platform.system() != "Windows" else "C:\\")

    top = sorted(
        psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
        key=lambda p: (p.info["cpu_percent"] or 0),
        reverse=True,
    )[:5]

    return {
        "cpu_percent": cpu_pct,
        "memory_percent": vm.percent,
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "top_processes": [
            {"pid": p.info["pid"], "name": p.info["name"], "cpu_percent": p.info["cpu_percent"], "memory_percent": round(p.info["memory_percent"] or 0, 1)}
            for p in top
        ],
        "warnings": _warnings(cpu_pct, vm.percent, disk.percent),
    }


def _warnings(cpu_pct: float, mem_pct: float, disk_pct: float) -> list[str]:
    warnings = []
    if cpu_pct > 90:
        warnings.append("CPU usage is critically high")
    if mem_pct > 90:
        warnings.append("Memory usage is critically high")
    if disk_pct > 90:
        warnings.append("Disk is nearly full")
    return warnings

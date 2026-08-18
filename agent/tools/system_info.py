import platform

import psutil


def run() -> dict:
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/" if platform.system() != "Windows" else "C:\\")
    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "release": platform.release(),
        "hostname": platform.node(),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "memory_total_gb": round(vm.total / (1024**3), 2),
        "memory_available_gb": round(vm.available / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2),
    }

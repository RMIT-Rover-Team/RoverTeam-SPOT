import psutil

def memory_vitals():
    vm = psutil.virtual_memory()
    return {
        "total_mb": vm.total // (1024 * 1024),
        "used_mb": vm.used // (1024 * 1024),
        "available_mb": vm.available // (1024 * 1024),
        "percent": vm.percent,
    }
#!/usr/bin/env python3
import time, json, psutil, subprocess, os
from dotenv import load_dotenv
load_dotenv()
LOG_PATH = os.getenv("MLINUX_METRICS_LOG")

LOW_UTIL_THRESHOLD = 10      # percent
STARVATION_SECONDS = 8       # how long low util before we call it "starved"
SAMPLE_INTERVAL = 1          # seconds

low_util_count = 0           # consecutive low-util samples

def get_gpu_stats():
    """
    Use `nvidia-smi` to get GPU utilization & memory per GPU.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            check=True
        )

        gpus = []
        for idx, line in enumerate(result.stdout.strip().splitlines()):
            if not line.strip():
                continue
            util_str, used_str, total_str = [x.strip() for x in line.split(",")]
            gpus.append({
                "index": idx,
                "gpu_util": int(util_str),
                "mem_used_MB": int(used_str),
                "mem_total_MB": int(total_str),
            })
        return {"gpu_detected": len(gpus) > 0, "gpus": gpus}

    except Exception as e:
        return {
            "gpu_detected": False,
            "gpus": [{"error": str(e)}]
        }

def get_process_gpu_stats():
    """
    Use `nvidia-smi` to get per-process GPU memory usage.
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_gpu_memory",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        procs = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            pid_str, name, mem_str = [x.strip() for x in line.split(",")]
            procs.append({
                "pid": int(pid_str),
                "name": name,
                "gpu_mem_MB": int(mem_str),
            })
        return procs
    except Exception:
        return []

os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

print(json.dumps({"event": "ml_profiler_started", "log_path": LOG_PATH}), flush=True)

while True:
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    gpu_info = get_gpu_stats()
    proc_gpu = get_process_gpu_stats()

    # --- GPU starvation detection ---
    global low_util_count
    gpu_starved = False
    if gpu_info["gpu_detected"] and gpu_info["gpus"]:
        # consider lowest util among GPUs
        min_util = min(
            g.get("gpu_util", 0)
            for g in gpu_info["gpus"]
            if "gpu_util" in g
        ) if any("gpu_util" in g for g in gpu_info["gpus"]) else 0

        if min_util < LOW_UTIL_THRESHOLD and proc_gpu:
            low_util_count += 1
        else:
            low_util_count = 0

        if low_util_count * SAMPLE_INTERVAL >= STARVATION_SECONDS:
            gpu_starved = True
    else:
        low_util_count = 0
        gpu_starved = False

    log = {
        "timestamp": time.time(),
        "cpu_usage": cpu,
        "mem_usage": mem,
        "gpu_detected": gpu_info["gpu_detected"],
        "gpus": gpu_info["gpus"],
        "process_gpu": proc_gpu,
        "gpu_starved": gpu_starved,
    }

    line = json.dumps(log)
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

    time.sleep(SAMPLE_INTERVAL)

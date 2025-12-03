#!/usr/bin/env python3
import time, json, psutil, subprocess, os
import psutil

# Resolve LOG_PATH dynamically with sensible fallbacks
def _resolve_log_path():
    # 1) Explicit override via environment variable
    env_path = os.getenv("MLINUX_LOG_PATH")
    if env_path:
        return env_path

    # 2) Workspace-relative (if running from repo or script directory)
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Try repo root candidates relative to script directory
        candidates = [
            os.path.join(script_dir, "..", "metrics.log"),
            os.path.join(script_dir, "..", "..", "mlinux-mvp", "metrics.log"),
            os.path.join(script_dir, "..", "mlinux-mvp", "metrics.log"),
        ]
        for p in candidates:
            p_norm = os.path.normpath(p)
            # If file already exists, prefer it
            if os.path.isfile(p_norm):
                return p_norm
            # Otherwise, remember the first reasonable candidate to create
        # Use the first candidate as default create location if parent exists
        for p in candidates:
            p_norm = os.path.normpath(p)
            parent = os.path.dirname(p_norm)
            if os.path.isdir(parent):
                return p_norm
    except Exception:
        pass

    # 3) User home fallback (cross-platform safe)
    home = os.path.expanduser("~")
    return os.path.join(home, "mlinux-mvp", "metrics.log")

LOG_PATH = _resolve_log_path()

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
_last_ctx_data = {} 
def get_scheduler_stats(pid):
    """
    Returns scheduler efficiency data for a given process.
    Includes:
      - voluntary context switches
      - involuntary context switches
      - thread count
      - switch rate (per second)
    """

    global _last_ctx_data

    try:
        p = psutil.Process(pid)
        ctx = p.num_ctx_switches()
        threads = p.num_threads()

        vol = ctx.voluntary
        invol = ctx.involuntary

        now = time.time()

        # Compute switch rate based on previous sample
        if pid in _last_ctx_data:
            prev_vol, prev_invol, prev_time = _last_ctx_data[pid]
            dt = max(now - prev_time, 1e-6)

            vol_rate = (vol - prev_vol) / dt
            invol_rate = (invol - prev_invol) / dt
        else:
            vol_rate = 0.0
            invol_rate = 0.0

        # Store for next iteration
        _last_ctx_data[pid] = (vol, invol, now)

        return {
            "voluntary": vol,
            "involuntary": invol,
            "threads": threads,
            "voluntary_rate": vol_rate,
            "involuntary_rate": invol_rate,
        }

    except Exception:
        return None

print(json.dumps({"event": "ml_profiler_started", "log_path": LOG_PATH}), flush=True)
_last_io = None

def detect_io_bottleneck():
    """
    Detect disk I/O bottlenecks based on:
      - read/write throughput
      - I/O wait time (CPU blocked on disk)
      - filesystem performance (WSL /mnt/c warning)
    """

    global _last_io
    current = psutil.disk_io_counters()
    now = time.time()

    if _last_io is None:
        _last_io = (current, now)
        return {
            "read_mb_s": 0,
            "write_mb_s": 0,
            "io_wait": psutil.cpu_times_percent().iowait,
            "filesystem": None,
            "bottleneck": False,
            "reason": "Not enough samples yet"
        }

    prev, prev_time = _last_io
    dt = max(now - prev_time, 1e-6)

    read_rate = (current.read_bytes - prev.read_bytes) / dt / (1024*1024)
    write_rate = (current.write_bytes - prev.write_bytes) / dt / (1024*1024)

    # Update last sample
    _last_io = (current, now)

    # CPU I/O wait percentage
    io_wait = psutil.cpu_times_percent().iowait

    # Identify filesystem type (WSL bottleneck)
    fs_path = os.getcwd()
    filesystem = "windows_mount" if fs_path.startswith("/mnt/") else "native_linux"

    bottleneck = False
    reasons = []

    if io_wait > 20:
        bottleneck = True
        reasons.append("High I/O wait (CPU blocked on disk)")

    if filesystem == "windows_mount":
        bottleneck = True
        reasons.append("Running on slow WSL Windows filesystem (/mnt/*)")

    if read_rate < 1 and write_rate < 1 and io_wait > 10:
        bottleneck = True
        reasons.append("Low throughput + high wait → disk too slow for dataloading")

    if not reasons:
        reasons.append("No significant I/O bottleneck")

    return {
        "read_mb_s": read_rate,
        "write_mb_s": write_rate,
        "io_wait": io_wait,
        "filesystem": filesystem,
        "bottleneck": bottleneck,
        "reason": "; ".join(reasons)
    }

def get_top_cpu_processes(limit=5):
    """
    Return top 'limit' processes sorted by CPU usage.
    Works perfectly in WSL.
    """
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
        try:
            procs.append(p.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort by CPU usage descending
    procs = sorted(procs, key=lambda x: x["cpu_percent"], reverse=True)

    return procs[:limit]
def detect_memory_pressure(window=5):
    """
    Predict OOM by analyzing memory usage growth.
    Returns:
      - memory_pressure_level: low / moderate / high / critical
      - oom_time_estimate: seconds remaining before OOM (approx)
    """

    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    free_mb = mem.available / (1024 * 1024)
    used_mb = mem.used / (1024 * 1024)
    total_mb = mem.total / (1024 * 1024)
    swap_used_mb = swap.used / (1024 * 1024)

    # Memory pressure classification
    if mem.percent < 60:
        level = "low"
    elif mem.percent < 80:
        level = "moderate"
    elif mem.percent < 90:
        level = "high"
    else:
        level = "critical"

    # Estimate OOM timeline based on memory rate of change
    # Capture memory over short window
    mem_before = mem.used
    time.sleep(0.2)
    mem_after = psutil.virtual_memory().used

    growth_rate_mb_s = (mem_after - mem_before) / (1024 * 1024) * 5  # scale to/sec
    oom_time = None

    if growth_rate_mb_s > 1:
        remaining_mb = total_mb - used_mb
        oom_time = remaining_mb / growth_rate_mb_s
    else:
        oom_time = None  # no meaningful growth

    return {
        "pressure": level,
        "free_mb": free_mb,
        "used_mb": used_mb,
        "swap_used_mb": swap_used_mb,
        "growth_rate_mb_s": growth_rate_mb_s,
        "oom_time_seconds": oom_time,
    }

def analyze_scheduler_behavior(sched):
    """
    Takes scheduler stats per process and returns:
      - interpretation string
      - flags: thrashing, contention, stuck_workers
    """

    vol_rate = sched["voluntary_rate"]
    invol_rate = sched["involuntary_rate"]
    threads = sched["threads"]

    # Flags
    thrashing = False
    contention = False
    stuck = False

    # Interpretation logic
    interp = []

    # 1. Detect thrashing
    if vol_rate > 200:
        thrashing = True
        interp.append("High voluntary switch rate → Possible thread thrashing (I/O bound).")

    # 2. Detect CPU contention
    if invol_rate > 30:
        contention = True
        interp.append("High involuntary switch rate → CPU contention; workers frequently preempted.")

    # 3. Detect stuck workers
    if threads > 4 and vol_rate < 1 and invol_rate < 1:
        stuck = True
        interp.append("Multiple threads but almost zero context switches → Worker threads may be stuck.")

    # Default interpretation
    if not interp:
        interp.append("Scheduler behavior normal.")

    return {
        "interpretation": " ".join(interp),
        "thrashing": thrashing,
        "contention": contention,
        "stuck": stuck
    }


while True:
    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    gpu_info = get_gpu_stats()
    proc_gpu = get_process_gpu_stats()
    top_cpu = get_top_cpu_processes()
    mem_status = detect_memory_pressure()
    io_status = detect_io_bottleneck()


    # --- GPU starvation detection ---
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
    scheduler_info = {}
    for proc in top_cpu:  
        pid = proc["pid"]
        sched = get_scheduler_stats(pid)
        analysis = analyze_scheduler_behavior(sched)
        scheduler_info[pid] = {
            **sched,
            **analysis
        }

        if sched:
            scheduler_info[pid] = sched

    log = {
        "timestamp": time.time(),
        "cpu_usage": cpu,
        "mem_usage": mem,
        "gpu_detected": gpu_info["gpu_detected"],
        "gpus": gpu_info["gpus"],
        "process_gpu": proc_gpu,
        "top_cpu_processes": top_cpu,    # NEW LINE
        "gpu_starved": gpu_starved,
        "log_memory": mem_status,
        "log_scheduler": scheduler_info,
        "log_io": io_status,
    }

    line = json.dumps(log)
    print(line, flush=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")

    time.sleep(SAMPLE_INTERVAL)



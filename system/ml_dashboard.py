#!/usr/bin/env python3
import time, json, os

# Resolve LOG_PATH dynamically to match ml_profiler.py behavior
def _resolve_log_path():
    # 1) Env var override
    env_path = os.getenv("MLINUX_LOG_PATH")
    if env_path:
        return env_path

    # 2) Try repo/script-relative candidates
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(script_dir, "..", "metrics.log"),
            os.path.join(script_dir, "..", "..", "mlinux-mvp", "metrics.log"),
            os.path.join(script_dir, "..", "mlinux-mvp", "metrics.log"),
        ]
        for p in candidates:
            p_norm = os.path.normpath(p)
            if os.path.isfile(p_norm):
                return p_norm
        for p in candidates:
            p_norm = os.path.normpath(p)
            parent = os.path.dirname(p_norm)
            if os.path.isdir(parent):
                return p_norm
    except Exception:
        pass

    # 3) Home fallback
    home = os.path.expanduser("~")
    return os.path.join(home, "mlinux-mvp", "metrics.log")

LOG_PATH = _resolve_log_path()

def read_last_line(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            lines = f.readlines()
            if not lines:
                return None
            return lines[-1].strip()
    except Exception:
        return None

def bar(pct, width=20):
    try:
        pct = float(pct)
    except:
        pct = 0
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)

while True:
    os.system("clear")
    print("=== MLinux Live Dashboard ===")
    print(f"Log source: {LOG_PATH}")
    line = read_last_line(LOG_PATH)
    if not line:
        print("No metrics yet. Is mlprofiler running?")
        time.sleep(1)
        continue

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        print("Last log line invalid JSON:")
        print(line)
        time.sleep(1)
        continue

    cpu = data.get("cpu_usage", 0)
    mem = data.get("mem_usage", 0)
    gpus = data.get("gpus", [])
    procs = data.get("process_gpu", [])

    print()
    print(f"CPU: {cpu:.1f}%  [{bar(cpu)}]")
    print(f"RAM: {mem:.1f}%  [{bar(mem)}]")

    print("\nGPUs:")
    if not gpus:
        print("  (no GPU info)")
    else:
        for g in gpus:
            if "error" in g:
                print(f"  GPU{g.get('index','?')}: ERROR: {g['error']}")
            else:
                util = g.get("gpu_util", 0)
                used = g.get("mem_used_MB", 0)
                total = g.get("mem_total_MB", 0)
                print(f"  GPU{g['index']}: {util:3d}% [{bar(util)}]  Mem: {used}/{total} MB")
    if "top_cpu_processes" in data:
        print("\nTop CPU Processes:")
        for p in data["top_cpu_processes"]:
            name = p.get("name", "unknown")
            pid = p.get("pid", "?")
            cpu = p.get("cpu_percent", 0)
            print(f"  PID {pid:<6} {name:<20} CPU: {cpu:>5.1f}%")

    print("\nProcesses using GPU:")
    if not procs:
        print("  (none)")
    else:
        for p in procs:
            print(f"  PID {p['pid']:5d}  {p['name']:<20}  {p['gpu_mem_MB']:5d} MB")
    if "log_memory" in data:
        mem = data["log_memory"]
        print(f"Memory Pressure:        {mem['pressure']}")
        print(f"Free Memory:            {mem['free_mb']:.1f} MB")
        print(f"Used Memory:            {mem['used_mb']:.1f} MB")
        print(f"Swap Used:              {mem['swap_used_mb']:.1f} MB")
        print(f"Memory Growth Rate:     {mem['growth_rate_mb_s']:.2f} MB/s")

        if mem['oom_time_seconds']:
            print(f"OOM in approx:          {mem['oom_time_seconds']:.1f} sec")
        else:
            print("OOM Risk:               No immediate risk")
    if "log_scheduler" in data:
        print("\nScheduler Metrics:")
        for pid, sched in data["log_scheduler"].items():
            print(f" PID {pid}: threads={sched['threads']}  "
                f"vol={sched['voluntary']}  invol={sched['involuntary']}  "
                f"vol_rate={sched['voluntary_rate']:.1f}/s  "
                f"invol_rate={sched['involuntary_rate']:.1f}/s")
    
    if "log_io" in data:
        io = data["log_io"]
        print("\nDisk I/O:")
        print(f" Read Speed:      {io['read_mb_s']:.2f} MB/s")
        print(f" Write Speed:     {io['write_mb_s']:.2f} MB/s")
        print(f" I/O Wait:        {io['io_wait']:.1f}%")
        print(f" Filesystem:      {io['filesystem']}")
        print(f" Bottleneck:      {io['bottleneck']}")
        print(f" Reason:          {io['reason']}")



    print("\n(Refreshes every second; Ctrl+C to exit)")
    time.sleep(1)

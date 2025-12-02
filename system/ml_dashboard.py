#!/usr/bin/env python3
import time, json, os
from dotenv import load_dotenv
load_dotenv()
LOG_PATH = os.getenv("MLINUX_METRICS_LOG")
REFRESH = int(os.getenv("MLINUX_DASHBOARD_REFRESH", "1"))

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

    print("\nProcesses using GPU:")
    if not procs:
        print("  (none)")
    else:
        for p in procs:
            print(f"  PID {p['pid']:5d}  {p['name']:<20}  {p['gpu_mem_MB']:5d} MB")

    print("\n(Refreshes every second; Ctrl+C to exit)")
    time.sleep(1)

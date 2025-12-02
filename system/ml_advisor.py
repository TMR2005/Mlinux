#!/usr/bin/env python3
import json, os

LOG_PATH = "/home/praveenkumar/mlinux-mvp/metrics.log"

def read_last_line(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        lines = f.readlines()
        if not lines:
            return None
        return lines[-1].strip()

line = read_last_line(LOG_PATH)
if not line:
    print("No metrics found. Is mlprofiler running?")
    exit(0)

try:
    data = json.loads(line)
except json.JSONDecodeError:
    print("Last metrics line is invalid JSON.")
    print(line)
    exit(0)

gpus = data.get("gpus", [])
if not gpus or "gpu_util" not in gpus[0] or "mem_used_MB" not in gpus[0] or "mem_total_MB" not in gpus[0]:
    print("No GPU metrics available.")
    exit(0)

gpu = gpus[0]
util = gpu["gpu_util"]
mem_used = gpu["mem_used_MB"]
mem_total = gpu["mem_total_MB"]
mem_pct = (mem_used / mem_total * 100) if mem_total > 0 else 0

print("=== MLinux Batch Size Advisor ===")
print(f"Current GPU util: {util}%")
print(f"Current GPU mem : {mem_used}/{mem_total} MB ({mem_pct:.1f}%)")

if util < 30 and mem_pct < 50:
    print("\nSuggestion: GPU is underutilized and memory usage is low.")
    print("→ You can likely INCREASE batch size to improve throughput.")
elif util > 80 or mem_pct > 80:
    print("\nSuggestion: GPU is heavily loaded.")
    print("→ Consider REDUCING batch size slightly to avoid OOM and throttling.")
else:
    print("\nSuggestion: Batch size looks reasonably balanced for current workload.")

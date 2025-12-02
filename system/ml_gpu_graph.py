#!/usr/bin/env python3
import json
from collections import deque

LOG_PATH = "/home/praveenkumar/mlinux-mvp/metrics.log"
SAMPLES = 30  # last 30 samples

def bar(pct, width=30):
    try:
        pct = float(pct)
    except:
        pct = 0
    filled = int(width * pct / 100)
    return "█" * filled + "░" * (width - filled)

lines = deque(maxlen=SAMPLES)

with open(LOG_PATH, "r") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("{\"event\""):
            continue
        lines.append(line)

print("=== MLinux GPU Utilization Graph (last {} samples) ===".format(len(lines)))

for line in lines:
    try:
        data = json.loads(line)
        gpus = data.get("gpus", [])
        if not gpus or "gpu_util" not in gpus[0]:
            continue
        util = gpus[0]["gpu_util"]
        print(f"{util:3d}% |{bar(util)}|")
    except Exception:
        continue

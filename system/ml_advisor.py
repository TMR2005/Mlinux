#!/usr/bin/env python3
import json
import os
import argparse
from dotenv import load_dotenv
load_dotenv()
LOG_PATH = os.getenv("MLINUX_METRICS_LOG")

def read_last_line(path):
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        lines = f.readlines()
        if not lines:
            return None
        return lines[-1].strip()

def compute_recommended_batch(current_batch, util, mem_used, mem_total):
    if mem_total <= 0:
        # no VRAM info → only use util, be conservative
        mem_pct = 0
    else:
        mem_pct = mem_used / mem_total * 100.0

    B = current_batch
    U = util
    M = mem_pct

    # --- Underutilized & low memory: increase batch size ---
    if U < 40 and M < 60:
        # how much we can scale before ~90% VRAM
        if M > 0:
            mem_scale_max = 0.9 / (M / 100.0)   # 90% / current_usage
        else:
            mem_scale_max = 2.0                # we have no idea; safe default

        # clamp to [1.2, 3.0]
        mem_scale_max = max(1.2, min(mem_scale_max, 3.0))

        scale = min(2.0, mem_scale_max)        # never more than 2x at once
        new_B = int(B * scale)

        reason = (
            "GPU is underutilized and VRAM usage is low; "
            f"safe to increase batch size by ~{scale:.1f}x."
        )

    # --- Overloaded: reduce batch size ---
    elif U > 90 or M > 85:
        if M > 95:
            scale = 0.5   # aggressive cut if very close to OOM
        else:
            scale = 0.75  # mild reduction

        new_B = max(1, int(B * scale))
        reason = (
            "GPU/VRAM is heavily loaded; reducing batch size "
            f"by ~{(1-scale)*100:.0f}% to avoid OOM and throttling."
        )

    # --- Balanced: keep as is ---
    else:
        new_B = B
        reason = (
            "GPU utilization and VRAM usage appear balanced; "
            "keeping current batch size."
        )

    return new_B, M, reason

def main():
    parser = argparse.ArgumentParser(
        description="MLinux Batch Size Advisor (numeric optimizer)"
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        required=True,
        help="Current batch size used in your training script"
    )
    parser.add_argument(
        "--log-path",
        type=str,
        default=LOG_PATH,
        help=f"Path to MLinux metrics.log (default: {LOG_PATH})"
    )
    args = parser.parse_args()

    line = read_last_line(args.log_path)
    if not line:
        print("No metrics found. Is mlprofiler running?")
        return

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        print("Last metrics line is invalid JSON:")
        print(line)
        return

    gpus = data.get("gpus", [])
    if not gpus or "gpu_util" not in gpus[0] or \
       "mem_used_MB" not in gpus[0] or "mem_total_MB" not in gpus[0]:
        print("No GPU metrics available. Cannot compute batch size suggestion.")
        return

    gpu = gpus[0]
    util = gpu["gpu_util"]
    mem_used = gpu["mem_used_MB"]
    mem_total = gpu["mem_total_MB"]

    new_batch, mem_pct, reason = compute_recommended_batch(
        args.batch_size, util, mem_used, mem_total
    )

    print("=== MLinux Batch Size Advisor ===")
    print(f"Current batch size : {args.batch_size}")
    print(f"GPU util          : {util}%")
    print(f"GPU mem           : {mem_used}/{mem_total} MB ({mem_pct:.1f}%)\n")
    print("Recommendation:")
    if new_batch == args.batch_size:
        print(f"→ Keep batch size at {args.batch_size}.")
    elif new_batch > args.batch_size:
        print(f"→ Increase batch size to ~{new_batch}.")
    else:
        print(f"→ Decrease batch size to ~{new_batch}.")
    print(f"\nReason: {reason}")

if __name__ == "__main__":
    main()

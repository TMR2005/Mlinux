import json
import time
import os
from ml_summary import _resolve_log_path

LOG_PATH = _resolve_log_path()


def tail_metrics(path, lines=50):
    """Return last N valid metric lines."""
    if not os.path.isfile(path):
        print("No metrics.log found.")
        return []

    with open(path, "r") as f:
        data = f.readlines()[-lines:]

    metrics = []
    for line in data:
        try:
            j = json.loads(line.strip())
            if "log_scheduler" in j:
                metrics.append(j)
        except:
            continue
    return metrics


def show_scheduler_page():
    os.system("clear")
    print("=== MLinux Scheduler Diagnostics ===")
    print(f"Log source: {LOG_PATH}")

    metrics = tail_metrics(LOG_PATH, lines=40)
    if not metrics:
        print("\nNo scheduler metrics found. Is ml_profiler running?")
        return

    latest = metrics[-1]
    sched = latest.get("log_scheduler", {})

    print("\nPer-Process Scheduler Stats:\n")

    for pid, s in sched.items():
        print(f" PID {pid}:")
        print(f"   Threads:              {s['threads']}")
        print(f"   Voluntary Rate:       {s['voluntary_rate']:.1f}/s")
        print(f"   Involuntary Rate:     {s['involuntary_rate']:.1f}/s")
        print(f"   Interpretation:        {s['interpretation']}")
        print()

    print("==========================================")


if __name__ == "__main__":
    while True:
        show_scheduler_page()
        time.sleep(1)

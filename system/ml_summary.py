import json
import os
from datetime import timedelta

# ---------------------------------------------------
# PATH RESOLUTION
# ---------------------------------------------------

def _resolve_log_path():
    """
    Attempts to automatically find metrics.log based on:
    1. Environment variable
    2. Script-relative paths
    3. Home-directory fallback
    """
    env_path = os.getenv("MLINUX_LOG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(script_dir, "metrics.log"),
            os.path.join(script_dir, "..", "metrics.log"),
            os.path.join(script_dir, "..", "..", "metrics.log"),
            os.path.join(script_dir, "..", "mlinux-mvp", "metrics.log"),
            os.path.join(script_dir, "..", "..", "mlinux-mvp", "metrics.log"),
        ]
        for path in candidates:
            norm = os.path.normpath(path)
            if os.path.isfile(norm):
                return norm
    except:
        pass

    return os.path.join(os.path.expanduser("~"), "mlinux-mvp", "metrics.log")


LOG_PATH = _resolve_log_path()

# ---------------------------------------------------
# LOG LOADING
# ---------------------------------------------------

def load_metrics(path):
    metrics = []
    if not os.path.isfile(path):
        print(f"Could not find metrics.log at: {path}")
        return metrics

    with open(path, "r") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                # ignore non-metrics events
                if "cpu_usage" in data:
                    metrics.append(data)
            except:
                continue
    return metrics

# ---------------------------------------------------
# SUMMARY COMPUTATION
# ---------------------------------------------------

def compute_summary(metrics):
    if not metrics:
        return None

    start_time = metrics[0]["timestamp"]
    end_time = metrics[-1]["timestamp"]
    duration = timedelta(seconds=int(end_time - start_time))

    cpu_values = []
    gpu_values = []
    vram_values = []
    starvation_events = 0
    cpu_hog_counts = {}

    pressure_levels = []
    free_mem_values = []
    swap_values = []
    growth_rates = []
    oom_times = []

    vol_rates = []
    invol_rates = []
    thread_counts = []

    thrash_count = 0
    contention_count = 0
    stuck_count = 0
    interpretations = []

    io_wait_values = []
    read_speeds = []
    write_speeds = []
    bottleneck_flags = []
    io_reasons = []

    # -----------------------------
    # SAFE PARSING FOR EACH ENTRY
    # -----------------------------
    for m in metrics:

        cpu_values.append(m.get("cpu_usage", 0))

        # ------------ GPU -------------
        if m.get("gpu_detected") and m.get("gpus"):
            g = m["gpus"][0]
            gpu_values.append(g.get("gpu_util", 0))
            vram_values.append(g.get("mem_used_mb", 0))
        else:
            gpu_values.append(0)
            vram_values.append(0)

        # ------------ starvation -------------
        if m.get("gpu_starved"):
            starvation_events += 1

        # ------------ cpu hog processes -------------
        for proc in m.get("top_cpu_processes", []):
            name = proc.get("name", "unknown")
            cpu = proc.get("cpu_percent", 0)
            if cpu > 50:
                cpu_hog_counts[name] = cpu_hog_counts.get(name, 0) + 1

        # ------------ memory section -------------
        mem = m.get("log_memory")
        if mem:
            pressure_levels.append(mem.get("pressure", "low"))
            free_mem_values.append(mem.get("free_mb", 0))
            swap_values.append(mem.get("swap_used_mb", 0))
            growth_rates.append(mem.get("growth_rate_mb_s", 0))

            if mem.get("oom_time_seconds") is not None:
                oom_times.append(mem["oom_time_seconds"])

        # ------------ scheduler section -------------
        sched = m.get("log_scheduler")
        if isinstance(sched, dict):

            # full scheduler metrics (vol, invol, threads)
            for pid, s in sched.items():
                vol_rates.append(s.get("voluntary_rate", 0))
                invol_rates.append(s.get("involuntary_rate", 0))
                thread_counts.append(s.get("threads", 0))

                if s.get("thrashing"):
                    thrash_count += 1
                if s.get("contention"):
                    contention_count += 1
                if s.get("stuck"):
                    stuck_count += 1
                interpretations.append(s.get("interpretation", ""))

        # ------------ I/O section -------------
        io = m.get("log_io")
        if io:
            io_wait_values.append(io.get("io_wait", 0))
            read_speeds.append(io.get("read_mb_s", 0))
            write_speeds.append(io.get("write_mb_s", 0))
            bottleneck_flags.append(io.get("bottleneck", False))
            io_reasons.append(io.get("reason", "unknown"))

    # ---------------------------------------------------
    # COMPUTE AGGREGATES
    # ---------------------------------------------------

    avg_cpu = sum(cpu_values) / len(cpu_values)
    avg_gpu = sum(gpu_values) / len(gpu_values)
    peak_gpu = max(gpu_values)
    avg_vram = sum(vram_values) / len(vram_values)
    peak_vram = max(vram_values)

    top_hog = max(cpu_hog_counts, key=cpu_hog_counts.get) if cpu_hog_counts else "None"

    # health score
    health = 100
    if avg_gpu < 40:
        health -= 25
    if avg_cpu > 80:
        health -= 20
    if starvation_events > 10:
        health -= 30
    health = max(0, health)

    # batch size logic (simple)
    if avg_gpu < 40:
        batch_recommend = "Increase batch size."
    elif peak_gpu > 90:
        batch_recommend = "Reduce batch size."
    else:
        batch_recommend = "Batch size is appropriate."

    # memory pressure score
    pressure_count = {
        "low": pressure_levels.count("low"),
        "moderate": pressure_levels.count("moderate"),
        "high": pressure_levels.count("high"),
        "critical": pressure_levels.count("critical")
    }
    total_p = len(pressure_levels)
    if total_p:
        score = (
            pressure_count["moderate"] * 1 +
            pressure_count["high"] * 2 +
            pressure_count["critical"] * 3
        ) / total_p
    else:
        score = 0

    if score >= 2.5:
        summary_pressure = "critical"
    elif score >= 1.5:
        summary_pressure = "high"
    elif score >= 0.5:
        summary_pressure = "moderate"
    else:
        summary_pressure = "low"

    # ---------------------------------------------------
    # RETURN SUMMARY DATA
    # ---------------------------------------------------

    return {
        "duration": duration,
        "avg_cpu": avg_cpu,
        "avg_gpu": avg_gpu,
        "peak_gpu": peak_gpu,
        "avg_vram": avg_vram,
        "peak_vram": peak_vram,
        "starvation_events": starvation_events,
        "top_cpu_hog": top_hog,
        "health_score": health,
        "batch_recommend": batch_recommend,
        "memory_pressure": summary_pressure,
        "min_free_mem": min(free_mem_values) if free_mem_values else None,
        "max_swap_usage": max(swap_values) if swap_values else None,
        "peak_growth_rate": max(growth_rates) if growth_rates else None,
        "earliest_oom_prediction": min(oom_times) if oom_times else None,
        "sched_peak_vol_rate": max(vol_rates) if vol_rates else None,
        "sched_peak_invol_rate": max(invol_rates) if invol_rates else None,
        "max_threads": max(thread_counts) if thread_counts else None,
        "sched_thrashing_events": thrash_count,
        "sched_contention_events": contention_count,
        "sched_stuck_workers": stuck_count,
        "sched_interpretations": list(set(interpretations)),
        "avg_io_wait": sum(io_wait_values)/len(io_wait_values) if io_wait_values else None,
        "max_io_wait": max(io_wait_values) if io_wait_values else None,
        "avg_read_speed": sum(read_speeds)/len(read_speeds) if read_speeds else None,
        "avg_write_speed": sum(write_speeds)/len(write_speeds) if write_speeds else None,
        "io_bottlenecks": bottleneck_flags.count(True),
        "io_reasons": list(set(io_reasons)),
    }

# ---------------------------------------------------
# PRINT SUMMARY
# ---------------------------------------------------

def print_summary(s):

    print("\n========== MLinux Training Summary ==========")
    print(f"Total Session Time:           {s['duration']}")
    print(f"Average CPU Usage:            {s['avg_cpu']:.2f}%")
    print(f"Average GPU Utilization:      {s['avg_gpu']:.2f}%")
    print(f"Peak GPU Utilization:         {s['peak_gpu']}%")
    print(f"Average VRAM Usage:           {s['avg_vram']:.2f} MB")
    print(f"Peak VRAM Usage:              {s['peak_vram']} MB")
    print(f"GPU Starvation Events:        {s['starvation_events']}")
    print(f"Top CPU Hog Process:          {s['top_cpu_hog']}")
    print(f"System Health Score:          {s['health_score']} / 100\n")
    print(f"Batch Size Recommendation:    {s['batch_recommend']}")

    print("\n--- Memory Health ---")
    if s["min_free_mem"] is not None:
        print(f"Lowest Free Memory:          {s['min_free_mem']:.1f} MB")
    else:
        print("No memory data")

    if s["max_swap_usage"] is not None:
        print(f"Highest Swap Usage:          {s['max_swap_usage']:.1f} MB")
    else:
        print("Swap data unavailable")

    if s["peak_growth_rate"] is not None:
        print(f"Peak Memory Growth Rate:     {s['peak_growth_rate']:.2f} MB/s")
    else:
        print("No growth data")

    if s["earliest_oom_prediction"]:
        print(f"Predicted Time to OOM:       {s['earliest_oom_prediction']:.1f} sec")
    else:
        print("Predicted Time to OOM:       No immediate risk")

    print("\n--- Scheduler Efficiency ---")
    print(f"Peak Voluntary Switch Rate:   {s['sched_peak_vol_rate']}")
    print(f"Peak Involuntary Switch Rate: {s['sched_peak_invol_rate']}")
    print(f"Maximum Thread Count:         {s['max_threads']}")
    print(f"Thrashing Events:             {s['sched_thrashing_events']}")
    print(f"Contention Events:            {s['sched_contention_events']}")
    print(f"Stuck Workers:                {s['sched_stuck_workers']}")

    print("\n--- Disk I/O Summary ---")
    print(f"Average Read Speed:         {s['avg_read_speed']}")
    print(f"Average Write Speed:        {s['avg_write_speed']}")
    print(f"Average I/O Wait:           {s['avg_io_wait']}")
    print(f"Max I/O Wait:               {s['max_io_wait']}")
    print(f"I/O Bottleneck Events:      {s['io_bottlenecks']}")

    print("Reasons:")
    for reason in s["io_reasons"]:
        print(f" - {reason}")

    print("==============================================\n")


# ---------------------------------------------------
# MAIN
# ---------------------------------------------------

if __name__ == "__main__":
    print(f"Resolved log path: {LOG_PATH}")
    metrics = load_metrics(LOG_PATH)
    summary = compute_summary(metrics)

    if summary is None:
        print("No valid metrics found in log.")
    else:
        print_summary(summary)

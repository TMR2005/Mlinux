import json
import os
from datetime import timedelta

def _resolve_log_path():
    """
    Attempts to automatically find metrics.log based on:
    1. Environment variable
    2. Script-relative paths
    3. Home-directory fallback
    """

    # 1) ENV override
    env_path = os.getenv("MLINUX_LOG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path

    # 2) Try script-relative paths
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
    except Exception:
        pass

    # 3) Home fallback
    home = os.path.expanduser("~")
    fallback = os.path.join(home, "mlinux-mvp", "metrics.log")
    return fallback


LOG_PATH = _resolve_log_path()


def load_metrics(path):
    metrics = []
    if not os.path.isfile(path):
        print(f"Could not find metrics.log at: {path}")
        return metrics

    with open(path, "r") as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                if "cpu_usage" in data:  # skip event messages
                    metrics.append(data)
            except:
                continue
    return metrics


def compute_summary(metrics):
    if not metrics:
        return None

    # time
    start_time = metrics[0]["timestamp"]
    end_time = metrics[-1]["timestamp"]
    duration = timedelta(seconds=int(end_time - start_time))

    cpu_values = [m["cpu_usage"] for m in metrics]
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
    bottleneck_flags = []
    read_speeds = []
    write_speeds = []
    io_reasons = []



    for m in metrics:
        # GPU info
        if m["gpu_detected"] and m["gpus"]:
            g = m["gpus"][0]
            gpu_values.append(g.get("gpu_util", 0))
            vram_values.append(g.get("mem_used_mb", 0))
        else:
            gpu_values.append(0)
            vram_values.append(0)

        # starvation
        if m.get("gpu_starved"):
            starvation_events += 1

        # CPU hog detection
        for proc in m.get("top_cpu_processes", []):
            name = proc["name"]
            cpu = proc["cpu_percent"]
            if cpu > 50:
                cpu_hog_counts[name] = cpu_hog_counts.get(name, 0) + 1
        if "log_memory" in m:
      
            for pid, sched in m["log_scheduler"].items():
                vol_rates.append(sched.get("voluntary_rate", 0))
                invol_rates.append(sched.get("involuntary_rate", 0))
                thread_counts.append(sched.get("threads", 0))
            mem = m["log_memory"]
            pressure_levels.append(mem.get("pressure", "low"))
            free_mem_values.append(mem.get("free_mb", 0))
            swap_values.append(mem.get("swap_used_mb", 0))
            growth_rates.append(mem.get("growth_rate_mb_s", 0))

            # OOM predictions may be None, skip empty entries
            if mem.get("oom_time_seconds") is not None:
                oom_times.append(mem["oom_time_seconds"])
        if "log_scheduler" in m:
            for pid, s in m["log_scheduler"].items():
                if s.get("thrashing"):
                    thrash_count += 1
                if s.get("contention"):
                    contention_count += 1
                if s.get("stuck"):
                    stuck_count += 1
                interpretations.append(s.get("interpretation", ""))
        if "log_io" in m:
            io = m["log_io"]
            io_wait_values.append(io["io_wait"])
            read_speeds.append(io["read_mb_s"])
            write_speeds.append(io["write_mb_s"])
            bottleneck_flags.append(io["bottleneck"])
            io_reasons.append(io["reason"])




    avg_cpu = sum(cpu_values) / len(cpu_values)
    avg_gpu = sum(gpu_values) / len(gpu_values)
    peak_gpu = max(gpu_values)
    avg_vram = sum(vram_values) / len(vram_values)
    peak_vram = max(vram_values)

    top_hog = max(cpu_hog_counts, key=cpu_hog_counts.get) if cpu_hog_counts else "None"

    # Basic health score
    health = 100
    if avg_gpu < 40:
        health -= 25
    if avg_cpu > 80:
        health -= 20
    if starvation_events > 10:
        health -= 30
    health = max(0, health)

    # Batch size logic
    if avg_gpu < 40 and peak_vram < (0.5 * peak_vram if peak_vram else 1):
        batch_recommend = "Increase batch size."
    elif peak_gpu > 90 and peak_vram > 0.85 * peak_vram:
        batch_recommend = "Reduce batch size."
    else:
        batch_recommend = "Batch size is appropriate."
    # Memory pressure summary
    pressure_count = {
        "low": pressure_levels.count("low"),
        "moderate": pressure_levels.count("moderate"),
        "high": pressure_levels.count("high"),
        "critical": pressure_levels.count("critical")
    }

    total = len(pressure_levels)
    if total > 0:
        # approximate pressure score
        pressure_score = (
            pressure_count["low"] * 0 +
            pressure_count["moderate"] * 1 +
            pressure_count["high"] * 2 +
            pressure_count["critical"] * 3
        ) / total
    else:
        pressure_score = 0

    summary_pressure = "low"
    if pressure_score >= 2.5:
        summary_pressure = "critical"
    elif pressure_score >= 1.5:
        summary_pressure = "high"
    elif pressure_score >= 0.5:
        summary_pressure = "moderate"


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
    print(f"Overall Memory Pressure:     {s['memory_pressure']}")
    print(f"Lowest Free Memory:          {s['min_free_mem']:.1f} MB" if s['min_free_mem'] else "No memory data")
    print(f"Highest Swap Usage:          {s['max_swap_usage']:.1f} MB" if s['max_swap_usage'] else "Swap data unavailable")
    print(f"Peak Memory Growth Rate:     {s['peak_growth_rate']:.2f} MB/s" if s['peak_growth_rate'] else "No growth data")

    if s["earliest_oom_prediction"]:
        print(f"Predicted Time to OOM:       {s['earliest_oom_prediction']:.1f} sec")
    else:
        print("Predicted Time to OOM:       No immediate risk")

    print("\n--- Scheduler Efficiency ---")
    print(f"Peak Voluntary Switch Rate:   {s['sched_peak_vol_rate']:.1f}/s" if s['sched_peak_vol_rate'] else "No scheduler data")
    print(f"Peak Involuntary Switch Rate: {s['sched_peak_invol_rate']:.1f}/s" if s['sched_peak_invol_rate'] else "")
    print(f"Maximum Thread Count:         {s['max_threads']}" if s['max_threads'] else "")

    print("\n--- Disk I/O Summary ---")
    print(f"Average Read Speed:         {s['avg_read_speed']:.2f} MB/s")
    print(f"Average Write Speed:        {s['avg_write_speed']:.2f} MB/s")
    print(f"Average I/O Wait:           {s['avg_io_wait']:.1f}%")
    print(f"Max I/O Wait:               {s['max_io_wait']:.1f}%")
    print(f"I/O Bottleneck Events:      {s['io_bottlenecks']}")

    print("Reasons:")
    for reason in s["io_reasons"]:
        print(f" - {reason}")


    print("==============================================\n")



if __name__ == "__main__":
    print(f"Resolved log path: {LOG_PATH}")
    metrics = load_metrics(LOG_PATH)
    summary = compute_summary(metrics)

    if summary is None:
        print("No valid metrics found in log.")
    else:
        print_summary(summary)

import time
import subprocess
import torch
from torch import nn, optim

def get_gpu_snapshot():
    """
    Return (gpu_util, mem_used_MB) for GPU0 using nvidia-smi.
    If anything fails, return (None, None).
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        line = result.stdout.strip().splitlines()[0]
        util_str, mem_str = [x.strip() for x in line.split(",")]
        return int(util_str), int(mem_str)
    except Exception:
        return None, None

device = "cuda" if torch.cuda.is_available() else "cpu"
print("Training on:", device)

x = torch.randn((5000, 512), device=device)
y = torch.randn((5000, 512), device=device)

model = nn.Sequential(
    nn.Linear(512, 1024),
    nn.ReLU(),
    nn.Linear(1024, 512)
).to(device)

opt = optim.Adam(model.parameters(), lr=1e-3)

num_params = sum(p.numel() for p in model.parameters())
print(f"Model parameters: {num_params}")

start_time = time.time()
peak_gpu_util = 0
peak_gpu_mem = 0
util_samples = []
mem_samples = []

for epoch in range(5):
    util, mem = get_gpu_snapshot()
    if util is not None:
        peak_gpu_util = max(peak_gpu_util, util)
        util_samples.append(util)
    if mem is not None:
        peak_gpu_mem = max(peak_gpu_mem, mem)
        mem_samples.append(mem)

    opt.zero_grad()
    out = model(x)
    loss = (out - y).pow(2).mean()
    loss.backward()
    opt.step()
    print(f"Epoch {epoch+1}, loss={loss.item():.5f}")

end_time = time.time()
total_time = end_time - start_time

avg_gpu_util = sum(util_samples) / len(util_samples) if util_samples else 0
avg_gpu_mem = sum(mem_samples) / len(mem_samples) if mem_samples else 0

print("\n=== Training Summary (MLinux) ===")
print(f"Total time: {total_time:.2f} seconds")
print(f"Model parameters: {num_params}")
if peak_gpu_util > 0:
    print(f"Peak GPU utilization: {peak_gpu_util}%")
    print(f"Average GPU utilization: {avg_gpu_util:.1f}%")
    print(f"Peak GPU memory: {peak_gpu_mem} MB")
    print(f"Average GPU memory: {avg_gpu_mem:.1f} MB")
else:
    print("GPU stats unavailable or GPU idle; training may have run on CPU.")
print("=================================")


#!/usr/bin/env bash
set -e

echo "[MLinux] Applying ML-focused kernel and CPU tuning..."

# Reduce swapping, better for large ML workloads
sudo sysctl -w vm.swappiness=10

# Reduce dirty page ratios to flush writes earlier
sudo sysctl -w vm.dirty_ratio=5
sudo sysctl -w vm.dirty_background_ratio=2

# Try to set CPU governor to performance (may not work in WSL, but valid on bare metal)
if [ -d /sys/devices/system/cpu/cpu0/cpufreq ]; then
  echo "[MLinux] Setting CPU frequency governor to performance..."
  for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance | sudo tee "$gov" >/dev/null || true
  done
else
  echo "[MLinux] CPU governor control not available (likely WSL) - skipping."
fi

echo "[MLinux] Done."

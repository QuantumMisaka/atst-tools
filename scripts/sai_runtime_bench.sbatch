#!/bin/bash
#SBATCH --job-name=atst-runtime-bench
#SBATCH --partition=4V100
#SBATCH --gres=gpu:2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=02:00:00
#
# Reference template for the P3 batch harness on SAI (GPU node tuning P5).
#
# Site facts (partition, QOS, module lines, CPU/memory shape) are NOT frozen
# here: fill them from $sai-user-guide at submission time and let the
# maintainer review the values before the first real run.
#
# Usage:
#   sbatch scripts/sai_runtime_bench.sbatch <work_dir> [manifest.json] [devices]
#
set -euo pipefail

WORK_DIR="${1:?usage: sbatch sai_runtime_bench.sbatch <work_dir> [manifest.json] [devices]}"
MANIFEST="${2:-${WORK_DIR}/cases.json}"
DEVICES="${3:-0,1}"
OUT_DIR="${OUT_DIR:-${WORK_DIR}/runs}"
SLOTS="${SLOTS:-1}"
CPU_BUDGET="${ATST_BATCH_CPU_BUDGET:-$(nproc)}"

source /etc/profile.d/modules.sh 2>/dev/null || true
# module load abacus/LTSv3.10.1-sm70-auto   # uncomment after site review

mkdir -p "${OUT_DIR}"
python -m atst_tools.bench.harness \
  --manifest "${MANIFEST}" \
  --out "${OUT_DIR}" \
  --devices "${DEVICES}" \
  --slots "${SLOTS}" \
  --cpu-budget "${CPU_BUDGET}"

#!/bin/bash
#SBATCH --job-name=atst-abacus-scan
#SBATCH --partition=4V100
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --time=01:00:00
#SBATCH --qos=rush-1o2gpu
#
# ABACUS inner-parallelism scan (mpi x omp) on one V100.  --ntasks=8 exposes the
# slots the inner `mpirun -np N` needs (PRRTE counts Slurm task slots).
set -euo pipefail

WORK="${WORK:-$HOME/atst-abacus-scan-20260921}"
ATST_ROOT="${ATST_SOURCE_ROOT:-$HOME/atst-p5-20260921/atst-tools}"
PYTHON_BIN="${PYTHON_BIN:-$HOME/atst-p5-20260921/venv/bin/python}"

set +u
source /opt/modules/lmod/9.2.4/init/bash
module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
module load deepmd-kit/3.2.0
module load abacus/LTSv3.10.1-sm70-auto
module list 2>&1 | sed -n '1,10p'
set -u

export PYTHONPATH="${ATST_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export ATST_SOURCE_ROOT="${ATST_ROOT}"
mkdir -p "${WORK}/runs"

echo "job=${SLURM_JOB_ID:-local} host=$(hostname -s) CVD=${CUDA_VISIBLE_DEVICES:-unset} np=$(nproc)"

"${PYTHON_BIN}" -m atst_tools.bench.batch_runner \
  --manifest "${WORK}/cases-abacus-scan.json" \
  --out "${WORK}/runs" \
  --devices "${CUDA_VISIBLE_DEVICES:-0}" \
  --slots 1 \
  --cpu-budget 8 \
  --threads 8

record_args=(
  --manifest "${WORK}/cases-abacus-scan.json"
  --out "${WORK}/runs/bench_record.json"
  --run-dir "${WORK}/runs"
  --note "abacus inner-parallelism scan: gpu=${CUDA_VISIBLE_DEVICES:-0}"
)
if [ -n "${SLURM_JOB_ID:-}" ]; then record_args+=(--job-id "${SLURM_JOB_ID}"); fi
if [ -n "${SLURM_JOB_PARTITION:-}" ]; then record_args+=(--partition "${SLURM_JOB_PARTITION}"); fi
if [ -n "${SLURM_JOB_QOS:-}" ]; then record_args+=(--qos "${SLURM_JOB_QOS}"); fi
"${PYTHON_BIN}" -m atst_tools.bench.record "${record_args[@]}"

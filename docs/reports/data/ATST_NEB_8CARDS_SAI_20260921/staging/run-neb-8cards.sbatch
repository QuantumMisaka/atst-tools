#!/bin/bash
#SBATCH --job-name=atst-neb-8cards
#SBATCH --partition=8V100V0
#SBATCH --gres=gpu:8
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --time=01:00:00
#SBATCH --qos=rush-gpu
#
# P5 remaining row: 8 NEB interior graphs across 8 V100 cards, plus the serial
# reference on the same chain (rush-gpu allows 16 GPUs per job).
set -euo pipefail

WORK="${WORK:-$HOME/atst-mainline-20260921/neb8}"
ATST_ROOT="${ATST_SOURCE_ROOT:-$HOME/atst-p5-20260921/atst-tools}"
PYTHON_BIN="${PYTHON_BIN:-$HOME/atst-p5-20260921/venv/bin/python}"

set +u
source /opt/modules/lmod/9.2.4/init/bash
module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
module load deepmd-kit/3.2.0
module list 2>&1 | sed -n '1,8p'
set -u
if ! "${PYTHON_BIN}" -c "from mpi4py import MPI" >/dev/null 2>&1; then
  echo "fatal: mpi4py cannot load an MPI library after the module loads" >&2
  exit 1
fi

export PYTHONPATH="${ATST_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export ATST_SOURCE_ROOT="${ATST_ROOT}"
mkdir -p "${WORK}/runs"

echo "job=${SLURM_JOB_ID:-local} host=$(hostname -s) CVD=${CUDA_VISIBLE_DEVICES:-unset} ntasks=${SLURM_NTASKS:-?}"

"${PYTHON_BIN}" -m atst_tools.bench.batch_runner \
  --manifest "${WORK}/cases-neb-8cards.json" \
  --out "${WORK}/runs" \
  --devices "${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}" \
  --slots 1 \
  --cpu-budget 64 \
  --threads 1

record_args=(--manifest "${WORK}/cases-neb-8cards.json" --out "${WORK}/runs/bench_record.json" --run-dir "${WORK}/runs"
             --note "neb 8 graphs / 8 cards: gpu=${CUDA_VISIBLE_DEVICES:-unset}")
if [ -n "${SLURM_JOB_ID:-}" ]; then record_args+=(--job-id "${SLURM_JOB_ID}"); fi
if [ -n "${SLURM_JOB_PARTITION:-}" ]; then record_args+=(--partition "${SLURM_JOB_PARTITION}"); fi
if [ -n "${SLURM_JOB_QOS:-}" ]; then record_args+=(--qos "${SLURM_JOB_QOS}"); fi
"${PYTHON_BIN}" -m atst_tools.bench.record "${record_args[@]}"

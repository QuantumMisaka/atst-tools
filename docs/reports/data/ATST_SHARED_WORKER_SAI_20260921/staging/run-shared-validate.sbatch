#!/bin/bash
#SBATCH --job-name=atst-shared-validate
#SBATCH --partition=4V100
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=01:00:00
#SBATCH --qos=rush-1o2gpu
#
# Shared-worker site validation: same 3-case CCQN batch in per-case and shared
# mode, then the fail-closed guard case in shared mode.
set -euo pipefail

WORK="${WORK:-$HOME/atst-mainline-20260921/shared}"
ATST_ROOT="${ATST_SOURCE_ROOT:-$HOME/atst-p5-20260921/atst-tools}"
PYTHON_BIN="${PYTHON_BIN:-$HOME/atst-p5-20260921/venv/bin/python}"

set +u
source /opt/modules/lmod/9.2.4/init/bash
module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
module load deepmd-kit/3.2.0
set -u

export PYTHONPATH="${ATST_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export ATST_SOURCE_ROOT="${ATST_ROOT}"
mkdir -p "${WORK}/runs-per-case" "${WORK}/runs-shared" "${WORK}/runs-guard"

echo "job=${SLURM_JOB_ID:-local} host=$(hostname -s) CVD=${CUDA_VISIBLE_DEVICES:-unset} np=$(nproc)"

"${PYTHON_BIN}" -m atst_tools.bench.batch_runner --manifest "${WORK}/cases-per-case.json" \
  --out "${WORK}/runs-per-case" --devices "${CUDA_VISIBLE_DEVICES:-0}" --slots 1 --cpu-budget 8 --threads 4
"${PYTHON_BIN}" -m atst_tools.bench.batch_runner --manifest "${WORK}/cases-shared.json" \
  --out "${WORK}/runs-shared" --devices "${CUDA_VISIBLE_DEVICES:-0}" --slots 1 --cpu-budget 8 --threads 4 --share-worker
set +e
"${PYTHON_BIN}" -m atst_tools.bench.batch_runner --manifest "${WORK}/cases-guard.json" \
  --out "${WORK}/runs-guard" --devices "${CUDA_VISIBLE_DEVICES:-0}" --slots 1 --cpu-budget 8 --threads 4 --share-worker
guard_rc=$?
set -e
echo "guard_run_exit=${guard_rc} (a non-zero per-case failure is expected and recorded)"
echo "DONE"

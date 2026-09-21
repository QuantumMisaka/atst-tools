#!/bin/bash
#SBATCH --job-name=atst-cp-runtime
#SBATCH --partition=4V100
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=02:00:00
#SBATCH --qos=rush-1o2gpu
#
# Constant-potential x runtime joint acceptance (GPU node tuning follow-up).
#
# Runs the two CP cases exactly once each through the batch harness (no sweep
# pass: the YAML runtime.telemetry section already requests the per-case
# sidecars), then writes the benchmark record.  A trailing negative check
# proves the on-site allocation refusal with runtime.devices: [1] inside a
# single-GPU allocation.
set -euo pipefail

WORK="${1:-$HOME/atst-cp-runtime-20260921}"
ATST_ROOT="${ATST_SOURCE_ROOT:-$HOME/atst-p5-20260921/atst-tools}"
PYTHON_BIN="${PYTHON_BIN:-$HOME/atst-p5-20260921/venv/bin/python}"
MANIFEST="${MANIFEST:-$WORK/cases-cp.json}"
OUT_DIR="$WORK/runs"
CPU_BUDGET="${ATST_BATCH_CPU_BUDGET:-8}"   # site policy: 1 GPU comes with 8 CPUs

if [ -f /opt/modules/lmod/9.2.4/init/bash ]; then
  # Lmod dereferences variables while sourcing; nounset must be off here.
  set +u
  source /opt/modules/lmod/9.2.4/init/bash
  module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
  module load deepmd-kit/3.2.0
  module load abacus/LTSv3.10.1-sm70-auto
  module list 2>&1 | sed -n '1,8p'
  set -u
  if ! "${PYTHON_BIN}" -c "from mpi4py import MPI" >/dev/null 2>&1; then
    echo "fatal: mpi4py cannot load an MPI library after the module loads" >&2
    exit 1
  fi
else
  source /etc/profile.d/modules.sh 2>/dev/null || true
fi

export PYTHONPATH="${ATST_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export ATST_SOURCE_ROOT="${ATST_ROOT}"
mkdir -p "${OUT_DIR}"

echo "job=${SLURM_JOB_ID:-local} host=$(hostname) node=$(hostname -s)"
echo "CVD=${CUDA_VISIBLE_DEVICES:-unset} ntasks=${SLURM_NTASKS:-?} cpus_per_task=${SLURM_CPUS_PER_TASK:-?}"
echo "atst_src=${ATST_ROOT} python=${PYTHON_BIN}"

"${PYTHON_BIN}" -m atst_tools.bench.harness \
  --manifest "${MANIFEST}" \
  --out "${OUT_DIR}" \
  --devices "${CUDA_VISIBLE_DEVICES:-0}" \
  --slots 1 \
  --cpu-budget "${CPU_BUDGET}" \
  --threads "${CPU_BUDGET}"

record_args=(
  --manifest "${MANIFEST}"
  --out "${OUT_DIR}/bench_record.json"
  --run-dir "${OUT_DIR}"
  --note "cp-runtime joint acceptance: gpu=${CUDA_VISIBLE_DEVICES:-0} slots=1 threads=${CPU_BUDGET}"
)
if [ -n "${SLURM_JOB_ID:-}" ]; then
  record_args+=(--job-id "${SLURM_JOB_ID}")
fi
if [ -n "${SLURM_JOB_PARTITION:-}" ]; then
  record_args+=(--partition "${SLURM_JOB_PARTITION}")
fi
if [ -n "${SLURM_JOB_QOS:-}" ]; then
  record_args+=(--qos "${SLURM_JOB_QOS}")
fi
"${PYTHON_BIN}" -m atst_tools.bench.record "${record_args[@]}"

# Negative check: an out-of-allocation device index must be refused before any
# ABACUS process starts.  Expected: exit status non-zero, refusal in stderr.
NEGATIVE_DIR="${WORK}/cases/cp-gate-single"
echo "--- negative check: runtime.devices [1] in a 1-GPU allocation ---"
if (cd "${NEGATIVE_DIR}" && "${PYTHON_BIN}" -m atst_tools.scripts.cli run --dry-run config.negative.yaml); then
  echo "NEGATIVE CHECK FAILED: the out-of-allocation device was accepted" >&2
  exit 2
else
  echo "negative check passed: the launcher refused the out-of-allocation device"
fi

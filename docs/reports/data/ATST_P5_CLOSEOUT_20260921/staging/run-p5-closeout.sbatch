#!/bin/bash
#SBATCH --job-name=atst-p5-closeout
#SBATCH --partition=4V100
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=8
# The site's OpenMPI counts Slurm task slots: the ABACUS example configs ask
# for `mpirun -np 4` internally, so the allocation must expose >= 4 slots
# (PRRTE otherwise refuses with "not enough slots available").
#SBATCH --time=02:00:00
#SBATCH --qos=rush-1o2gpu
#
# P5 closeout on one V100:
#   (a) post-fix ABACUS relax baseline - the example config as shipped (explicit
#       omp: 1) against the same case without omp, where the manifest budget (2)
#       must arrive through the harness marker;
#   (b) the remaining pressure row - 8 image-parallel DP ranks on ONE card,
#       with the serial reference on the same chain.
#
# Site policy: CPUs follow the GPU count, so no --cpus-per-task here.
set -euo pipefail

WORK="${WORK:-$HOME/atst-p5-closeout-20260921}"
ATST_ROOT="${ATST_SOURCE_ROOT:-$HOME/atst-p5-20260921/atst-tools}"
PYTHON_BIN="${PYTHON_BIN:-$HOME/atst-p5-20260921/venv/bin/python}"
CPU_BUDGET="${ATST_BATCH_CPU_BUDGET:-8}"

if [ -f /opt/modules/lmod/9.2.4/init/bash ]; then
  set +u
  source /opt/modules/lmod/9.2.4/init/bash
  module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
  module load deepmd-kit/3.2.0
  module load abacus/LTSv3.10.1-sm70-auto
  module list 2>&1 | sed -n '1,10p'
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

echo "job=${SLURM_JOB_ID:-local} host=$(hostname -s) CVD=${CUDA_VISIBLE_DEVICES:-unset} np=$(nproc)"
echo "atst_src=${ATST_ROOT} python=${PYTHON_BIN}"

run_group() {
  manifest="$1"; outdir="$2"; threads="$3"
  mkdir -p "${outdir}"
  "${PYTHON_BIN}" -m atst_tools.bench.harness \
    --manifest "${manifest}" \
    --out "${outdir}" \
    --devices "${CUDA_VISIBLE_DEVICES:-0}" \
    --slots 1 \
    --cpu-budget "${CPU_BUDGET}" \
    --threads "${threads}"
  record_args=(
    --manifest "${manifest}"
    --out "${outdir}/bench_record.json"
    --run-dir "${outdir}"
    --note "p5-closeout: gpu=${CUDA_VISIBLE_DEVICES:-0} slots=1 cpu_budget=${CPU_BUDGET}"
  )
  if [ -n "${SLURM_JOB_ID:-}" ]; then record_args+=(--job-id "${SLURM_JOB_ID}"); fi
  if [ -n "${SLURM_JOB_PARTITION:-}" ]; then record_args+=(--partition "${SLURM_JOB_PARTITION}"); fi
  if [ -n "${SLURM_JOB_QOS:-}" ]; then record_args+=(--qos "${SLURM_JOB_QOS}"); fi
  "${PYTHON_BIN}" -m atst_tools.bench.record "${record_args[@]}"
}

run_group "${WORK}/cases-abacus-threads.json" "${WORK}/runs-abacus" 2
run_group "${WORK}/cases-neb-8rank-1card.json" "${WORK}/runs-neb8" 1

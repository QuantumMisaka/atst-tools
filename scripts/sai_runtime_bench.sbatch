#!/bin/bash
#SBATCH --job-name=atst-runtime-bench
#SBATCH --partition=4V100
#SBATCH --gres=gpu:2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=02:00:00
# #SBATCH --qos=rush-1o2gpu   # site: 1-day wall limit, <=2 GPUs; pick at submission
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
# Environment overrides:
#   SLOTS=1,2,3        per-device concurrency variants for the sweep
#   REPEATS=3          alternating repeat count per variant
#   EVIDENCE_PASS=1    additionally run one single-repeat pass with per-case
#                      runtime_evidence.json sidecars (timing pass keeps them
#                      off so samplers cannot perturb makespan)
#   MODEL=/path/model.pt  fixture hashed into the benchmark record
#   DRY_RUN=1          print the commands instead of executing them
#
set -euo pipefail

WORK_DIR="${1:?usage: sbatch sai_runtime_bench.sbatch <work_dir> [manifest.json] [devices]}"
MANIFEST="${2:-${WORK_DIR}/cases.json}"
DEVICES="${3:-0,1}"
OUT_DIR="${OUT_DIR:-${WORK_DIR}/runs}"
SLOTS="${SLOTS:-1,2,3}"
REPEATS="${REPEATS:-3}"
CPU_BUDGET="${ATST_BATCH_CPU_BUDGET:-$(nproc)}"
DRY_RUN="${DRY_RUN:-0}"
PYTHON_BIN="${PYTHON_BIN:-python}"

# Site facts from the 2026-09-21 read-only reconnaissance (plan P5 prep):
# Lmod lives under /opt/modules/lmod/9.2.4 with modulefiles in
# /opt/modules/modulefiles/{devtools,apps}; there is no system conda. The DP
# runtime must be DPA4/SeZM-capable (deepmd-kit/3.2.0; 3.1.2 fails with
# "Unknown model type: dpa4") and needs an MPI module so mpi4py finds libmpi.
# The maintainer still reviews these lines before the first real run.
source /opt/modules/lmod/9.2.4/init/bash 2>/dev/null || source /etc/profile.d/modules.sh 2>/dev/null || true
module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps 2>/dev/null || true
module load deepmd-kit/3.2.0 2>/dev/null || true
module load openmpi/5.0.8-nvhpc25.7-gnu-auto 2>/dev/null || true
# module load abacus/LTSv3.10.1-sm70-auto   # ABACUS channel only; loads the same OpenMPI

mkdir -p "${OUT_DIR}"

run() {
  if [ "${DRY_RUN}" = "1" ]; then
    printf '+ %s\n' "$*"
  else
    "$@"
  fi
}

# 1) Timing matrix: alternating repeats, no per-case sidecars.
run "${PYTHON_BIN}" -m atst_tools.bench.sweep \
  --manifest "${MANIFEST}" \
  --out "${OUT_DIR}/sweep" \
  --devices "${DEVICES}" \
  --slots "${SLOTS}" \
  --repeats "${REPEATS}" \
  --cpu-budget "${CPU_BUDGET}"

# 2) Evidence pass: one repeat with per-case runtime_evidence.json sidecars.
if [ "${EVIDENCE_PASS:-1}" = "1" ]; then
  run "${PYTHON_BIN}" -m atst_tools.bench.sweep \
    --manifest "${MANIFEST}" \
    --out "${OUT_DIR}/evidence" \
    --devices "${DEVICES}" \
    --slots "${SLOTS%%,*}" \
    --repeats 1 \
    --case-telemetry \
    --cpu-budget "${CPU_BUDGET}"
fi

# 3) Self-describing record (operator fields stay null until filled in).
record_args=(
  --manifest "${MANIFEST}"
  --out "${OUT_DIR}/bench_record.json"
  --run-dir "${OUT_DIR}/sweep"
  --note "sai_runtime_bench: devices=${DEVICES} slots=${SLOTS} repeats=${REPEATS}"
)
if [ "${EVIDENCE_PASS:-1}" = "1" ]; then
  record_args+=(--run-dir "${OUT_DIR}/evidence")
fi
if [ -n "${MODEL:-}" ]; then
  record_args+=(--fixture "${MODEL}")
fi
if [ -n "${SLURM_JOB_ID:-}" ]; then
  record_args+=(--job-id "${SLURM_JOB_ID}")
fi
if [ -n "${SLURM_JOB_PARTITION:-}" ]; then
  record_args+=(--partition "${SLURM_JOB_PARTITION}")
fi
if [ -n "${SLURM_JOB_QOS:-}" ]; then
  record_args+=(--qos "${SLURM_JOB_QOS}")
fi
run "${PYTHON_BIN}" -m atst_tools.bench.record "${record_args[@]}"

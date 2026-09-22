#!/bin/bash
#SBATCH --job-name=atst-runtime-bench
#SBATCH --partition=4V100
#SBATCH --gres=gpu:2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=02:00:00
# #SBATCH --qos=rush-1o2gpu   # site: 1-day wall limit, <=2 GPUs; pick at submission
#
# Reference template for the P3 batch runner + sweep + record on SAI (GPU node tuning P5).
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
#   MODEL=/path/model.pt   DP model, recorded as the `dp_model` fixture of the
#                          benchmark record
#   ABACUS_INPUTS=/path    ABACUS input file or directory (hashed as a tree when
#                          it is a directory), recorded as the `abacus_inputs`
#                          fixture so the ABACUS channel is not recorded with
#                          the DP model hash
#   DRY_RUN=1          print the commands instead of executing them
#   ABACUS_MODULE=1    additionally load abacus/LTSv3.10.1-sm70-auto (ABACUS cases)
#
# Site note (2026-09-21): a Slurm allocation grants one task slot per --ntasks,
# and the site's OpenMPI counts those slots; case launchers and the ABACUS
# calculator's inner `mpirun -np N` therefore need --ntasks >= N (or
# --oversubscribe) on the sbatch line.
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
# SAI has python3 but no bare python; prefer an explicit interpreter (venv).
PYTHON_BIN="${PYTHON_BIN:-$(command -v python || command -v python3)}"

# Optional: run from a source checkout so the benchmark record carries a real
# git revision instead of null (a wheel install records no revision).
if [ -n "${ATST_SOURCE_ROOT:-}" ] && [ -d "${ATST_SOURCE_ROOT}/src/atst_tools" ]; then
  export PYTHONPATH="${ATST_SOURCE_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
fi

# Site facts from the 2026-09-21 reconnaissance (plan P5 prep): Lmod lives under
# /opt/modules/lmod/9.2.4 with modulefiles in /opt/modules/modulefiles/{devtools,apps};
# there is no system conda. The DP runtime must be DPA4/SeZM-capable
# (deepmd-kit/3.2.0; 3.1.2 fails with "Unknown model type: dpa4"), and that
# module chain brings the OpenMPI the venv's mpi4py links against.
#
# Lmod dereferences variables such as LD_LIBRARY_PATH while sourcing and while
# applying module loads, so nounset must be off for this block (the site's SIF
# build scripts use the same idiom). Measured on 4v100 nodes: with `set -u`
# active the module loads silently do nothing, and every case then fails with
# "cannot load MPI library" before any science runs.
if [ -f /opt/modules/lmod/9.2.4/init/bash ]; then
  set +u
  source /opt/modules/lmod/9.2.4/init/bash
  module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
  module load deepmd-kit/3.2.0
  if [ "${ABACUS_MODULE:-0}" = "1" ]; then
    module load abacus/LTSv3.10.1-sm70-auto
  fi
  module list 2>&1 | sed -n '1,8p'
  set -u
  if ! "${PYTHON_BIN}" -c "from mpi4py import MPI" >/dev/null 2>&1; then
    echo "fatal: mpi4py cannot load an MPI library after 'module load deepmd-kit/3.2.0'; see the module list above" >&2
    exit 1
  fi
else
  source /etc/profile.d/modules.sh 2>/dev/null || true
fi
# module load abacus/LTSv3.10.1-sm70-auto   # ABACUS channel only; brings openmpi/5.0.8

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
#
# Fixtures are labeled per benchmark channel: `MODEL` is the DP model and
# `ABACUS_INPUTS` the ABACUS channel's inputs. The labels provided on this run
# go into the note, so a record without a channel fixture is distinguishable
# from one whose fixture argument was simply not passed.
labeled_fixtures=()
if [ -n "${MODEL:-}" ]; then
  labeled_fixtures+=("dp_model=${MODEL}")
fi
if [ -n "${ABACUS_INPUTS:-}" ]; then
  labeled_fixtures+=("abacus_inputs=${ABACUS_INPUTS}")
fi
FIXTURE_LABELS="none"
if [ -n "${labeled_fixtures[*]:-}" ]; then
  FIXTURE_LABELS=""
  for entry in "${labeled_fixtures[@]}"; do
    FIXTURE_LABELS="${FIXTURE_LABELS:+${FIXTURE_LABELS},}${entry%%=*}"
  done
fi

record_args=(
  --manifest "${MANIFEST}"
  --out "${OUT_DIR}/bench_record.json"
  --run-dir "${OUT_DIR}/sweep"
  --note "sai_runtime_bench: devices=${DEVICES} slots=${SLOTS} repeats=${REPEATS} fixtures=${FIXTURE_LABELS}"
)
if [ "${EVIDENCE_PASS:-1}" = "1" ]; then
  record_args+=(--run-dir "${OUT_DIR}/evidence")
fi
if [ "${#labeled_fixtures[@]}" -gt 0 ]; then
  for entry in "${labeled_fixtures[@]}"; do
    record_args+=(--fixture-labeled "${entry}")
  done
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

#!/bin/bash
#SBATCH --job-name=atst-pt-mps-verify
#SBATCH --partition=4V100
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:30:00
#SBATCH --qos=rush-1o2gpu
#
# Site re-verification (2026-09-22, authorized): the DeepMD PT thread keys and
# the MPS attribution facts on SAI 4V100.  One DP relax run with an explicit
# thread budget and telemetry; every assertion reads the sidecar this run wrote.
set -euo pipefail

WORK="${WORK:-$HOME/atst-p2-closeout-20260922}"
ATST_ROOT="$WORK/atst-tools-pt"
PYTHON_BIN="${PYTHON_BIN:-$HOME/atst-p5-20260921/venv/bin/python}"
DEV="${CUDA_VISIBLE_DEVICES:-0}"

if [ -f /opt/modules/lmod/9.2.4/init/bash ]; then
  set +u
  source /opt/modules/lmod/9.2.4/init/bash
  module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
  module load deepmd-kit/3.2.0
  module list 2>&1 | sed -n '1,6p'
  set -u
else
  source /etc/profile.d/modules.sh 2>/dev/null || true
fi

export PYTHONPATH="${ATST_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export ATST_SOURCE_ROOT="${ATST_ROOT}"
RUN="$WORK/pt-mps-verify"
mkdir -p "$RUN"
cd "$RUN"

echo "job=${SLURM_JOB_ID:-local} node=$(hostname -s) dev=${DEV} src=${ATST_ROOT}"
echo "mps_daemon_lines_seen_by_shell=$(ps -ef 2>/dev/null | grep -c '[n]vidia-cuda-mps' || true)"
ps -ef 2>/dev/null | grep "[n]vidia-cuda-mps" | head -3 || true

"${PYTHON_BIN}" -m atst_tools.scripts.cli run \
  --devices "${DEV}" --threads 4 --telemetry "$WORK/configs/dp_relax_restart.yaml"

echo "== PT thread budget + MPS assertions =="
"${PYTHON_BIN}" - "$RUN" <<'PY'
import json, pathlib, sys

run = pathlib.Path(sys.argv[1])
payload = json.loads((run / "runtime_evidence.json").read_text())
environment = payload.get("environment") or {}
threads = environment.get("threads") or {}

print("threads:", json.dumps(threads, sort_keys=True))
print("threads_source:", environment.get("threads_source"))
assert threads.get("DP_INTRA_OP_PARALLELISM_THREADS") == "4", threads
assert threads.get("DP_INTER_OP_PARALLELISM_THREADS") == "4", threads
assert threads.get("OMP_NUM_THREADS") == "4", threads
assert environment.get("threads_source") == "explicit", environment.get("threads_source")

sampler = (payload.get("telemetry") or {}).get("sampler") or {}
mps = sampler.get("mps") or {}
print("mps:", json.dumps(mps))
# Semantic contract: true needs positive evidence, false needs a completed
# process-table probe (a real negative, never a guess), null needs a reason.
if mps.get("detected") is True:
    assert mps.get("evidence"), mps
elif mps.get("detected") is False:
    probes = mps.get("probes") or {}
    assert any(str(v).startswith(("ok", "partial")) for v in probes.values()), mps
else:
    assert mps.get("reason"), mps

samples = sampler.get("samples") or []
processes = (samples[-1].get("processes") if samples else {}) or {}
print("compute_processes:", processes.get("status"), "|", processes.get("reason"))
if processes.get("status") == "unavailable":
    assert "MPS" in (processes.get("reason") or ""), processes

self_reported = payload.get("self_reported") or {}
print("self_reported:", json.dumps(self_reported)[:280])
assert "self_reported" in payload, sorted(payload)
if self_reported.get("status") == "observed":
    values = [d.get("max_memory_allocated_mib") for d in self_reported.get("devices") or []]
    print("max_memory_allocated_mib:", values)
    assert any(v and v > 0 for v in values), values
else:
    assert self_reported.get("reason"), self_reported

print("PT-THREAD + MPS ASSERTIONS OK")
PY

echo "DONE"

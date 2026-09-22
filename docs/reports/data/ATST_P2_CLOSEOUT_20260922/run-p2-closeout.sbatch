#!/bin/bash
#SBATCH --job-name=atst-p2-closeout
#SBATCH --partition=4V100
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=01:00:00
#SBATCH --qos=rush-1o2gpu
#
# GPU tuning P2 closeout on SAI 4V100 (authorized 2026-09-22):
#   1. MPS probe (read-only): does the node run MPS servers, and what does the
#      host sampler report for compute processes there
#   2. read-only model sharing across one shared worker + per-attempt caches
#   3. per-attempt cache and evidence attribution (ATST_ATTEMPT 1/2)
#   4. same-workdir restart regression (two batches over one workdir)
# Assertions are explicit; any failure exits non-zero.
set -euo pipefail

WORK="${WORK:-$HOME/atst-p2-closeout-20260922}"
ATST_ROOT="$WORK/atst-tools"
PYTHON_BIN="${PYTHON_BIN:-$HOME/atst-p5-20260921/venv/bin/python}"
CPU_BUDGET="${ATST_BATCH_CPU_BUDGET:-8}"
DEV="${CUDA_VISIBLE_DEVICES:-0}"

if [ -f /opt/modules/lmod/9.2.4/init/bash ]; then
  # Lmod dereferences variables while sourcing; nounset must stay off here.
  set +u
  source /opt/modules/lmod/9.2.4/init/bash
  module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
  module load deepmd-kit/3.2.0
  module list 2>&1 | sed -n '1,8p'
  set -u
else
  source /etc/profile.d/modules.sh 2>/dev/null || true
fi

export PYTHONPATH="${ATST_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export ATST_SOURCE_ROOT="${ATST_ROOT}"
export ATST_BATCH_CPU_BUDGET="${CPU_BUDGET}"

echo "job=${SLURM_JOB_ID:-local} node=$(hostname -s) devices=${DEV} cpus=${SLURM_CPUS_PER_TASK:-?}"
echo "atst_src=${ATST_ROOT} python=$("${PYTHON_BIN}" -V 2>&1)"
mkdir -p "$WORK/runs"

echo "== 1. MPS probe (read-only) =="
nvidia-smi -q 2>&1 | grep -i -A6 "MPS" | head -24 || echo "no MPS block in nvidia-smi -q"
ls -ld /tmp/nvidia-mps 2>/dev/null || echo "no /tmp/nvidia-mps (no MPS client pipe directory here)"
echo "mps_server_processes=$(ps -ef 2>/dev/null | grep -c '[n]vidia-cuda-mps' || true)"
ps -ef 2>/dev/null | grep "[n]vidia-cuda-mps" | head -4 || true
echo "-- compute-apps view during this probe:"
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>&1 | head -5

echo "== 2. read-only model sharing =="
mkdir -p "$WORK/models-ro"
if [ ! -f "$WORK/models-ro/model.ckpt-100000.pt" ]; then
  cp "$HOME/atst-p5-20260921/models/model.ckpt-100000.pt" "$WORK/models-ro/model.ckpt-100000.pt"
fi
chmod 444 "$WORK/models-ro/model.ckpt-100000.pt"
chmod 555 "$WORK/models-ro"
ls -l "$WORK/models-ro"
model_before=$(find "$WORK/models-ro" -type f -printf '%P %s %T@\n' | sort | sha256sum | cut -d' ' -f1)
echo "model_dir_digest_before=${model_before}"

"${PYTHON_BIN}" -m atst_tools.bench.batch_runner \
  --manifest "$WORK/cases/cases-dp-share.json" \
  --out "$WORK/runs/share-second" \
  --devices "${DEV}" --slots 1 --cpu-budget "${CPU_BUDGET}" --threads "${CPU_BUDGET}" \
  --share-worker

model_after=$(find "$WORK/models-ro" -type f -printf '%P %s %T@\n' | sort | sha256sum | cut -d' ' -f1)
echo "model_dir_digest_after=${model_after}"
if [ "${model_before}" != "${model_after}" ]; then
  echo "FAIL: the read-only model directory changed during the batch"
  exit 1
fi
echo "OK: read-only model directory unchanged (bytes and mtimes)"

echo "-- share summary:"
sed -n '1,20p' "$WORK/runs/share-second/batch_summary.json"
echo "-- cache directories under the batch tree:"
find "$WORK/runs/share-second" -maxdepth 6 -name '.atst_cache' -print 2>/dev/null | head -5
find "$WORK/runs/share-second" -maxdepth 7 -path '*.atst_cache/*' -print 2>/dev/null | head -8

echo "-- sidecar facts (share cases):"
"${PYTHON_BIN}" - "$WORK" <<'PY'
import json, pathlib, sys

work = pathlib.Path(sys.argv[1])
for case in ("ro-a", "ro-b"):
    sidecar = work / "runs/share-second/work" / case / "runtime_evidence.json"
    if not sidecar.is_file():
        print(f"{case}: no sidecar at {sidecar}")
        continue
    data = json.loads(sidecar.read_text())
    environment = data.get("environment") or {}
    sampler = (data.get("telemetry") or {}).get("sampler") or {}
    samples = sampler.get("samples") or []
    processes = (samples[-1].get("processes") if samples else {}) or {}
    statuses = {}
    for sample in samples:
        sample_processes = sample.get("processes") or {}
        key = sample_processes.get("status")
        statuses[key] = statuses.get(key, 0) + 1
    print(f"{case}: attempt={data.get('attempt')} status={data.get('status')} "
          f"threads={environment.get('threads')} threads_source={environment.get('threads_source')}")
    print(f"  counters={data.get('counters')} gauges={data.get('gauges')}")
    print(f"  memory_peak_mib={sampler.get('memory_peak_mib')} samples={sampler.get('sample_count')}")
    print(f"  compute_process_statuses_across_samples={statuses}")
    print(f"  compute_processes: status={processes.get('status')!r} reason={processes.get('reason')!r} "
          f"count={len(processes.get('processes') or [])}")
PY

echo "-- shared calculator reuse across the two cases (read-only model sharing):"
"${PYTHON_BIN}" - "$WORK" <<'PY'
import json, pathlib, sys

work = pathlib.Path(sys.argv[1])
reused = 0
for case in ("ro-a", "ro-b"):
    sidecar = work / "runs/share-second/work" / case / "runtime_evidence.json"
    if not sidecar.is_file():
        continue
    counters = json.loads(sidecar.read_text()).get("counters") or {}
    reused += counters.get("dp.calculator_reused") or 0
print(f"dp.calculator_reused total across cases = {reused}")
assert reused >= 1, "no reused DP calculator instance was recorded"
print("SHARED-INSTANCE ASSERTION OK (one DP calculator served both cases)")
PY

echo "== 3. per-attempt cache and evidence attribution (ATST_ATTEMPT 1/2) =="
ATTN="$WORK/work/attn"
mkdir -p "$ATTN"
cp -f "$WORK/configs/dp_relax_restart.yaml" "$ATTN/config.yaml"
cd "$ATTN"
for n in 1 2; do
  echo "-- attempt ${n}"
  ATST_ATTEMPT="$n" "${PYTHON_BIN}" -m atst_tools.scripts.cli run \
    --devices "${DEV}" --threads 4 --telemetry "$ATTN/config.yaml"
  cp "$ATTN/runtime_evidence.json" "$WORK/runs/attempt-${n}-evidence.json"
  cp "$ATTN/relax_restart.traj" "$WORK/runs/attempt-${n}.traj"
done
cd "$WORK"

echo "== 3b. attempt assertions =="
"${PYTHON_BIN}" - "$WORK" <<'PY'
import json, pathlib, sys

work = pathlib.Path(sys.argv[1])
cache_root = work / "work/attn/.atst_cache"
e1 = json.loads((work / "runs/attempt-1-evidence.json").read_text())
e2 = json.loads((work / "runs/attempt-2-evidence.json").read_text())

assert e1["attempt"] == 1, e1["attempt"]
assert e2["attempt"] == 2, e2["attempt"]

caches = sorted(entry.name for entry in cache_root.iterdir())
assert caches == ["attempt-1", "attempt-2"], caches
entries = {name: sorted(entry.name for entry in (cache_root / name).iterdir()) for name in caches}
print("cache entries:", entries)

for index, evidence in ((1, e1), (2, e2)):
    counters = evidence.get("counters") or {}
    environment = evidence.get("environment") or {}
    print(f"attempt {index}: counters={counters} gauges={evidence.get('gauges')} "
          f"threads_source={environment.get('threads_source')}")
    assert counters.get("dp.calculator_built") is not None, counters
    assert (counters.get("dp.force_calls") or 0) > 0, counters
    assert evidence.get("phases"), evidence.keys()

print("ATTEMPT ASSERTIONS OK (cache directory and evidence carry the same attempt)")
PY

echo "== 4. restart regression: same absolute workdir, two batches =="
for phase in first second; do
  out="$WORK/runs/restart/$phase"
  mkdir -p "$out"
  echo "-- run ${phase}"
  "${PYTHON_BIN}" -m atst_tools.bench.batch_runner \
    --manifest "$WORK/cases/cases-restart.json" \
    --out "$out" \
    --devices "${DEV}" --slots 1 --cpu-budget "${CPU_BUDGET}" --threads "${CPU_BUDGET}" \
    --share-worker
  cp "$WORK/work/restart/relax_restart.traj" "$out/relax_restart.traj"
  echo "-- ${phase} summary:"
  sed -n '/"cases_total"/,+6p' "$out/batch_summary.json"
done

echo "== 4b. restart assertions =="
"${PYTHON_BIN}" - "$WORK" <<'PY'
import json, pathlib, sys
from ase.io import read

work = pathlib.Path(sys.argv[1])
first, second = work / "runs/restart/first", work / "runs/restart/second"

for phase, out in (("first", first), ("second", second)):
    summary = json.loads((out / "batch_summary.json").read_text())
    assert summary["succeeded"] == 1, (phase, summary["succeeded"])
    assert summary["failed"] == 0, (phase, summary["failed"])
    report = json.loads((out / "restart/case_report.json").read_text())
    assert report["status"] == "succeeded", (phase, report["status"])
    print(f"{phase}: attempt={report['attempt']} status={report['status']} wall_s={report['wall_s']}")

e1 = read(first / "relax_restart.traj", index=-1).get_potential_energy()
e2 = read(second / "relax_restart.traj", index=-1).get_potential_energy()
delta = abs(e1 - e2)
print(f"first_energy={e1!r} second_energy={e2!r} delta={delta!r}")
# Tolerance: recomputing the same structure twice on the GPU differs at the
# 1e-6 eV level (observed 1.1e-6 eV); that is numerical noise, not state reuse.
assert delta < 1e-3, (e1, e2)

case_dir = work / "work/restart"
# The shared-worker batch uses its own output directory as the workflow
# directory, so the per-attempt cache lives there rather than in the case
# directory; both are printed so the layout is explicit in the evidence.
batch_cache = work / "runs/restart/second/.atst_cache"
batch_caches = sorted(p.name for p in batch_cache.iterdir()) if batch_cache.is_dir() else []
case_caches = sorted(p.name for p in (case_dir / ".atst_cache").iterdir()) if (case_dir / ".atst_cache").is_dir() else []
print("batch_cache_dirs_after_second_run:", batch_caches)
print("case_cache_dirs_after_second_run:", case_caches)
assert batch_caches == ["attempt-1"], batch_caches
assert case_caches == [], case_caches
for entry in sorted(batch_cache.iterdir()):
    print(f"  batch cache {entry.name}: {sorted(p.name for p in entry.iterdir())}")

for artefact in ("atst_api_result.json", "atst_artifacts.json", "runtime_evidence.json",
                 "relax_restart.traj", "relax.traj", "relax_run"):
    print(f"case_dir/{artefact}: {'present' if (case_dir / artefact).exists() else 'absent'}")

print("RESTART ASSERTIONS OK (equivalent recompute, one attempt cache directory, own artifacts)")
PY

echo "DONE"

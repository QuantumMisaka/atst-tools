#!/bin/bash
#SBATCH --job-name=atst-record-channels
#SBATCH --partition=4V100
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --time=01:00:00
#SBATCH --qos=rush-1o2gpu
#
# Record-channel closeout on SAI 4V100: run the repository's one-shot site
# entry point once per channel and assert that each benchmark record carries
# its own channel fixture - the DP model for DP cases, the ABACUS inputs for
# ABACUS cases - instead of the DP model hash for everything.
set -euo pipefail

WORK="${WORK:-$HOME/atst-p2-closeout-20260922}"
ATST_ROOT="$WORK/atst-tools"
PYTHON_BIN="${PYTHON_BIN:-$HOME/atst-p5-20260921/venv/bin/python}"
DEV="${CUDA_VISIBLE_DEVICES:-0}"
export PYTHONPATH="${ATST_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export ATST_SOURCE_ROOT="${ATST_ROOT}"
export PYTHON_BIN
export ATST_BATCH_CPU_BUDGET="${ATST_BATCH_CPU_BUDGET:-8}"

if [ -f /opt/modules/lmod/9.2.4/init/bash ]; then
  set +u
  source /opt/modules/lmod/9.2.4/init/bash
  module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
  module load deepmd-kit/3.2.0 abacus/LTSv3.10.1-sm70-auto
  module list 2>&1 | sed -n '1,8p'
  set -u
else
  source /etc/profile.d/modules.sh 2>/dev/null || true
fi

echo "job=${SLURM_JOB_ID:-local} node=$(hostname -s) devices=${DEV}"
mkdir -p "$WORK/record-dp" "$WORK/record-abacus"
cd "$ATST_ROOT"

echo "== DP channel: MODEL only =="
SLOTS=1 REPEATS=1 EVIDENCE_PASS=0 MODEL="$WORK/models-ro/model.ckpt-100000.pt" \
  bash scripts/sai_runtime_bench.sbatch "$WORK/record-dp" "$WORK/cases/cases-record-dp.json" "${DEV}"

echo "== ABACUS channel: ABACUS_INPUTS only =="
SLOTS=1 REPEATS=1 EVIDENCE_PASS=0 ABACUS_MODULE=1 \
  ABACUS_INPUTS="$ATST_ROOT/examples/06_relax_H2-Au/inputs" \
  bash scripts/sai_runtime_bench.sbatch "$WORK/record-abacus" "$WORK/cases/cases-record-abacus.json" "${DEV}"

echo "== record assertions =="
"${PYTHON_BIN}" - "$WORK" <<'PY'
import hashlib, json, pathlib, sys

work = pathlib.Path(sys.argv[1])
dp = json.loads((work / "record-dp/runs/bench_record.json").read_text())
ab = json.loads((work / "record-abacus/runs/bench_record.json").read_text())

def labelled(record):
    return {entry.get("label"): entry for entry in record["inputs"]["fixtures"]}

dp_fixtures, ab_fixtures = labelled(dp), labelled(ab)
assert set(dp_fixtures) == {"dp_model"}, dp_fixtures
assert set(ab_fixtures) == {"abacus_inputs"}, ab_fixtures

model = work / "models-ro/model.ckpt-100000.pt"
expected = hashlib.sha256(model.read_bytes()).hexdigest()
assert dp_fixtures["dp_model"]["sha256"] == expected, dp_fixtures["dp_model"]

entry = ab_fixtures["abacus_inputs"]
assert entry["tree_sha256"], entry
assert entry["file_count"] >= 1, entry
assert entry["sha256"] is None, entry

model_hash = dp_fixtures["dp_model"]["sha256"]
abacus_hashes = {entry.get("sha256"), entry.get("tree_sha256")}
assert model_hash not in abacus_hashes, "the ABACUS record still carries the DP model hash"

assert "fixtures=dp_model" in dp["notes"][0], dp["notes"]
assert "fixtures=abacus_inputs" in ab["notes"][0], ab["notes"]
assert not dp["warnings"], dp["warnings"]
assert not ab["warnings"], ab["warnings"]

for channel, record in (("dp", dp), ("abacus", ab)):
    revision = record["atst"]["record_time"]
    print(f"{channel}: head={revision.get('head')} branch={revision.get('branch')} dirty={revision.get('dirty')}")
print("dp fixture:", json.dumps(dp_fixtures["dp_model"]))
print("abacus fixture:", json.dumps(ab_fixtures["abacus_inputs"]))
print("RECORD-CHANNEL ASSERTIONS OK")
PY

echo "DONE"

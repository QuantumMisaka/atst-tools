#!/bin/bash
#SBATCH --job-name=atst-host-sif-pair
#SBATCH --partition=4V100
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=01:00:00
#SBATCH --qos=rush-1o2gpu
#
# host/SIF pairing (ABACUS channel): the same relax case once on the host module
# stack and once inside the toolbox SIF, in the same allocation.
#
# The SIF invocation follows what the layer1 image documents ("-B /opt") and adds
# the module's LD_LIBRARY_PATH because Apptainer strips it on entry; --nv brings
# the driver library on the GPU node.
set -euo pipefail

WORK="${WORK:-$HOME/atst-host-sif-pair-20260921}"
ATST_ROOT="${ATST_SOURCE_ROOT:-$HOME/atst-p5-20260921/atst-tools}"
PYTHON_BIN="${PYTHON_BIN:-$HOME/atst-p5-20260921/venv/bin/python}"
SIF="${SIF:-$HOME/abacus-sif-builds/20260920-toolbox-atst/abacus-adam-sai-toolbox-atst.sif}"

set +u
source /opt/modules/lmod/9.2.4/init/bash
module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
module load apptainer/1.4.4
module load abacus/LTSv3.10.1-sm70-auto
set -u

echo "job=${SLURM_JOB_ID:-local} host=$(hostname -s) CVD=${CUDA_VISIBLE_DEVICES:-unset}"
echo "host LD_LIBRARY_PATH entries: $(echo "$LD_LIBRARY_PATH" | tr ':' '\n' | wc -l)"

export PYTHONPATH="${ATST_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export ATST_SOURCE_ROOT="${ATST_ROOT}"

# ---- 1) host pass ----
host_start=$(date +%s)
"${PYTHON_BIN}" -m atst_tools.api.runner --config "${WORK}/host/config.yaml" \
  --workdir "${WORK}/host" --result-json "${WORK}/host/atst_api_result.json"
host_wall=$(( $(date +%s) - host_start ))
echo "HOST_WALL_S=${host_wall}"

# ---- 2) SIF pass ----
sif_start=$(date +%s)
apptainer exec --nv -B /opt:/opt -B "${ATST_ROOT}:/work/atst" -B "${WORK}/sif:/work/case" \
  --env "LD_LIBRARY_PATH=${LD_LIBRARY_PATH}" --env "PYTHONPATH=/work/atst/src" \
  "${SIF}" bash -c "cd /work/case && python -m atst_tools.api.runner --config config.yaml --workdir . --result-json atst_api_result.json"
sif_wall=$(( $(date +%s) - sif_start ))
echo "SIF_WALL_S=${sif_wall}"
echo "PAIR_DONE host=${host_wall}s sif=${sif_wall}s"

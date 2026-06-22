#!/bin/bash
#SBATCH --job-name=atst-dmf-irc
#SBATCH --partition=4V100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=2
#SBATCH --qos=rush-1o2gpu

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"

if [[ -z "${ATST_DMF_ATST:-}" ]]; then
  source /opt/devtools/anaconda3/etc/profile.d/conda.sh
  DMF_CACHE_ROOT="${CACHE_LOCAL:-/cache_local/${USER}}"
  DMF_ENV="${DMF_CACHE_ROOT}/atst-dmf-dpa4-${SLURM_JOB_ID}"
  echo "[$(date '+%F %T')] cloning dpeva-dpa4-test to ${DMF_ENV}"
  conda create --prefix "${DMF_ENV}" --clone dpeva-dpa4-test -y
  echo "[$(date '+%F %T')] installing cyipopt/IPOPT into ${DMF_ENV}"
  conda install --prefix "${DMF_ENV}" --offline --use-local --override-channels -c conda-forge \
    "python=3.12" "libuuid>=2.38" "python_abi=3.12.*=*cp312*" \
    cyipopt ipopt -y
  conda run --prefix "${DMF_ENV}" python -c "import ase, torch, deepmd, cyipopt; print('dmf env ok')"
  echo "[$(date '+%F %T')] installing current ATST checkout into ${DMF_ENV}"
  "${DMF_ENV}/bin/python" -m pip install -e ../.. --no-build-isolation --no-deps
  ATST_DMF_ATST="${DMF_ENV}/bin/atst"
  ATST_DMF_PYTHON="${DMF_ENV}/bin/python"
else
  ATST_DMF_PYTHON="$(dirname "$ATST_DMF_ATST")/python"
fi

export OMP_NUM_THREADS=4

echo "[$(date '+%F %T')] preparing DMF-D2S IRC inputs"
"$ATST_DMF_PYTHON" prepare_dmf_irc_inputs.py
echo "[$(date '+%F %T')] running Li-Si D2S rough-DMF descent IRC"
"$ATST_DMF_ATST" run config_07_Li-Si_d2s_dmf_irc_dp.yaml
echo "[$(date '+%F %T')] running H2-Au D2S rough-DMF descent IRC"
"$ATST_DMF_ATST" run config_08_H2-Au_d2s_dmf_irc_dp.yaml
echo "[$(date '+%F %T')] validating IRC endpoint connection"
"$ATST_DMF_PYTHON" ../../scripts/validate_dmf_irc_endpoints.py \
  irc_validation_manifest.yaml \
  --root ../.. \
  --output dmf_irc_endpoint_report.json
echo "[$(date '+%F %T')] done"

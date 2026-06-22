#!/bin/bash
#SBATCH --job-name=atst-d2s-dmf-p4-dp
#SBATCH --partition=4V100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=2
#SBATCH --qos=rush-1o2gpu

set -euo pipefail
set -x

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
  echo "[$(date '+%F %T')] installing current ATST checkout"
  "${DMF_ENV}/bin/python" -m pip install -e ../.. --no-build-isolation --no-deps
  ATST_DMF_ATST="${DMF_ENV}/bin/atst"
fi

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"

nvidia-smi dmon -s pucvmte -o T > "nvdmon_d2s_dmf_p4_dp_${SLURM_JOB_ID}.log" &

echo "[$(date '+%F %T')] running Li-Si D2S rough-DMF -> Sella smoke"
"$ATST_DMF_ATST" run config_03_Li-Si_d2s_dmf_sella_dp.yaml
echo "[$(date '+%F %T')] running H2-Au D2S rough-DMF -> Sella smoke"
"$ATST_DMF_ATST" run config_04_H2-Au_d2s_dmf_sella_dp.yaml

exit

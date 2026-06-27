#!/bin/bash
#SBATCH --job-name=atst-dmf-risk-dp
#SBATCH --partition=4V100
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=1
#SBATCH --qos=rush-1o2gpu

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"

if [[ -z "${ATST_DMF_ATST:-}" ]]; then
  source /opt/devtools/anaconda3/etc/profile.d/conda.sh
  DMF_CACHE_ROOT="${CACHE_LOCAL:-/cache_local/${USER}}"
  DMF_ENV="${DMF_CACHE_ROOT}/atst-dmf-risk-${SLURM_JOB_ID}"
  echo "[$(date '+%F %T')] cloning dpeva-dpa4-test to ${DMF_ENV}"
  conda create --prefix "${DMF_ENV}" --clone dpeva-dpa4-test -y
  echo "[$(date '+%F %T')] installing cyipopt/IPOPT into ${DMF_ENV}"
  conda install --prefix "${DMF_ENV}" --offline --use-local --override-channels -c conda-forge \
    python=3.12 "libuuid>=2.38" "python_abi=3.12.*=*cp312*" cyipopt ipopt -y
  echo "[$(date '+%F %T')] installing current checkout"
  "${DMF_ENV}/bin/python" -m pip install -e ../.. --no-build-isolation --no-deps
  ATST_DMF_ATST="${DMF_ENV}/bin/atst"
fi

export OMP_NUM_THREADS=4
nvidia-smi dmon -s pucvmte -o T > "nvdmon_dmf_risk_dp_${SLURM_JOB_ID}.log" &

echo "[$(date '+%F %T')] preparing DMF risk cases"
python dmf_risk_review.py prepare

run_case() {
  local case_name="$1"
  local config="$2"
  local timeout_seconds="${DMF_RISK_CASE_TIMEOUT_SECONDS:-600}"
  local started ended elapsed rc status

  echo "[$(date '+%F %T')] running ${config} with timeout ${timeout_seconds}s"
  started="$(date +%s)"
  set +e
  timeout "${timeout_seconds}" "$ATST_DMF_ATST" run "${config}"
  rc="$?"
  set -e
  ended="$(date +%s)"
  elapsed="$((ended - started))"
  if [[ "${rc}" -eq 0 ]]; then
    status="completed"
  elif [[ "${rc}" -eq 124 ]]; then
    status="timeout"
  else
    status="failed"
  fi
  python dmf_risk_review.py mark-run-status \
    --case "${case_name}" \
    --status "${status}" \
    --exit-code "${rc}" \
    --elapsed-seconds "${elapsed}"
  echo "[$(date '+%F %T')] ${case_name} ${status} after ${elapsed}s"
}

run_case H2-Au_wrapped_final_image risk_cases/H2-Au_wrapped_final_image/config.yaml
run_case H2-Au_swapped_H_indices risk_cases/H2-Au_swapped_H_indices/config.yaml
run_case H2-Au_inconsistent_fixed_slab risk_cases/H2-Au_inconsistent_fixed_slab/config.yaml

echo "[$(date '+%F %T')] confirming PBC+CFBENM guard rejects invalid config"
if "$ATST_DMF_ATST" config validate risk_cases/Li-Si_pbc_cfbenm/config.yaml >/tmp/atst_dmf_risk_guard_${SLURM_JOB_ID}.log 2>&1; then
  echo "PBC+CFBENM guard did not reject risk_cases/Li-Si_pbc_cfbenm/config.yaml" >&2
  cat /tmp/atst_dmf_risk_guard_${SLURM_JOB_ID}.log >&2
  exit 1
fi
cat /tmp/atst_dmf_risk_guard_${SLURM_JOB_ID}.log

echo "[$(date '+%F %T')] summarizing DMF risk cases"
python dmf_risk_review.py summarize

exit

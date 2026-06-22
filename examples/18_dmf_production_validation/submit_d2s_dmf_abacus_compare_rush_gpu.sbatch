#!/bin/bash
#SBATCH --job-name=atst-dmf-abacus
#SBATCH --partition=4V100
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --gpus-per-node=4
#SBATCH --qos=rush-gpu

set -euo pipefail

cd "$SLURM_SUBMIT_DIR"

source /etc/profile.d/modules.sh
source /opt/sai_config/mps_mapping.d/${SLURM_JOB_PARTITION}.bash
module load abacus/LTSv3.10.1-sm70-auto
source /opt/devtools/anaconda3/etc/profile.d/conda.sh
conda activate atst-dev

export OMP_NUM_THREADS=1
nvidia-smi dmon -s pucvmte -o T > "nvdmon_dmf_abacus_compare_${SLURM_JOB_ID}.log" &

ABACUS_CMD="mpirun -np ${SLURM_NTASKS} -map-by ${MAP_OPT} -mca coll_hcoll_enable 0 abacus"
MANIFEST="${ATST_DMF_ABACUS_MANIFEST:-abacus_comparison_manifest.yaml}"
OUTPUT="${ATST_DMF_ABACUS_OUTPUT:-dmf_abacus_comparison_report.json}"

python ../../scripts/validate_dmf_abacus_comparison.py \
  "${MANIFEST}" \
  --root ../.. \
  --output "${OUTPUT}" \
  --run \
  --command "${ABACUS_CMD}"

exit

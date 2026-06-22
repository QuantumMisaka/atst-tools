#!/bin/bash
#SBATCH --job-name=atst-dmf-abacus-refined
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
nvidia-smi dmon -s pucvmte -o T > "nvdmon_dmf_abacus_refined_compare_${SLURM_JOB_ID}.log" &

ABACUS_CMD="mpirun -np ${SLURM_NTASKS} -map-by ${MAP_OPT} -mca coll_hcoll_enable 0 abacus"

python ../../scripts/validate_dmf_abacus_comparison.py \
  abacus_comparison_refined_manifest.yaml \
  --root ../.. \
  --output dmf_abacus_comparison_refined_report.json \
  --run \
  --command "${ABACUS_CMD}"

exit

#!/bin/bash
#SBATCH --job-name=atst-h2au-dmf-abacus-sella
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
nvidia-smi dmon -s pucvmte -o T > "nvdmon_h2au_dmf_abacus_sella_${SLURM_JOB_ID}.log" &

mkdir -p runs/11_H2-Au_d2s_dmf_sella_abacus/SELLA

atst run config_11_H2-Au_d2s_dmf_sella_abacus.yaml

python - <<'PY'
from ase.io import read, write
frame = read("runs/11_H2-Au_d2s_dmf_sella_abacus/sella.traj", index=-1)
write("runs/11_H2-Au_d2s_dmf_sella_abacus/final.extxyz", frame)
print("wrote runs/11_H2-Au_d2s_dmf_sella_abacus/final.extxyz")
PY

exit

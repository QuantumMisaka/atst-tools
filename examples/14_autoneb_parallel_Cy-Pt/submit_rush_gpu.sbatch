#!/bin/bash
#SBATCH --job-name=atst-cypt-autoneb-img4
#SBATCH --partition=4V100
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --gpus-per-node=4
#SBATCH --qos=rush-gpu

source /etc/profile.d/modules.sh
source /opt/sai_config/mps_mapping.d/${SLURM_JOB_PARTITION}.bash

nvidia-smi dmon -s pucvmte -o T > nvdmon_autoneb_parallel_single_gpu_$SLURM_JOB_ID.log &
module load abacus/LTSv3.10.1-sm70-auto
source /opt/devtools/anaconda3/etc/profile.d/conda.sh
conda activate atst-neb-mpi

mpirun -np 4 --map-by $MAP_OPT atst run config.yaml

exit

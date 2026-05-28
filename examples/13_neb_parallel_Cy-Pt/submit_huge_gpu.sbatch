#!/bin/bash
#SBATCH --job-name=atst-cypt-neb-img5
#SBATCH --partition=4V100
#SBATCH --nodes=5
#SBATCH --ntasks=20
#SBATCH --gpus-per-node=4
#SBATCH --qos=huge-gpu

source /etc/profile.d/modules.sh
source /opt/sai_config/mps_mapping.d/${SLURM_JOB_PARTITION}.bash

nvidia-smi dmon -s pucvmte -o T > nvdmon_neb_parallel_nested_mpi_$SLURM_JOB_ID.log &
module load abacus/LTSv3.10.1-sm70-auto
source /opt/devtools/anaconda3/etc/profile.d/conda.sh
conda activate atst-neb-mpi

mpirun -np 5 --map-by ppr:1:node atst run config.yaml

exit

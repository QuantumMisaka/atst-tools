#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=16
#SBATCH --cpus-per-task=1
#SBATCH -J ATST-D2S
#SBATCH -o job.out
#SBATCH -e job.err
#SBATCH -p normal

# Load environment
module load abacus/3.7.5
source activate atst

# Run D2S Workflow
# D2S workflow handles optimization, rough NEB, and single-ended search internally
atst-run config.yaml

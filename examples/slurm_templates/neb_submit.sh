#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks=16
#SBATCH --cpus-per-task=1
#SBATCH -J ATST-NEB
#SBATCH -o job.out
#SBATCH -e job.err
#SBATCH -p normal

# Load environment
module load abacus/3.7.5
source activate atst

# 1. Generate Initial Guess (Optional, if not provided)
# atst-neb-make init.stru final.stru 8

# 2. Run Calculation
atst-run config.yaml

# 3. Post Processing
atst-neb-post neb.traj --plot

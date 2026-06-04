#!/bin/bash
#SBATCH --job-name=atst-02-neb-ts-par-4v
#SBATCH --partition=4V100
#SBATCH --nodes=8
#SBATCH --ntasks=32
#SBATCH --gpus-per-node=4
#SBATCH --qos=huge-gpu
#SBATCH --time=1-00:00:00
#SBATCH --output=slurm-%x-%j.out
#SBATCH --error=slurm-%x-%j.err

set -euo pipefail

REPO=/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools
source /etc/profile.d/modules.sh
source /opt/sai_config/mps_mapping.d/${SLURM_JOB_PARTITION}.bash
module load abacus/LTSv3.10.1-sm70-auto
source /opt/devtools/anaconda3/etc/profile.d/conda.sh
conda activate atst-dev

echo "case=02_parallel"
echo "date=$(date '+%F %T %Z')"
echo "repo_commit=$(git -C "${REPO}" rev-parse HEAD)"
python -c "import atst_tools, mpi4py; from mpi4py import MPI; print('python', __import__('sys').executable); print('atst_tools', atst_tools.__file__); print('mpi4py', mpi4py.__version__, MPI.Get_library_version().splitlines()[0])"
which atst
atst --version
which mpirun
which abacus
timeout 30 abacus --version || true
module list
mpirun -np 8 --map-by ppr:1:node python -c "from mpi4py import MPI; from ase.parallel import world; print('outer_rank', MPI.COMM_WORLD.Get_rank(), 'size', MPI.COMM_WORLD.Get_size(), 'ase_size', world.size)"

nvidia-smi dmon -s pucvmte -o T > nvdmon_job-${SLURM_JOB_ID}.log &
ATST_NVDMON_PID=$!

mpirun -np 8 --map-by ppr:1:node atst run config.yaml
atst neb summary neb_parallel_nested_mpi.traj --n-max 8 --strict --format json --output summary.json

kill ${ATST_NVDMON_PID} || true
exit

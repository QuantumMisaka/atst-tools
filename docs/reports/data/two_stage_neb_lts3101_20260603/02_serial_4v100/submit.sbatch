#!/bin/bash
#SBATCH --job-name=atst-02-neb-ts-ser-4v
#SBATCH --partition=4V100
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --gpus-per-node=4
#SBATCH --qos=huge-gpu
#SBATCH --time=3-00:00:00
#SBATCH --output=slurm-%x-%j.out
#SBATCH --error=slurm-%x-%j.err

set -euo pipefail

REPO=/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools
source /etc/profile.d/modules.sh
source /opt/sai_config/mps_mapping.d/${SLURM_JOB_PARTITION}.bash
module load abacus/LTSv3.10.1-sm70-auto
source /opt/devtools/anaconda3/etc/profile.d/conda.sh
conda activate atst-dev

echo "case=02_serial"
echo "date=$(date '+%F %T %Z')"
echo "repo_commit=$(git -C "${REPO}" rev-parse HEAD)"
python -c "import atst_tools, mpi4py; from mpi4py import MPI; print('python', __import__('sys').executable); print('atst_tools', atst_tools.__file__); print('mpi4py', mpi4py.__version__, MPI.Get_library_version().splitlines()[0])"
which atst
atst --version
which mpirun
which abacus
timeout 30 abacus --version || true
module list

nvidia-smi dmon -s pucvmte -o T > nvdmon_job-${SLURM_JOB_ID}.log &
ATST_NVDMON_PID=$!

atst run config.yaml
atst neb summary neb.traj --n-max 8 --strict --format json --output summary.json

kill ${ATST_NVDMON_PID} || true
exit

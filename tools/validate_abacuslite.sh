#!/bin/bash
set -u

# Validation Script for atst-tools and abacuslite

# 1. Environment Setup
source /home/pku-jianghong/liuzhaoqing/.bashrc
eval "$(conda shell.bash hook)"
conda activate atst-dev

# Load Modules
module load abacus/LTSv3.10.1-sm70-auto

# 2. Run ASE_interface Tests
echo "========================================"
echo "Running ASE_interface Tests..."
echo "========================================"
export PYTHONPATH=$PYTHONPATH:/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/temp_repos/abacus-develop/interfaces/ASE_interface
TEST_DIR="/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/temp_repos/abacus-develop/interfaces/ASE_interface/tests"

cd $TEST_DIR || exit 1
bash xtest.sh
if [ $? -ne 0 ]; then
    echo "ASE_interface tests FAILED"
    exit 1
fi
echo "ASE_interface tests PASSED"

# 3. Check DeepMD and Run DP Examples
echo "========================================"
echo "Checking DeepMD..."
echo "========================================"
if python -c "import deepmd" 2>/dev/null; then
    echo "DeepMD found. Running DP examples..."
    cd /home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/examples/01_neb_Li-Si
    atst-run config_dp.yaml
else
    echo "WARNING: deepmd-kit not found. Skipping DP examples."
    # We do not exit here to allow ABACUS submission, but we note the failure.
fi

# 4. Submit ABACUS Examples
echo "========================================"
echo "Submitting ABACUS Examples..."
echo "========================================"
cd /home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/examples/01_neb_Li-Si

# Generate submission script if not exists
if [ ! -f submit_neb.sbatch ]; then
cat <<EOF > submit_neb.sbatch
#!/bin/bash
#SBATCH --job-name=atst_val_01
#SBATCH --partition=4V100PX
#SBATCH --qos=rush-1o2gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gpus-per-node=1
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err

module load abacus/LTSv3.10.1-sm70-auto
source /home/pku-jianghong/liuzhaoqing/.bashrc
eval "\$(conda shell.bash hook)"
conda activate atst-dev

cd /home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/examples/01_neb_Li-Si
atst-run config.yaml
EOF
fi

sbatch submit_neb.sbatch

# 5. Snapshots
cd /home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools
conda list > conda_env_snapshot.txt
pip freeze > pip_snapshot.txt

echo "Validation process completed."

#!/bin/bash
set -u

# Validation script for atst-tools and the vendored abacuslite ASE_interface.

ROOT=/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools
ASE_INTERFACE="$ROOT/src/atst_tools/external/ASE_interface"

source /home/pku-jianghong/liuzhaoqing/.bashrc
eval "$(conda shell.bash hook)"
conda activate atst-dev
source /etc/profile.d/modules.sh
module load abacus/LTSv3.10.1-sm70-auto

echo "========================================"
echo "Running vendored ASE_interface tests..."
echo "========================================"
export PYTHONPATH=$PYTHONPATH:$ASE_INTERFACE
cd "$ASE_INTERFACE/tests" || exit 1
bash xtest.sh
if [ $? -ne 0 ]; then
    echo "ASE_interface tests FAILED"
    exit 1
fi
echo "ASE_interface tests PASSED"

echo "========================================"
echo "Checking DeepMD import..."
echo "========================================"
if python -c "import deepmd" 2>/dev/null; then
    echo "DeepMD found. DP real workflow validation is deferred until ABACUS examples pass."
else
    echo "WARNING: deepmd-kit not found. DP examples remain deferred."
fi

echo "========================================"
echo "Submitting ABACUS examples..."
echo "========================================"
for case_dir in "$ROOT"/examples/[0-9][0-9]_*; do
    [ -f "$case_dir/config.yaml" ] || continue
    cd "$case_dir" || exit 1
    cat > submit_atst_abacus.sbatch <<EOF
#!/bin/bash
#SBATCH --job-name=atst_$(basename "$case_dir" | cut -c1-8)
#SBATCH --partition=4V100
#SBATCH --qos=rush-gpu
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --gpus-per-node=4
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err

source /etc/profile.d/modules.sh
module load abacus/LTSv3.10.1-sm70-auto
source /home/pku-jianghong/liuzhaoqing/.bashrc
eval "\$(conda shell.bash hook)"
conda activate atst-dev

cd "$case_dir"
atst-run config.yaml
EOF
    sbatch submit_atst_abacus.sbatch
done

cd "$ROOT" || exit 1
conda list > conda_env_snapshot.txt
pip freeze > pip_snapshot.txt

echo "Validation submission completed."

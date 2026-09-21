#!/bin/bash
#SBATCH --job-name=atst-dp-warmup
#SBATCH --partition=4V100
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:30:00
#SBATCH --qos=rush-1o2gpu
set -euo pipefail
set +u
source /opt/modules/lmod/9.2.4/init/bash
module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
module load deepmd-kit/3.2.0
set -u
export PYTHONPATH="$HOME/atst-p5-20260921/atst-tools/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$HOME/atst-p5-20260921/venv/bin/python" "$HOME/atst-ccqn-20260921/probe_dp_warmup.py"

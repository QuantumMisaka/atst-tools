#!/bin/bash
#SBATCH --job-name=atst-cp-omp-probe
#SBATCH --partition=4V100
#SBATCH --gres=gpu:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=00:30:00
#SBATCH --qos=rush-1o2gpu
# Diagnostic: reproduce the CP OMP override with the caller chain printed.
set -euo pipefail
set +u
source /opt/modules/lmod/9.2.4/init/bash
module use /opt/modules/modulefiles/devtools /opt/modules/modulefiles/apps
module load deepmd-kit/3.2.0
module load abacus/LTSv3.10.1-sm70-auto
set -u
export PYTHONPATH="$HOME/atst-p5-20260921/atst-tools/src"
cd "$HOME/atst-cp-runtime-20260921/cases/cp-gate-single"
exec "$HOME/atst-p5-20260921/venv/bin/python" "$HOME/atst-cp-runtime-20260921/probe_eval_omp.py" \
  --config config.yaml --workdir probe-run --result-json probe_result.json

# DMF Environment Smoke Report 2026-06-18

**Version**: 2026-06-18
**Date**: 2026-06-18
**Status**: Current evidence
**Owner**: ATST-Tools maintainers
**Scope**: P0/P1 DMF dependency and runtime smoke

## Summary

DMF dependency setup was validated in a temporary cache-local conda environment:

```text
/cache_local/liuzhaoqing/atst-dmf-dpa4
```

This avoids the home-directory quota issue that prevented creating
`~/.conda/envs/atst-dmf-dpa4`.

## Environment Setup

The first attempt to install `cyipopt ipopt` into the cloned environment failed
because defaults-channel `libuuid` conflicted with conda-forge Python ABI
requirements. The successful installation explicitly migrated Python ABI and
`libuuid` to conda-forge:

```bash
conda create --prefix /cache_local/liuzhaoqing/atst-dmf-dpa4 --clone dpeva-dpa4-test -y
conda install --prefix /cache_local/liuzhaoqing/atst-dmf-dpa4 \
  --override-channels -c conda-forge \
  'python=3.12' 'libuuid>=2.38' 'python_abi=3.12.*=*cp312*' \
  cyipopt ipopt -y
/cache_local/liuzhaoqing/atst-dmf-dpa4/bin/python -m pip install -e .
```

## Import Smoke

Validated command:

```bash
/cache_local/liuzhaoqing/atst-dmf-dpa4/bin/python -c \
  "import ase, torch, deepmd, cyipopt; import atst_tools; print('ok', ase.__version__, torch.__version__, atst_tools.package_version())"
```

Observed output:

```text
ok 3.28.0 2.11.0+cu126 2.1.2
```

Vendored PyDMF NumPy and torch namespaces were also importable:

```bash
/cache_local/liuzhaoqing/atst-dmf-dpa4/bin/python -c \
  "from atst_tools.external.pydmf.dmf import DirectMaxFlux; from atst_tools.external.pydmf.dmf.torch import DirectMaxFlux as TorchDirectMaxFlux; print('pydmf ok', DirectMaxFlux.__name__, TorchDirectMaxFlux.__name__)"
```

Observed output:

```text
pydmf ok DirectMaxFlux DirectMaxFlux
```

## Runtime Smoke

A direct vendored PyDMF smoke was run with ASE EMT on a small non-periodic HOH
endpoint pair. The smoke exercised:

- `interpolate_fbenm(..., correlated=True)`
- `DirectMaxFlux(..., coefs=...)`
- `cyipopt` solve
- `tmax` candidate extraction
- trajectory writes

Artifacts were written under:

```text
/cache_local/liuzhaoqing/atst-dmf-smoke-20260618
```

Observed summary:

```json
{
  "workflow": "direct_pydmf_emt_smoke",
  "n_images": 5,
  "history_tmax_count": 2,
  "last_tmax": 0.0,
  "ipopt_status": 0,
  "ipopt_status_msg": "b'Algorithm terminated successfully at a locally optimal point, satisfying the convergence tolerances (can be specified by options).'"
}
```

This is dependency/runtime smoke evidence only. It is not P3 production
validation and does not promote DMF beyond experimental status.

## Remaining Work

- Run at least two P3 production comparison cases from the DMF plan with
  DP/ABACUS and CI-NEB baselines.
- Write the P3 runtime validation report with barrier, TS mode, endpoint
  connection, walltime, and failure-mode comparisons.
- Only after P3 evidence, implement and validate D2S `rough_method: dmf`.

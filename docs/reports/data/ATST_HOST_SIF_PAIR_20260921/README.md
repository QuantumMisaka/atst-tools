# host/SIF pairing, ABACUS channel (2026-09-21, job 1438496)

The last P5 row: one relax case (example 06 H2-Au, `max_steps: 1`, `mpi: 1`,
`omp: 8`) run twice in the same allocation - once on the host module stack and
once inside the toolbox SIF - with the same atst runner on both sides
(`python -m atst_tools.api.runner`, the SIF using the image's own Python 3.12).

| pass | runtime | wall | final energy | sidecar |
| --- | --- | --- | --- | --- |
| host | module `abacus/LTSv3.10.1-sm70-auto`, venv Python 3.13 | 142 s | −239256.2707 eV | complete (1 build, 1 force call, OMP=8) |
| SIF | `apptainer exec --nv -B /opt:/opt ...`, image Python 3.12.14 | 153 s | −239256.2707 eV | complete (1 build, 1 force call, OMP=8) |

The SIF invocation is the working recipe discovered this round (the layer1
image documents `-B /opt`; Apptainer strips `LD_LIBRARY_PATH`, so the module's
value is passed through `--env`, and `--nv` supplies `libcuda.so.1` on the GPU
node).  It also binds the checkout to `/work/atst` and the case directory to
`/work/case`, with `PYTHONPATH=/work/atst/src`; the SIF-side config points
`command` at the image's own `/usr/local/bin/abacus` wrapper.

Only container networking noise appears in the SIF pass (`libibverbs` config
warning, UCX falling back to TCP).

`staging/` holds both case configs and the sbatch entry; `*-atst_api_result.json`
and `*-runtime_evidence.json` are the runner outputs and sidecars of each pass.

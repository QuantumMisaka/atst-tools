# host/SIF pairing - site reconnaissance (2026-09-21)

The P5 plan pairs one case on the host (module environment) with the same case
inside the toolbox SIF.  This slice records what the SIF currently offers on
`galileouser02`, so the remaining row has a precise blocker instead of a vague
"needs site coordination".

Image: `~/abacus-sif-builds/20260920-toolbox-atst/abacus-adam-sai-toolbox-atst.sif`
(1.5 GB, labels: `AtstToolsDelivery: toolbox`, `HostCluster: sai-native`,
`Layer: 2`, `SAI_RUNTIME_CONTRACT_SUPPORTED=1`).

What works (login node, `module load apptainer/1.4.4`):

```text
$ apptainer exec --bind $HOME/atst-p5-20260921/atst-tools:/work/atst <sif> \
    bash -lc 'PYTHONPATH=/work/atst/src python -c "import atst_tools, ase, pydantic; ..."'
atst_tools /work/atst/src/atst_tools/__init__.py
ase 3.29.0 | pydantic 2.13.5
```

so the checkout imports inside the image (Python 3.12.14, `numpy`/`mpi4py`
present).  `deepmd` is **not** installed in the image, so only the ABACUS
channel is available there.

What blocks the pairing: the image's ABACUS is a "SAI-native runtime provider"
wrapper (`/usr/local/bin/abacus` -> `sai_native_runtime_prepare`), which expects
the site's module stack to be visible inside the container:

```text
$ apptainer exec --bind /opt/modules:/opt/modules --bind /opt/apps:/opt/apps \
    --bind /opt/devtools:/opt/devtools,ro <sif> bash -c 'abacus --version'
SAI-native runtime error: module did not provide a readable ScaLAPACK library directory
```

and `mpirun` is not resolvable inside either (loading
`openmpi/5.0.8-nvhpc25.7-gnu-auto` in a container shell reports nothing and
leaves `mpirun` missing), while the module stack it does resolve points at
`/opt/devtools/...` (ELPA/openmpi) - with `/opt/devtools` bound the wrapper
still fails the ScaLAPACK check.

Status: the row stays open and is handed to the SIF owner (the image is the
toolbox delivery): either the wrapper needs an additional documented bind /
stack fix, or the pairing uses the toolbox launcher instead of a bare
`apptainer exec`.  Re-run the two commands above to check a rebuilt image.

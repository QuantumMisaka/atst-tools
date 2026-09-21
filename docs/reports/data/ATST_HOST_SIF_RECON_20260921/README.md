# host/SIF pairing - site reconnaissance (2026-09-21)

Scope first: the image under `~/abacus-sif-builds/20260920-toolbox-atst/` is the
**ABACUS** toolbox delivery (`Application: ABACUS`, `AtstToolsDelivery: toolbox`,
`HostCluster: sai-native`, `Layer: 2`).  DeepMD is intentionally **not** in it -
the DP channel's runtime is the site's `deepmd-kit/3.2.0` module environment
(which every DP run in this project used).  So this row is an ABACUS-channel
pairing: host module ABACUS vs SIF ABACUS; a DP container comparison would be
the DP side's own image, not this one.

What works inside the image (`module load apptainer/1.4.4`):

```text
$ apptainer exec --bind $HOME/atst-p5-20260921/atst-tools:/work/atst <sif> \
    bash -lc 'PYTHONPATH=/work/atst/src python -c "import atst_tools, ase, pydantic; ..."'
atst_tools /work/atst/src/atst_tools/__init__.py
ase 3.29.0 | pydantic 2.13.5          # Python 3.12.14, numpy/mpi4py present
```

so the checkout imports from a bind mount; the ABACUS binary at
`/opt/apps/abacus/abacus-develop-LTSv3.10.1/bin_sm70_avx512/abacus` is also
visible when `/opt/apps` is bound.

The blocker is a **bind/overlay conflict on `/opt/devtools`**:

```text
$ apptainer exec --bind /opt/modules:/opt/modules --bind /opt/apps:/opt/apps \
    --bind /opt/devtools:/opt/devtools,ro <sif> \
    ls -l /opt/devtools/saiblas/2509-gnu-avx512/lib/libscalapack.so ...
/bin/ls: cannot access '/opt/devtools/saiblas/.../libscalapack.so': No such file or directory
/bin/ls: cannot access '/opt/devtools/elpa/.../lib': No such file or directory
-rwxr-xr-x 1 nobody nogroup 355913072 ... /opt/apps/abacus/.../abacus     # this one IS visible
```

i.e. `/opt/apps` binds through while the whole `/opt/devtools` tree (site BLAS /
ScaLAPACK / ELPA / CUDA / OpenMPI) does not, in this account.  Consequences,
depending on how ABACUS is invoked inside the container:

* the image's own wrapper (`/usr/local/bin/abacus` ->
  `sai_native_runtime_prepare`, see
  `/usr/local/share/abacus/abacus-native-runtime.sh:148`) fails its
  "readable ScaLAPACK library directory" check (`sai_native_module_blas_library_dir`
  scans `LD_LIBRARY_PATH` for `libscalapack.so*`; the file exists on the host and
  the path is on the in-container `LD_LIBRARY_PATH`, yet the directory is not
  readable inside), and with a writable bind it degrades to "ABACUS has
  unresolved shared libraries" (its `ldd` check);
* running the host binary directly inside the container leaves 12 unresolved
  shared libraries.

The same message appears for every image in the account
(`abacus-adam-sai-atst226-matesbench-candidate-a.sif`,
`20260822-closure-3fe3618b`, `20260823-closure-4996a8c1`,
`20260814-836863-e103fc56`), so this is a launch-context issue, not one broken
build.

Handoff (image owner, the toolbox delivery): either the documented launcher /
extra binds that make `/opt/devtools` visible (the `shared-layer2` build may
mount over `/opt`), or the wrapper needs an equivalent that reads the stack from
the host's environment.  Re-running the two commands above against a rebuilt
image checks it.

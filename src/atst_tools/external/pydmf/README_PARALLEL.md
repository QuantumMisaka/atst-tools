# Parallel energy/force evaluation

## Overview

PyDMF supports parallel energy and force evaluations at the energy evaluation points along the path. As of v1.2.1, PyDMF implements only thread-based parallelization. In practice, PyDMF simply runs multiple ASE calculators concurrently.

Therefore, when constructing the calculators, users should explicitly allocate computational resources as needed and avoid conflicts in output files or working directories.

## Details

Parallel evaluation is enabled by passing `parallel=True` when constructing a `DirectMaxFlux` object.

The evaluations are parallelized as follows:

- In the initial step, the energy and force calculations for the two endpoint images, `images[0]` and `images[nimages - 1]`, are performed in parallel.
- In subsequent steps, the energy and force calculations for the internal images, from `images[1]` to `images[nimages - 2]`, are performed in parallel. The number of these images is `nimages - 2`, which is equal to `nmove`.

## Example: Gaussian calculators

The following example runs Gaussian calculations on `nmove` nodes. Each calculation is launched on a specified node using `mpirun`, and each image uses a separate output directory. This example assumes that the working directory is located on an NFS-mounted filesystem and is visible from all nodes.

```python
mxflx = DirectMaxFlux([react, prod], parallel=True, ...)

mxflx.images[0].calc = Gaussian(
    command="mpirun -np 1 -host node00 g16 < PREFIX.com > PREFIX.log",
    label="image00/force",
    ...,
)

mxflx.images[-1].calc = Gaussian(
    command="mpirun -np 1 -host node01 g16 < PREFIX.com > PREFIX.log",
    label=f"image{mxflx.nimages - 1:02}/force",
    ...,
)

for i, image in enumerate(mxflx.images[1:-1], start=1):
    image.calc = Gaussian(
        command=f"mpirun -np 1 -host node{i - 1:02} g16 < PREFIX.com > PREFIX.log",
        label=f"image{i:02}/force",
        ...,
    )
```

Depending on the MPI implementation and local environment settings, it may be necessary to explicitly pass required environment variables to the MPI-launched processes.

# About GPU acceleration

Thanks to the contribution by @t-0hmura, GPU acceleration is now available in v1.2.0 and later.

Before we complete the major revision of the API documentation currently planned, we would like to provide usage instructions here. A detailed report on the performance and related implementation details is also available at [https://github.com/shin1koda/dmf/pull/3](https://github.com/shin1koda/dmf/pull/3).


## dmf.torch (GPU acceleration)

`dmf.torch` is a PyTorch-accelerated backend that mirrors the `dmf` API while offloading internal tensor operations to PyTorch (CUDA when available).

If you want to use `dmf.torch`, install a CUDA-matched build of PyTorch before installing PyDMF.
Example for CUDA 12.8:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install "pydmf[torch]"
```

To use the PyTorch backend, import from `dmf.torch`. The rest of the API is unchanged:

```python
from dmf.torch import DirectMaxFlux, interpolate_fbenm
```

When using `dmf.torch`, it automatically utilizes the available CUDA device. However, you can optionally specify the CUDA device in entry points such as `DirectMaxFlux` and `interpolate_fbenm`:

```python
mxflx = DirectMaxFlux(ref_images, coefs=coefs, nmove=3, device="cuda")
mxflx_fbenm = interpolate_fbenm(ref_images, correlated=True, device="cuda")
```

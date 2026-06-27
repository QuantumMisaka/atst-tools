import numpy as np
import torch
import warnings


def _resolve_torch_device(device_spec):
    """
    Resolve a torch device from a user spec.
    """
    if device_spec is None:
        d = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        try:
            d = torch.device(device_spec)
        except (TypeError, ValueError):
            warnings.warn(f"[dmf.torch] Invalid device spec '{device_spec}', falling back to CPU.")
            d = torch.device("cpu")
    if d.type == "cuda" and not torch.cuda.is_available():
        warnings.warn("[dmf.torch] CUDA requested but not available; falling back to CPU.")
        d = torch.device("cpu")
    return d


def _resolve_torch_dtype(dtype_spec):
    """
    Resolve a torch dtype from a user spec (float32/float64).
    """
    if dtype_spec is None:
        return torch.float64
    if isinstance(dtype_spec, torch.dtype):
        if dtype_spec in (torch.float32, torch.float64):
            return dtype_spec
        warnings.warn(f"[dmf.torch] Unsupported dtype '{dtype_spec}', falling back to float64.")
        return torch.float64
    if isinstance(dtype_spec, str):
        key = dtype_spec.strip().lower()
        if key in ("float32", "fp32", "single", "float"):
            return torch.float32
        if key in ("float64", "fp64", "double"):
            return torch.float64
        warnings.warn(f"[dmf.torch] Invalid dtype spec '{dtype_spec}', falling back to float64.")
        return torch.float64
    try:
        np_dtype = np.dtype(dtype_spec)
        if np_dtype.kind == "f" and np_dtype.itemsize == 4:
            return torch.float32
        if np_dtype.kind == "f" and np_dtype.itemsize == 8:
            return torch.float64
    except Exception:
        pass
    warnings.warn(f"[dmf.torch] Invalid dtype spec '{dtype_spec}', falling back to float64.")
    return torch.float64


# Backward-compatible aliases.
resolve_torch_device = _resolve_torch_device
resolve_torch_dtype = _resolve_torch_dtype

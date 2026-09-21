# Shared-worker validation on SAI (2026-09-21, job 1438378)

One V100, three identical CCQN cases (H2+Au64, FT2DP single-head model, each
config carrying a `runtime` section), ran twice:

| mode | batch wall | per-case walls |
| --- | --- | --- |
| `--share-worker` off | 17.38 s | 6.76 / 5.31 / 5.31 s |
| `--share-worker` on | **5.73 s** | 4.18 / **0.35** / **0.35** s |

So on the site the mode pays 3.0x for this small batch: the model load and the
first call happen once, and the following cases cost ~0.35 s each.

`runs-guard/` keeps the fail-closed check: the same shared mode with a config
asking for `runtime.devices: [1]` while the batch holds device 0 - one case,
failed in 0.30 s with
`case_error: RuntimeBindingError: device index 1 is outside the inherited visible set (size 1)`.

`staging/` holds the manifests, the four case configs, the sbatch entry.

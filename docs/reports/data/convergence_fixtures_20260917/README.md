# Convergence stage fixtures (2026-09-17)

Canonical serialized manifest fixtures for the ATST → Paimon producer-consumer
agreement of optimizer convergence facts. They are **schema fixtures** produced
by the real serialization helpers (`StageRecord.to_manifest()` +
`write_artifact_manifest`), not records of a real ABACUS/DP run.

Provenance: generated on 2026-09-17 from branch `feature/workflow-convergence`
(see the branch commit history) with the shared
`src/atst_tools/utils/convergence.py` helper. Regenerate with the same helper
if the stage contract changes; do not hand-edit.

| File | Covers |
| :--- | :--- |
| `sella_false.json` | explicit-false Sella record with criterion provenance |
| `relax_true.json` | relax record with trajectory/log/final-structure artifacts |
| `ccqn_null.json` | CCQN run whose convergence signal is unknown (`null`) |
| `neb_two_stage.json` | ordinary warmup + CI-NEB final stage, both facts |
| `neb_endpoint_serial.json` | skipped + completed endpoint records before the band stages |
| `irc_both_directions.json` | one record per IRC direction with stage-local step deltas |
| `autoneb_windows.json` | per-iteration image-subset windows plus the last-iteration final scope |
| `d2s_constituents.json` | endpoint / rough / refinement / vibration stages in one D2S manifest |
| `api_synthesized.json` | API-synthesized completion: execution complete, convergence unknown |
| `legacy_no_stages.json` | pre-2.2.6 manifest without stage records (readers must treat as unknown) |

## Consumer rules

- The manifest is the durable authority; the API result document only exposes
  its path. Do not recompute convergence from trajectories or raw force maxima.
- `name`, `status` and `converged` are always present on stage records;
  `converged` is strictly `true`, `false` or `null` (`null` = unknown, never
  "false"). `status` describes execution (`complete`/`skipped`/`failed`);
  `status == "complete"` never means converged.
- Optional keys (`role`, `criterion`, `direction`, `iteration`, `subset`,
  `fmax`, `fmax_unit`, `steps`, `actual_steps`, `measured`, `measured_unit`)
  appear only when the producer recorded them.
- `subset` identifies the image window actually optimized (AutoNEB); a final
  AutoNEB record never claims whole-band convergence. IRC `direction` uses the
  runtime values `forward`/`reverse`.
- A synthesized manifest (`metadata.manifest_source == "api_synthesized"`)
  means execution completed with convergence unknown.
- Presentation may translate facts into another language, but must not alter
  values, invent `false`, or treat missing legacy records as success.

# Sella IRC Integration Review

**Date**: 2026-05-12  
**Version**: 2.0.0

## Conclusion

ATST-Tools 2.0.0 has migrated the main-branch Sella IRC application pattern
into the unified CLI/YAML workflow. The project is responsible for reading the
TS structure, constructing the configured ASE calculator, passing IRC control
parameters to Sella, writing trajectories, and reporting known boundary
conditions. The IRC integration algorithm itself is delegated to the upstream
Sella package.

## Main-Branch Behavior

The legacy `sella/sella_IRC.py` and `ase-dp/sella_dp_IRC.py` scripts:

- read a TS structure from `STRU`;
- attach an ABACUS or DP ASE calculator;
- construct `sella.IRC(ts_atoms, trajectory=..., dx=..., eta=...)`;
- run `direction='forward'` and then `direction='reverse'`;
- post-process the raw trajectory into `norm_irc_log.traj` using monotonic
  energy segments.

## Refactored Behavior

`calculation.type: irc` follows the same application mode through
`IRCWorkflow`:

- `init_structure`, `trajectory`, `normalized_trajectory`, `direction`, `dx`,
  `eta`, `gamma`, `irctol`, `keep_going`, `fmax`, and `max_steps` are governed
  by the YAML schema.
- Calculator construction is delegated to `CalculatorFactory`, so the same IRC
  workflow works with ABACUS and DP.
- `direction: both` executes forward and reverse directions and writes the
  normalized trajectory after both directions finish.
- Restart reads the last trajectory frame and appends to the existing
  trajectory.

## Boundary Handling

Historical ABACUS IRC reruns reached valid force calls and wrote physical
frames, then stopped inside Sella with either
`IRCInnerLoopConvergenceFailure` or an assertion in
`sella/optimize/restricted_step.py:get_s`. ATST-Tools now catches those known
Sella boundary failures and reports a controlled `IRCBoundaryError` with the
direction, trajectory frame count, and original exception type.

This confirms that the remaining flat-endpoint behavior belongs to the Sella
IRC integration boundary, not to ATST-Tools calculator construction, YAML
normalization, or trajectory orchestration.

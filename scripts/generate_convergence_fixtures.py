"""Generate the canonical convergence stage fixtures for the consumer handoff.

The fixtures under ``docs/reports/data/convergence_fixtures_20260917/`` are
produced by the real serialization helpers
(``StageRecord.to_manifest`` + ``write_artifact_manifest``) so the committed
JSON always matches the producer contract.  Re-run this script after any stage
contract change instead of hand-editing the JSON files.

Examples:
    conda run -n atst-dev python scripts/generate_convergence_fixtures.py
    conda run -n atst-dev python scripts/generate_convergence_fixtures.py --output /tmp/fixtures
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from atst_tools.utils.artifacts import write_artifact_manifest
from atst_tools.utils.convergence import StageRecord


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "reports"
    / "data"
    / "convergence_fixtures_20260917"
)


def generate(output: Path) -> list[str]:
    """Write every fixture into ``output`` and return the written file names."""
    output.mkdir(parents=True, exist_ok=True)

    write_artifact_manifest(
        output / "sella_false.json",
        workflow="sella",
        artifacts=[{"role": "trajectory", "path": "sella.traj"}],
        stages=[
            StageRecord(
                name="sella",
                role="final",
                criterion="sella_projected_force+constraint",
                converged=False,
                fmax=0.05,
                steps=100,
                actual_steps=100,
            ).to_manifest()
        ],
    )
    write_artifact_manifest(
        output / "relax_true.json",
        workflow="relax",
        artifacts=[
            {"role": "trajectory", "path": "relax.traj"},
            {"role": "log", "path": "relax.log"},
            {"role": "final_structure", "path": "final_relaxed.traj"},
        ],
        stages=[
            StageRecord(
                name="relax",
                role="final",
                criterion="ase_optimizer",
                converged=True,
                fmax=0.05,
                steps=200,
                actual_steps=37,
            ).to_manifest()
        ],
    )
    write_artifact_manifest(
        output / "ccqn_null.json",
        workflow="ccqn",
        artifacts=[
            {"role": "trajectory", "path": "ccqn.traj"},
            {"role": "ts_structure", "path": "ccqn_final.extxyz"},
        ],
        stages=[
            StageRecord(
                name="ccqn",
                role="final",
                criterion="ccqn_prfo",
                converged=None,
                fmax=0.05,
                steps=200,
                actual_steps=200,
            ).to_manifest()
        ],
    )
    write_artifact_manifest(
        output / "neb_two_stage.json",
        workflow="neb",
        artifacts=[{"role": "trajectory", "path": "neb.traj"}],
        stages=[
            StageRecord(
                name="ordinary_neb_warmup",
                role="warmup",
                converged=True,
                fmax=0.2,
                steps=20,
                actual_steps=8,
            ).to_manifest(),
            StageRecord(
                name="ci_neb",
                role="final",
                criterion="neb_fmax",
                converged=False,
                fmax=0.05,
                steps=100,
                actual_steps=100,
            ).to_manifest(),
        ],
    )
    write_artifact_manifest(
        output / "neb_endpoint_serial.json",
        workflow="neb",
        artifacts=[{"role": "trajectory", "path": "neb.traj"}],
        stages=[
            StageRecord(
                name="endpoint_initial_relax",
                role="endpoint",
                criterion="ase_optimizer",
                status="skipped",
            ).to_manifest(),
            StageRecord(
                name="endpoint_final_relax",
                role="endpoint",
                criterion="ase_optimizer",
                converged=True,
                fmax=0.05,
                steps=100,
                actual_steps=12,
            ).to_manifest(),
            StageRecord(
                name="ordinary_neb_warmup", role="warmup", status="skipped"
            ).to_manifest(),
            StageRecord(
                name="ci_neb",
                role="final",
                criterion="neb_fmax",
                converged=True,
                fmax=0.05,
                steps=100,
                actual_steps=64,
            ).to_manifest(),
        ],
    )
    write_artifact_manifest(
        output / "irc_both_directions.json",
        workflow="irc",
        artifacts=[
            {"role": "irc_trajectory", "path": "irc.traj"},
            {"role": "normalized_irc_trajectory", "path": "irc_normalized.traj"},
        ],
        stages=[
            StageRecord(
                name="sella_irc",
                role="final",
                criterion="sella_irc_endpoint",
                direction="forward",
                converged=True,
                fmax=0.03,
                steps=50,
                actual_steps=23,
            ).to_manifest(),
            StageRecord(
                name="sella_irc",
                role="final",
                criterion="sella_irc_endpoint",
                direction="reverse",
                converged=False,
                fmax=0.03,
                steps=50,
                actual_steps=31,
            ).to_manifest(),
        ],
    )
    write_artifact_manifest(
        output / "autoneb_windows.json",
        workflow="autoneb",
        artifacts=[
            {"role": "image_trajectory", "path": f"run_autoneb{index:03d}.traj"}
            for index in range(5)
        ],
        stages=[
            StageRecord(
                name="autoneb_iter",
                role="subset",
                criterion="neb_fmax",
                iteration=1,
                subset=[1, 2, 3],
                converged=True,
                fmax=0.05,
                steps=100,
                actual_steps=100,
            ).to_manifest(),
            StageRecord(
                name="autoneb_iter",
                role="subset",
                criterion="neb_fmax",
                iteration=2,
                subset=[1, 2, 3, 4],
                converged=False,
                fmax=0.05,
                steps=200,
                actual_steps=200,
            ).to_manifest(),
            StageRecord(
                name="autoneb",
                role="final",
                criterion="neb_fmax",
                iteration=2,
                subset=[1, 2, 3, 4],
                converged=False,
                fmax=0.05,
                steps=200,
                actual_steps=200,
            ).to_manifest(),
        ],
    )
    write_artifact_manifest(
        output / "d2s_constituents.json",
        workflow="d2s",
        artifacts=[
            {"role": "rough_neb_trajectory", "path": "neb_rough.traj"},
            {"role": "single_ended_trajectory", "path": "d2s_sella.traj"},
            {"role": "vibration_results", "path": "d2s_vibration.json"},
            {"role": "ts_validation", "path": "d2s_ts_validation.json"},
        ],
        stages=[
            StageRecord(
                name="endpoint_initial_relax",
                role="endpoint",
                criterion="ase_optimizer",
                status="skipped",
            ).to_manifest(),
            StageRecord(
                name="endpoint_final_relax",
                role="endpoint",
                criterion="ase_optimizer",
                converged=True,
                fmax=0.05,
                steps=100,
                actual_steps=20,
            ).to_manifest(),
            StageRecord(
                name="rough_neb",
                role="rough",
                criterion="neb_fmax",
                converged=False,
                fmax=0.1,
                steps=200,
                actual_steps=200,
            ).to_manifest(),
            StageRecord(
                name="sella",
                role="final",
                criterion="sella_projected_force+constraint",
                converged=True,
                fmax=0.05,
                steps=200,
                actual_steps=71,
            ).to_manifest(),
            StageRecord(name="vibration").to_manifest(),
        ],
    )
    write_artifact_manifest(
        output / "api_synthesized.json",
        workflow="sella",
        artifacts=[{"role": "trajectory", "path": "sella.traj"}],
        stages=[StageRecord(name="sella").to_manifest()],
        metadata={"manifest_source": "api_synthesized"},
    )
    legacy = (
        '{\n'
        '  "schema_version": "atst-artifacts-v1",\n'
        '  "workflow": "neb",\n'
        '  "metadata": {},\n'
        '  "stages": [],\n'
        '  "artifacts": [\n'
        '    {\n'
        '      "role": "trajectory",\n'
        '      "path": "neb.traj"\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )
    (output / "legacy_no_stages.json").write_text(legacy, encoding="utf-8")
    legacy_stage = {
        "schema_version": "atst-artifacts-v1",
        "workflow": "vibration",
        "metadata": {},
        "stages": [{"name": "vibration", "status": "complete"}],
        "artifacts": [
            {"role": "vibration_results", "path": "vibration_results.json"}
        ],
    }
    (output / "legacy_stage_without_converged.json").write_text(
        json.dumps(legacy_stage, indent=2) + "\n", encoding="utf-8"
    )
    return sorted(path.name for path in output.glob("*.json"))


def main(argv: list[str] | None = None) -> int:
    """Write the fixture set and print the resulting file names."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Fixture output directory (defaults to the maintained handoff directory).",
    )
    args = parser.parse_args(argv)
    for name in generate(args.output):
        print(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

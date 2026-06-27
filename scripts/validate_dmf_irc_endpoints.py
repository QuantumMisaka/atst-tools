#!/usr/bin/env python
"""Build a DMF IRC endpoint-connection validation report from a manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ruamel.yaml import YAML

from atst_tools.utils.dmf_validation import summarize_irc_endpoint_connection


def load_manifest(path: Path) -> dict:
    """Load a YAML or JSON endpoint-validation manifest."""
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    yaml = YAML(typ="safe")
    return yaml.load(path.read_text(encoding="utf-8"))


def resolve(path: str | Path, root: Path) -> Path:
    """Resolve a manifest path relative to the repository root."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def summarize_manifest(manifest: dict, *, root_dir: Path, output: Path) -> dict:
    """Summarize all IRC endpoint validation cases declared by a manifest."""
    cases = []
    for case in manifest.get("cases", []):
        cases.append(
            summarize_irc_endpoint_connection(
                case_name=case["name"],
                irc_trajectory=resolve(case["irc_trajectory"], root_dir),
                init_structure=resolve(case["init_structure"], root_dir),
                final_structure=resolve(case["final_structure"], root_dir),
                indices=case.get("indices"),
                rmsd_threshold=case.get("rmsd_threshold", manifest.get("rmsd_threshold", 0.25)),
            )
        )
    report = {
        "schema_version": "atst-dmf-irc-endpoint-suite-v1",
        "workflow": "dmf_irc_endpoint_validation_suite",
        "experimental": True,
        "validated_endpoint_connection": bool(cases) and all(case["validated_endpoint_connection"] for case in cases),
        "status": "pass" if cases and all(case["status"] == "pass" for case in cases) else "fail",
        "case_count": len(cases),
        "cases": cases,
    }
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="YAML/JSON manifest declaring IRC endpoint outputs")
    parser.add_argument("--root", type=Path, default=None, help="Repository root; defaults to manifest parent/../..")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON report path")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    root = args.root.resolve() if args.root else args.manifest.resolve().parents[2]
    output = args.output or args.manifest.with_name("dmf_irc_endpoint_report.json")
    report = summarize_manifest(manifest, root_dir=root, output=output)
    print(json.dumps({"status": report["status"], "case_count": report["case_count"]}, indent=2))


if __name__ == "__main__":
    main()

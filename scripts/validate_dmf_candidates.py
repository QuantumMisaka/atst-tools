#!/usr/bin/env python
"""Build a DMF candidate validation report from a manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ruamel.yaml import YAML

from atst_tools.utils.dmf_validation import summarize_manifest


def load_manifest(path: Path) -> dict:
    """Load a YAML or JSON validation manifest."""
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    yaml = YAML(typ="safe")
    return yaml.load(path.read_text(encoding="utf-8"))


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="YAML/JSON manifest declaring DMF candidate outputs")
    parser.add_argument("--root", type=Path, default=None, help="Repository root; defaults to manifest parent/../..")
    parser.add_argument("--output", type=Path, default=None, help="Output JSON report path")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    root = args.root or args.manifest.resolve().parents[2]
    output = args.output or args.manifest.with_name("dmf_validation_report.json")
    summarize_manifest(manifest, root_dir=root, output=output)


if __name__ == "__main__":
    main()

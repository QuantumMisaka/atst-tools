"""Inspect built artifacts for PyDMF licensing and frozen ABACUS audit records."""

from __future__ import annotations

import os
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

import pytest


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "atst_tools" / "external"
AUDIT_FILES = (
    "pydmf/LICENSE",
    "pydmf/UPSTREAM.md",
    "ASE_interface/ABACUSLITE_SNAPSHOT.md",
    "ASE_interface/PATCHES.md",
)
# Import identity is checked by test_backend_routing in the installed-wheel suite.
FORWARDING_MODULES = (
    "abacuslite/core.py",
    "abacuslite/io/generalio.py",
    "abacuslite/io/latestio.py",
    "abacuslite/io/legacyio.py",
    "abacuslite/utils/ksampling.py",
)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("env_var", "archive_type"),
    [("ATST_DIST_SDIST", "sdist"), ("ATST_DIST_WHEEL", "wheel")],
)
def test_distributions_preserve_pydmf_license_and_abacus_audit(
    env_var, archive_type
):
    """Published code archives carry the actual license and source records."""
    if env_var not in os.environ:
        pytest.skip(f"set {env_var} to inspect a built artifact")
    artifact = Path(os.environ[env_var])
    assert artifact.is_file()

    if archive_type == "sdist":
        with tarfile.open(artifact, "r:gz") as archive:
            members = {member.name: member for member in archive.getmembers()}
            prefix = archive.getnames()[0].split("/", 1)[0] + "/src/atst_tools/"
            for relative in AUDIT_FILES:
                source = SOURCE_ROOT / relative
                name = prefix + "external/" + relative
                assert name in members
                assert archive.extractfile(members[name]).read() == source.read_bytes()
            assert prefix + "external/pydmf/dmf/dmf.py" in members
            for relative in FORWARDING_MODULES:
                name = prefix + "external/ASE_interface/" + relative
                assert name in members
    else:
        with zipfile.ZipFile(artifact) as archive:
            members = set(archive.namelist())
            prefix = "atst_tools/external/"
            for relative in AUDIT_FILES:
                source = SOURCE_ROOT / relative
                name = prefix + relative
                assert name in members
                assert archive.read(name) == source.read_bytes()
            assert prefix + "pydmf/dmf/dmf.py" in members
            for relative in FORWARDING_MODULES:
                assert prefix + "ASE_interface/" + relative in members
            metadata_name = next(
                name for name in members if name.endswith(".dist-info/METADATA")
            )
            metadata = Parser().parsestr(archive.read(metadata_name).decode())
            assert metadata["License-Expression"] == "LGPL-3.0-or-later"

    license_text = (SOURCE_ROOT / "pydmf/LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Copyright (c) 2025 Shin-ichi Koda" in license_text
    provenance = (SOURCE_ROOT / "pydmf/UPSTREAM.md").read_text(encoding="utf-8")
    assert "https://github.com/shin1koda/dmf" in provenance
    assert "ed7ed53623e8eaa2e8f57d040b3564a731a67e46" in provenance
    snapshot = (SOURCE_ROOT / "ASE_interface/ABACUSLITE_SNAPSHOT.md").read_text(
        encoding="utf-8"
    )
    assert "70f7ed69b5677c447afdc78e05240e93da660e66" in snapshot
    assert "core.py" in (SOURCE_ROOT / "ASE_interface/PATCHES.md").read_text(
        encoding="utf-8"
    )

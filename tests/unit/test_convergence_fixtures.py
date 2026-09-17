"""Contract tests for the canonical convergence fixtures.

These fixtures are the handoff material for the Paimon consumer. The tests keep
the serialized contract honest: every stage record carries an explicit
tri-state convergence value, AutoNEB keeps its real subset scope, the
synthesized manifest stays "execution complete, convergence unknown", and the
legacy manifest stays readable without inventing records.
"""

from __future__ import annotations

import json
from pathlib import Path


FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "reports"
    / "data"
    / "convergence_fixtures_20260917"
)

EXPECTED_FIXTURES = (
    "api_synthesized.json",
    "autoneb_windows.json",
    "ccqn_null.json",
    "d2s_constituents.json",
    "irc_both_directions.json",
    "legacy_no_stages.json",
    "neb_endpoint_serial.json",
    "neb_two_stage.json",
    "relax_true.json",
    "sella_false.json",
)


def _manifest(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_expected_fixture_set_is_present():
    """The committed fixture set is pinned explicitly (nothing silently missing)."""
    names = sorted(path.name for path in FIXTURES.glob("*.json"))

    assert names == list(EXPECTED_FIXTURES)


def test_every_fixture_is_a_readable_manifest():
    """All fixtures keep the atst-artifacts-v1 envelope."""
    for name in EXPECTED_FIXTURES:
        manifest = _manifest(name)
        assert manifest["schema_version"] == "atst-artifacts-v1", name
        assert isinstance(manifest["workflow"], str) and manifest["workflow"], name
        assert isinstance(manifest["artifacts"], list), name
        assert isinstance(manifest["metadata"], dict), name
        assert isinstance(manifest["stages"], list), name


def test_stage_records_carry_name_status_and_tri_state_convergence():
    """Every recorded stage exposes name/status/converged; converged is tri-state."""
    for name in EXPECTED_FIXTURES:
        for stage in _manifest(name)["stages"]:
            assert set(stage) >= {"name", "status", "converged"}, name
            assert stage["converged"] in (True, False, None), name
            assert stage["status"] in {"complete", "skipped", "failed"}, name


def test_irc_fixture_keeps_one_record_per_direction():
    """IRC stores stage-local facts per executed direction."""
    stages = _manifest("irc_both_directions.json")["stages"]

    assert [stage["direction"] for stage in stages] == ["forward", "reverse"]
    assert all(stage["actual_steps"] for stage in stages)
    assert stages[0]["converged"] is True
    assert stages[1]["converged"] is False


def test_autoneb_final_scope_reuses_the_last_window():
    """The AutoNEB final record never claims whole-band convergence."""
    manifest = _manifest("autoneb_windows.json")
    stages = manifest["stages"]
    iterations = [stage for stage in stages if stage["name"] == "autoneb_iter"]
    final = stages[-1]
    band = range(len(manifest["artifacts"]))

    assert final["name"] == "autoneb"
    assert final["subset"] == iterations[-1]["subset"]
    assert set(final["subset"]) != set(band)
    assert final["converged"] is False


def test_synthesized_manifest_is_explicitly_unknown():
    """API synthesis means execution complete with convergence unknown."""
    manifest = _manifest("api_synthesized.json")

    assert manifest["workflow"] == "sella"
    assert manifest["metadata"]["manifest_source"] == "api_synthesized"
    assert manifest["stages"][0]["name"] == "sella"
    assert manifest["stages"][0]["converged"] is None
    assert manifest["stages"][0]["status"] == "complete"


def test_d2s_fixture_keeps_constituent_identity():
    """D2S aggregates constituent stages without dropping their scope/role."""
    stages = _manifest("d2s_constituents.json")["stages"]
    by_name = {stage["name"]: stage for stage in stages}

    assert by_name["endpoint_initial_relax"]["status"] == "skipped"
    assert by_name["rough_neb"]["converged"] is False
    assert by_name["sella"]["converged"] is True
    assert by_name["vibration"]["status"] == "complete"


def test_legacy_fixture_stays_unknown_instead_of_reconstructed_success():
    """A manifest without stage records must not be back-filled with facts."""
    manifest = _manifest("legacy_no_stages.json")

    assert manifest["stages"] == []

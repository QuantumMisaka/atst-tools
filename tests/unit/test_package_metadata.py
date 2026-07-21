"""Package metadata governance tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import signal
import subprocess
import sys

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[2]


def _project_metadata() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def test_runtime_dependency_policy_is_explicit() -> None:
    """Default install dependencies should be explicit and lightweight."""
    project = _project_metadata()

    assert project["requires-python"] == ">=3.10"
    assert project["dependencies"] == [
        "ase>=3.28.0",
        "numpy>=1.26,<3",
        "scipy>=1.13,<2",
        "pydantic>=2,<3",
        "ruamel.yaml>=0.18,<0.20",
        "seekpath>=2.2,<3",
        "sella>=2.5,<3",
    ]


def test_optional_dependency_groups_cover_feature_specific_stacks() -> None:
    """Heavy or feature-specific stacks should be opt-in extras."""
    optional = _project_metadata()["optional-dependencies"]

    assert optional["plot"] == ["matplotlib>=3.9,<4"]
    assert optional["dp"] == ["deepmd-kit>=3.1.3"]
    assert optional["parallel"] == ["mpi4py>=4.1.2"]
    assert optional["test"] == ["pytest>=8.4,<10"]
    assert optional["release"] == ["build>=1.5,<2", "twine>=6.2,<7"]
    assert optional["dev"] == [
        "pytest>=8.4,<10",
        "build>=1.5,<2",
        "twine>=6.2,<7",
    ]


def test_wheel_release_gate_script_exposes_a_clean_install_check() -> None:
    """Release verification is available without leaving build artifacts in-tree."""
    script = ROOT / "scripts" / "verify_wheel_api.py"

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--wheel" in result.stdout


def test_wheel_release_gate_rejects_source_tree_imports() -> None:
    """The wheel gate must isolate imports from inherited source paths."""
    script = (ROOT / "scripts" / "verify_wheel_api.py").read_text(encoding="utf-8")

    assert "PYTHONPATH" in script
    assert "site.getsitepackages" in script
    assert "atst_tools.__file__" in script
    assert "is_relative_to" in script


def test_wheel_release_gate_runs_the_h2_au_api_fixture_and_has_opt_in_mpi_smoke() -> None:
    """The installed-wheel gate exercises a real public API example path."""
    script = (ROOT / "scripts" / "verify_wheel_api.py").read_text(encoding="utf-8")

    assert "12_ccqn_H2-Au" in script
    assert "ccqn_api_auto_modes.py" in script
    assert "--system-site-packages" in script
    assert "--no-index" in script
    assert "--no-deps" in script
    assert "--force-reinstall" in script
    assert "--mpi-smoke" in script
    assert "mpiexec" in script


def test_wheel_ccqn_example_fixture_installs_only_a_backend_run_patch(
    tmp_path, monkeypatch
) -> None:
    """The example gate keeps the real wheel API while bounding CCQN execution."""
    script = ROOT / "scripts" / "verify_wheel_api.py"
    spec = importlib.util.spec_from_file_location("verify_wheel_api", script)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    monkeypatch.setattr(gate, "H2_AU_API_EXAMPLE", tmp_path / "source")
    (tmp_path / "source").mkdir()

    fixture = gate._copy_h2_au_api_fixture(tmp_path / "workspace")

    patch = (fixture / "sitecustomize.py").read_text(encoding="utf-8")
    assert "from atst_tools.mep.ccqn import AbacusCCQN" in patch
    assert "from atst_tools.utils.artifacts import write_artifact_manifest" in patch
    assert "AbacusCCQN.run = _return_copied_atoms" in patch
    assert "return self.init_Atoms.copy()" in patch
    assert "atst_tools.api" not in patch


def test_wheel_ccqn_example_runs_with_its_isolated_startup_fixture(
    monkeypatch, tmp_path
) -> None:
    """The temporary patch is importable before the real example imports its API."""
    script = ROOT / "scripts" / "verify_wheel_api.py"
    spec = importlib.util.spec_from_file_location("verify_wheel_api", script)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    fixture = tmp_path / "fixture"
    observed = {}

    monkeypatch.setattr(gate, "_copy_h2_au_api_fixture", lambda _: fixture)
    monkeypatch.setattr(
        gate,
        "_run",
        lambda command, **kwargs: observed.update(command=command, **kwargs),
    )

    gate._run_h2_au_api_example(tmp_path / "python", tmp_path / "workspace")

    assert observed == {
        "command": [str(tmp_path / "python"), "ccqn_api_auto_modes.py"],
        "cwd": fixture,
        "environment_overrides": {"PYTHONPATH": str(fixture)},
    }


def test_wheel_mpi_smoke_skips_cleanly_without_a_launcher(
    monkeypatch, capsys, tmp_path
) -> None:
    """The opt-in MPI release gate does not fail environments without mpiexec."""
    script = ROOT / "scripts" / "verify_wheel_api.py"
    spec = importlib.util.spec_from_file_location("verify_wheel_api", script)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    monkeypatch.setattr(gate.shutil, "which", lambda name: None)

    gate._run_mpi_smoke(tmp_path / "python", tmp_path)

    assert capsys.readouterr().out == "MPI smoke skipped: mpiexec is unavailable\n"


def test_wheel_mpi_smoke_exercises_an_image_parallel_failure_gate(
    monkeypatch, tmp_path
) -> None:
    """The release gate must prove root-only MPI failures release every rank."""
    script = ROOT / "scripts" / "verify_wheel_api.py"
    spec = importlib.util.spec_from_file_location("verify_wheel_api", script)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    commands = []
    monkeypatch.setattr(gate.shutil, "which", lambda name: "/test/mpiexec")
    monkeypatch.setattr(
        gate,
        "_run",
        lambda command, **kwargs: commands.append((command, kwargs)),
    )
    monkeypatch.setattr(
        gate,
        "_run_mpi_command",
        lambda command, **kwargs: commands.append((command, kwargs)),
    )

    gate._run_mpi_smoke(tmp_path / "python", tmp_path)

    launcher_command = commands[-1][0]
    smoke = launcher_command[-1]
    assert launcher_command[:4] == ["/test/mpiexec", "-n", "2", str(tmp_path / "python")]
    assert "WorkflowExecutionError" in smoke
    assert "injected root endpoint failure" in smoke
    assert "'type': 'neb'" in smoke
    assert "'type': 'autoneb'" in smoke
    assert "allreduce" in smoke
    assert "class NoopCalculator" in smoke
    assert smoke.index("class NoopCalculator") < smoke.index("NoopCalculator()")


def test_wheel_mpi_command_kills_and_waits_for_the_process_group_on_timeout(
    monkeypatch, tmp_path
) -> None:
    """The MPI launcher must not leave child ranks behind after a timeout."""
    script = ROOT / "scripts" / "verify_wheel_api.py"
    spec = importlib.util.spec_from_file_location("verify_wheel_api", script)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    class HangingProcess:
        pid = 31415
        returncode = None

        def __init__(self):
            self.communicate_calls = 0

        def communicate(self, timeout=None):
            self.communicate_calls += 1
            if timeout is not None:
                raise subprocess.TimeoutExpired(["mpiexec"], timeout)
            self.returncode = -signal.SIGKILL
            return "", ""

    process = HangingProcess()
    popen_calls = []
    monkeypatch.setattr(
        gate.subprocess,
        "Popen",
        lambda command, **kwargs: (popen_calls.append((command, kwargs)) or process),
    )
    killpg_calls = []
    monkeypatch.setattr(gate.os, "killpg", lambda pid, sig: killpg_calls.append((pid, sig)))

    try:
        gate._run_mpi_command(["mpiexec", "-n", "2", "python"], cwd=tmp_path, timeout=3)
    except subprocess.TimeoutExpired:
        pass
    else:
        raise AssertionError("MPI timeout should be propagated after cleanup")

    assert popen_calls[0][1]["start_new_session"] is True
    assert killpg_calls == [(process.pid, signal.SIGKILL)]
    assert process.communicate_calls == 2


def test_wheel_mpi_command_runs_a_real_short_lived_process(tmp_path) -> None:
    """The release helper uses only subprocess.Popen-supported arguments."""
    script = ROOT / "scripts" / "verify_wheel_api.py"
    spec = importlib.util.spec_from_file_location("verify_wheel_api", script)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    gate._run_mpi_command(
        [sys.executable, "-c", "print('short-lived subprocess')"],
        cwd=tmp_path,
        timeout=3,
    )


def test_wheel_mpi_command_reaps_launcher_when_process_group_already_exited(
    monkeypatch, tmp_path
) -> None:
    """A vanished process group must not mask or skip cleanup after timeout."""
    script = ROOT / "scripts" / "verify_wheel_api.py"
    spec = importlib.util.spec_from_file_location("verify_wheel_api", script)
    assert spec is not None and spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)

    class AlreadyExitedProcess:
        pid = 27182
        returncode = None

        def __init__(self):
            self.communicate_calls = 0

        def communicate(self, timeout=None):
            self.communicate_calls += 1
            if timeout is not None:
                raise subprocess.TimeoutExpired(["mpiexec"], timeout)
            self.returncode = -signal.SIGKILL
            return "", ""

    process = AlreadyExitedProcess()
    monkeypatch.setattr(gate.subprocess, "Popen", lambda *args, **kwargs: process)

    def killpg(_pid, _sig):
        raise ProcessLookupError

    monkeypatch.setattr(gate.os, "killpg", killpg)

    try:
        gate._run_mpi_command(["mpiexec", "-n", "2", "python"], cwd=tmp_path, timeout=3)
    except subprocess.TimeoutExpired as error:
        assert error.cmd == ["mpiexec"]
        assert error.timeout == 3
    else:
        raise AssertionError("MPI timeout should be propagated after cleanup")

    assert process.communicate_calls == 2

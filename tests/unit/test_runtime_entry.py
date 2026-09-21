"""Entry-point tests: light imports, worker contract and legacy compatibility."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def _run_python(code: str):
    """Run one snippet in a fresh interpreter with the source tree on sys.path."""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(SRC_ROOT)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=environment,
    )


def test_light_entry_import_does_not_load_the_scientific_stack():
    code = (
        "import sys\n"
        "import atst_tools.scripts.cli\n"
        "import atst_tools.runtime.cli_dispatch\n"
        "heavy = [name for name in ('numpy', 'ase', 'sella', 'deepmd', "
        "'matplotlib', 'jax', 'torch') if name in sys.modules]\n"
        "print(','.join(heavy))\n"
    )
    completed = _run_python(code)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == ""


def test_api_package_resolves_lazily():
    code = (
        "import sys\n"
        "import atst_tools.api as api\n"
        "before = 'numpy' in sys.modules\n"
        "_ = api.RunOptions\n"
        "after_options = 'numpy' in sys.modules\n"
        "_ = api.run_workflow\n"
        "print(before, after_options, 'numpy' in sys.modules)\n"
    )
    completed = _run_python(code)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False False True"


def test_runner_help_exposes_the_runtime_options():
    code = (
        "import runpy, sys\n"
        "sys.argv = ['runner', '--help']\n"
        "try:\n"
        "    runpy.run_module('atst_tools.api.runner', run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
    )
    completed = _run_python(code)
    assert completed.returncode == 0, completed.stderr
    for flag in ("--devices", "--binding", "--threads", "--telemetry"):
        assert flag in completed.stdout


def test_cli_module_entry_point_executes_main():
    code = (
        "import runpy, sys\n"
        "sys.argv = ['atst', '--help']\n"
        "try:\n"
        "    runpy.run_module('atst_tools.scripts.cli', run_name='__main__')\n"
        "except SystemExit as exc:\n"
        "    print('exit', exc.code)\n"
    )
    completed = _run_python(code)
    assert completed.returncode == 0, completed.stderr
    assert "usage: atst" in completed.stdout
    assert "exit 0" in completed.stdout


def test_worker_child_environment_carries_bound_facts(tmp_path):
    """A stand-in worker records the environment the coordinator builds."""
    from atst_tools.runtime import devices as runtime_devices
    from atst_tools.runtime import launch as runtime_launch

    resolution = runtime_devices.resolve_devices(
        runtime_devices.parse_device_tokens([0]),
        environ={"CUDA_VISIBLE_DEVICES": "2,3"},
    )
    request = runtime_launch.merge_runtime_request(
        cli_devices="0", cli_threads="5", environ={}
    )
    child_env = runtime_launch.build_child_environment(
        request,
        resolution,
        base={"CUDA_VISIBLE_DEVICES": "2,3", "PATH": os.environ.get("PATH", "")},
        workflow_dir=tmp_path,
        attempt=1,
    )
    keys = (
        list(runtime_launch.THREAD_ENV_KEYS)
        + list(runtime_launch.CACHE_ENV_KEYS)
        + [
            runtime_devices.CUDA_VISIBLE_DEVICES,
            runtime_devices.RUNTIME_BOUND_ENV,
            runtime_devices.INHERITED_DEVICES_ENV,
            runtime_devices.EFFECTIVE_DEVICES_ENV,
        ]
    )
    script = tmp_path / "standin.py"
    output = tmp_path / "env.json"
    script.write_text(
        "import json, os, sys\n"
        f"keys = {keys!r}\n"
        "payload = {key: os.environ.get(key) for key in keys}\n"
        "payload['argv'] = sys.argv[1:]\n"
        f"open({str(output)!r}, 'w').write(json.dumps(payload))\n",
        encoding="utf-8",
    )
    parent_env = dict(os.environ)
    completed = subprocess.run(
        [sys.executable, str(script), "config.yaml"],
        env=child_env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[runtime_devices.CUDA_VISIBLE_DEVICES] == "2"
    assert payload[runtime_devices.RUNTIME_BOUND_ENV] == "1"
    assert payload[runtime_devices.INHERITED_DEVICES_ENV] == "2,3"
    assert payload[runtime_devices.EFFECTIVE_DEVICES_ENV] == "2"
    assert payload["OMP_NUM_THREADS"] == "5"
    # The frozen contract: all four process-level thread keys carry one value.
    assert {payload[key] for key in runtime_launch.THREAD_ENV_KEYS} == {"5"}
    assert payload["argv"] == ["config.yaml"]
    assert (tmp_path / ".atst_cache" / "attempt-1").is_dir()
    assert dict(os.environ) == parent_env


def test_legacy_atst_run_creates_no_new_artifacts(monkeypatch, tmp_path):
    from atst_tools.scripts import cli
    from atst_tools.scripts import main as run_cli

    config = {
        "calculation": {"type": "relax", "init_structure": "init.stru"},
        "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
    }

    class FakeRelaxWorkflow:
        def __init__(self, config, calc_name, calc_config):
            return None

        def run(self):
            return None

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_cli.ConfigLoader, "load", lambda path: config)
    monkeypatch.setattr(run_cli, "RelaxWorkflow", FakeRelaxWorkflow)

    cli.main(["run", "config.yaml"])

    assert not (tmp_path / "atst_api_result.json").exists()
    assert not (tmp_path / "atst_artifacts.json").exists()


def _record_execute(monkeypatch, recorded):
    """Patch the launch seam so the coordinator does not replace the process."""
    from atst_tools.runtime import cli_dispatch

    def execute(self):
        recorded.append(self)
        raise SystemExit(0)

    monkeypatch.setattr(cli_dispatch.LaunchPlan, "execute", execute)


def test_isolated_atst_run_hands_over_to_the_bound_worker(monkeypatch, tmp_path):
    import pytest

    from atst_tools.runtime import devices as runtime_devices
    from atst_tools.runtime import launch as runtime_launch
    from atst_tools.scripts import cli

    config = tmp_path / "config.yaml"
    config.write_text("runtime:\n  devices: [0]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2,3")
    recorded: list = []
    _record_execute(monkeypatch, recorded)

    with pytest.raises(SystemExit):
        cli.main(["run", str(config)])

    assert len(recorded) == 1
    plan = recorded[0]
    assert plan.environment["CUDA_VISIBLE_DEVICES"] == "2"
    assert plan.environment[runtime_devices.RUNTIME_BOUND_ENV] == "1"
    assert plan.command[1:3] == ["-m", runtime_launch.WORKER_MODULE]


def test_runner_direct_entry_rebinds_before_running(monkeypatch, tmp_path):
    import pytest

    from atst_tools.api import runner

    config = tmp_path / "config.yaml"
    config.write_text("runtime:\n  devices: [1]\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "2,3")
    recorded: list = []
    order: list = []
    _record_execute(monkeypatch, recorded)
    monkeypatch.setattr(runner, "_process_rank", lambda: order.append("rank") or 0)

    with pytest.raises(SystemExit):
        runner.main(["--config", str(config)])

    assert len(recorded) == 1
    assert recorded[0].environment["CUDA_VISIBLE_DEVICES"] == "3"
    # The rank probe imports mpi4py; it must not run before the rebind exec or
    # an OpenMPI rank loses its PMIx session and hangs (review finding 2).
    assert order == []


def test_explicit_calculator_omp_wins_over_the_runtime_budget(monkeypatch):
    from atst_tools.calculators.factory import _effective_omp

    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    assert _effective_omp({"omp": 2}, None) == 2
    assert os.environ["OMP_NUM_THREADS"] == "2"


def test_runtime_thread_budget_survives_an_implicit_calculator_default(monkeypatch):
    from atst_tools.calculators.factory import _effective_omp

    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    monkeypatch.setenv("ATST_THREADS_SOURCE", "explicit")
    assert _effective_omp({}, None) == 8
    assert os.environ["OMP_NUM_THREADS"] == "8"


def test_omp_defaults_to_one_without_any_budget(monkeypatch):
    from atst_tools.calculators.factory import _effective_omp

    monkeypatch.delenv("ATST_THREADS_SOURCE", raising=False)
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    assert _effective_omp({}, None) == 1
    assert os.environ["OMP_NUM_THREADS"] == "1"


def test_legacy_shell_omp_is_not_inherited_without_a_runtime_budget(monkeypatch):
    """Legacy runs keep the historical default of 1 (review F8)."""
    from atst_tools.calculators.factory import _effective_omp

    monkeypatch.delenv("ATST_THREADS_SOURCE", raising=False)
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    assert _effective_omp({}, None) == 1
    assert os.environ["OMP_NUM_THREADS"] == "1"


def test_explicit_omp_override_is_recorded_in_the_evidence(monkeypatch):
    from atst_tools.calculators.factory import _effective_omp
    from atst_tools.runtime import counters

    counters.reset()
    counters.set_enabled(True)
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    monkeypatch.setenv("ATST_THREADS_SOURCE", "explicit")
    assert _effective_omp({"omp": 2}, None) == 2
    assert counters.snapshot().get("runtime_threads_overridden") == 1
    assert counters.gauge_snapshot().get("runtime_threads_effective") == 2.0
    counters.reset()
    counters.set_enabled(False)


def test_runner_direct_entry_resolves_paths_from_the_caller_directory(tmp_path):
    """A relative --config/--workdir pair must survive the worker re-exec.

    The worker replaces the process image before entering the workflow
    directory, so the config must be found relative to the caller's directory.
    Regression: it used to be resolved inside the workdir and failed with
    "Configuration file .../<workdir>/config.yaml not found".
    """
    config = tmp_path / "config.yaml"
    config.write_text(
        "calculation:\n"
        "  type: relax\n"
        "  init_structure: missing_input.traj\n"
        "calculator:\n"
        "  name: abacus\n"
        "  abacus:\n"
        "    parameters: {}\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(SRC_ROOT)
    environment["CUDA_VISIBLE_DEVICES"] = "0"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "atst_tools.api.runner",
            "--config",
            "config.yaml",
            "--workdir",
            "run",
            "--result-json",
            "result.json",
            "--devices",
            "0",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 2, completed.stderr
    payload = json.loads((tmp_path / "run" / "result.json").read_text(encoding="utf-8"))
    message = payload["error"]["message"]
    assert "config.yaml not found" not in message
    assert "missing_input.traj" in message
    assert not (tmp_path / "run" / "run").exists()

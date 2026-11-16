"""ATST-owned ABACUS version probing and external dependency failures."""

import builtins

import pytest

from atst_tools.calculators import abacuslite_backend
from atst_tools.calculators.abacuslite_backend import ATSTAbacusProfile


@pytest.mark.parametrize(
    "error",
    [
        ImportError("external abacuslite internal dependency failed"),
        ModuleNotFoundError(
            "external abacuslite internal dependency failed", name="abacuslite"
        ),
    ],
)
def test_abacuslite_backend_does_not_hide_external_package_import_errors(monkeypatch, error):
    """A broken installed package must report its import failure unchanged."""
    original_import = builtins.__import__
    monkeypatch.setattr(abacuslite_backend, "find_spec", lambda name: object())

    def broken_external_import(name, *args, **kwargs):
        if name == "abacuslite":
            raise error
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_external_import)

    with pytest.raises(ImportError) as excinfo:
        abacuslite_backend._load_abacuslite_backend()
    assert excinfo.value is error


def test_atst_parse_version_accepts_legacy_abacus_version_line():
    """ABACUS <= 3.9 style version output remains supported."""
    assert ATSTAbacusProfile.parse_version("ABACUS version v3.9.0.17\n") == "v3.9.0.17"


def test_atst_parse_version_accepts_banner_abacus_version_line():
    """ATST's profile adapter supports the ABACUS LTS startup banner."""
    stdout = """
                              ABACUS v3.10.1

               Atomic-orbital Based Ab-initio Computation at UStc
"""
    assert ATSTAbacusProfile.parse_version(stdout) == "v3.10.1"


def test_atst_parse_version_reports_unrecognized_output():
    """Unexpected version output should fail with an actionable message."""
    with pytest.raises(RuntimeError):
        ATSTAbacusProfile.parse_version("unrecognized output")


def test_atst_version_uses_bare_executable_for_wrapped_run_command(monkeypatch):
    """Version probing should not run mpirun -np N abacus --version by default."""
    calls = []

    def fake_read_stdout(command):
        calls.append(command)
        return "ABACUS v3.10.1\n"

    monkeypatch.setattr(abacuslite_backend, "read_stdout", fake_read_stdout)

    profile = ATSTAbacusProfile("mpirun -np 4 abacus")

    assert profile.version() == "v3.10.1"
    assert calls == [["abacus", "--version"]]


def test_atst_version_uses_bare_executable_for_full_path_mpirun_wrap(monkeypatch):
    """Probe the engine directly when the MPI launcher uses an absolute path."""
    calls = []

    def fake_read_stdout(command):
        calls.append(command)
        return "ABACUS v3.10.1\n"

    monkeypatch.setattr(abacuslite_backend, "read_stdout", fake_read_stdout)

    profile = ATSTAbacusProfile(
        "/opt/devtools/openmpi/openmpi-5.0.8-nvhpc257-gnu-avx2/bin/mpirun "
        "-np 4 --map-by ppr:4:node:pe=4 --prtemca plm '^slurm' abacus"
    )

    assert profile.version() == "v3.10.1"
    assert calls == [["abacus", "--version"]]


def test_atst_version_uses_bare_executable_for_env_sanitized_command(monkeypatch):
    """Version probing should skip env -u prefixes used for MPI env cleanup."""
    calls = []

    def fake_read_stdout(command):
        calls.append(command)
        return "ABACUS v3.10.1\n"

    monkeypatch.setattr(abacuslite_backend, "read_stdout", fake_read_stdout)

    profile = ATSTAbacusProfile("env -u OMPI_COMM_WORLD_SIZE -u PMIX_RANK abacus")

    assert profile.version() == "v3.10.1"
    assert calls == [["abacus", "--version"]]


@pytest.mark.parametrize(
    ("run_command", "expected_probe"),
    [
        ("/usr/bin/env -u OMPI_COMM_WORLD_SIZE abacus", "abacus"),
        ("/usr/bin/env -u PMIX_RANK /opt/abacus/bin/abacus -n 2",
         "/opt/abacus/bin/abacus"),
    ],
)
def test_atst_version_probe_unwraps_absolute_env_prefix(
    monkeypatch, run_command, expected_probe,
):
    calls = []

    def fake_read_stdout(command):
        calls.append(command)
        return "ABACUS v3.10.1\n"

    monkeypatch.setattr(abacuslite_backend, "read_stdout", fake_read_stdout)
    profile = ATSTAbacusProfile(run_command)
    assert profile.version() == "v3.10.1"
    assert profile.command == run_command
    assert calls == [[expected_probe, "--version"]]


@pytest.mark.parametrize(
    "run_command",
    [
        "srun --job-name abacus /opt/abacus/bin/abacus",
        "mpirun --wdir /scratch/abacus /opt/abacus/bin/abacus",
        "srun -n4 -c8 /opt/abacus/bin/abacus",
        "srun --ntasks-per-node 4 /opt/abacus/bin/abacus",
        "mpirun --tag-output -np 4 /opt/abacus/bin/abacus",
        "mpirun -np 4 -x OMP_NUM_THREADS=8 /opt/abacus/bin/abacus",
        "env -u PMIX_RANK mpirun --tag-output -np 4 /opt/abacus/bin/abacus",
    ],
)
def test_atst_version_probe_keeps_legacy_executable_last_mpi_commands(
    monkeypatch, run_command,
):
    calls = []
    monkeypatch.setattr(
        abacuslite_backend, "read_stdout",
        lambda command: calls.append(command) or "ABACUS v3.10.1\n",
    )

    profile = ATSTAbacusProfile(run_command)

    assert profile.version() == "v3.10.1"
    assert profile.command == run_command
    assert calls == [["/opt/abacus/bin/abacus", "--version"]]


def test_atst_version_command_override_handles_full_mpi_command_with_engine_args(monkeypatch):
    calls = []
    monkeypatch.setattr(
        abacuslite_backend, "read_stdout",
        lambda command: calls.append(command) or "ABACUS v3.10.1\n",
    )
    profile = ATSTAbacusProfile(
        "mpirun --tag-output -np 4 /opt/abacus/bin/abacus -n 2",
        version_command="/opt/abacus/bin/abacus --version",
    )

    assert profile.version() == "v3.10.1"
    assert calls == [["/opt/abacus/bin/abacus", "--version"]]


def test_atst_version_command_override_is_used_verbatim(monkeypatch):
    """Site-specific version probe commands can be configured explicitly."""
    calls = []

    def fake_read_stdout(command):
        calls.append(command)
        return "ABACUS version v3.9.0.17\n"

    monkeypatch.setattr(abacuslite_backend, "read_stdout", fake_read_stdout)

    profile = ATSTAbacusProfile(
        "mpirun -np 4 abacus",
        version_command="srun --partition debug abacus --version",
    )

    assert profile.version() == "v3.9.0.17"
    assert calls == [["srun", "--partition", "debug", "abacus", "--version"]]

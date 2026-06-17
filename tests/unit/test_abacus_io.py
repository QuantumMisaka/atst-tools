import subprocess
import tempfile
from pathlib import Path


def test_run_abacus_check_input_dry_run_writes_inputs_runs_check_and_cleans(monkeypatch, tmp_path):
    from atst_tools.utils import abacus_io

    config_path = tmp_path / "config.yaml"
    config_path.write_text("config\n", encoding="utf-8")
    (tmp_path / "init.stru").write_text("structure\n", encoding="utf-8")
    (tmp_path / "data").mkdir()
    captured = {}

    class FakeGeneralIO:
        @staticmethod
        def write_input(data, filename):
            captured["input"] = dict(data)
            Path(filename).write_text("INPUT\n", encoding="utf-8")
            return filename

        @staticmethod
        def write_kpt(kpts, filename):
            Path(filename).write_text("KPT\n", encoding="utf-8")
            return filename

        @staticmethod
        def write_stru(atoms, output_dir, pseudopotentials, basissets, filename):
            path = Path(output_dir) / filename
            path.write_text("STRU\n", encoding="utf-8")
            return str(path)

    def fake_run(cmd, cwd, env, text, capture_output, timeout):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["omp"] = env["OMP_NUM_THREADS"]
        captured["timeout"] = timeout
        Path(cwd, "OUT.ABACUS").mkdir()
        Path(cwd, "abacus.log").write_text("log\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(abacus_io, "read_structure", lambda path: object())
    monkeypatch.setattr(abacus_io, "_import_generalio", lambda: FakeGeneralIO)
    monkeypatch.setattr(abacus_io.subprocess, "run", fake_run)

    result = abacus_io.run_abacus_check_input_dry_run(
        {
            "calculation": {"type": "relax", "init_structure": "init.stru"},
            "calculator": {
                "name": "abacus",
                "abacus": {
                    "kpts": [1, 1, 1],
                    "parameters": {
                        "calculation": "scf",
                        "pseudo_dir": "./data",
                        "orbital_dir": "./data",
                        "pseudopotentials": {"H": "H.upf"},
                        "basissets": {"H": "H.orb"},
                    },
                },
            },
        },
        str(config_path),
        timeout_sec=9,
        abacus_executable="abacus-lts",
    )

    assert captured["cmd"] == ["abacus-lts", "--check-input"]
    assert captured["omp"] == "1"
    assert captured["timeout"] == 9
    assert captured["input"]["pseudo_dir"] == str((tmp_path / "data").resolve())
    assert captured["input"]["orbital_dir"] == str((tmp_path / "data").resolve())
    assert result["checked"] == 1
    assert not Path(captured["cwd"]).exists()


def test_run_abacus_check_input_dry_run_filters_version_command_from_input(monkeypatch, tmp_path):
    from atst_tools.utils import abacus_io

    config_path = tmp_path / "config.yaml"
    config_path.write_text("config\n", encoding="utf-8")
    (tmp_path / "init.stru").write_text("structure\n", encoding="utf-8")
    captured = {}

    class FakeGeneralIO:
        @staticmethod
        def write_input(data, filename):
            captured["input"] = dict(data)
            Path(filename).write_text("INPUT\n", encoding="utf-8")
            return filename

        @staticmethod
        def write_kpt(kpts, filename):
            Path(filename).write_text("KPT\n", encoding="utf-8")
            return filename

        @staticmethod
        def write_stru(atoms, output_dir, pseudopotentials, basissets, filename):
            path = Path(output_dir) / filename
            path.write_text("STRU\n", encoding="utf-8")
            return str(path)

    def fake_run(cmd, cwd, env, text, capture_output, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(abacus_io, "read_structure", lambda path: object())
    monkeypatch.setattr(abacus_io, "_import_generalio", lambda: FakeGeneralIO)
    monkeypatch.setattr(abacus_io.subprocess, "run", fake_run)

    abacus_io.run_abacus_check_input_dry_run(
        {
            "calculation": {"type": "relax", "init_structure": "init.stru"},
            "calculator": {
                "name": "abacus",
                "abacus": {
                    "version_command": "abacus --version",
                    "parameters": {"calculation": "scf"},
                },
            },
        },
        str(config_path),
    )

    assert captured["input"]["calculation"] == "scf"
    assert "version_command" not in captured["input"]


def test_run_abacus_check_input_dry_run_reports_abacus_failure(monkeypatch, tmp_path):
    from atst_tools.utils import abacus_io

    config_path = tmp_path / "config.yaml"
    config_path.write_text("config\n", encoding="utf-8")
    (tmp_path / "init.stru").write_text("structure\n", encoding="utf-8")

    class FakeGeneralIO:
        @staticmethod
        def write_input(data, filename):
            Path(filename).write_text("INPUT\n", encoding="utf-8")
            return filename

        @staticmethod
        def write_kpt(kpts, filename):
            Path(filename).write_text("KPT\n", encoding="utf-8")
            return filename

        @staticmethod
        def write_stru(atoms, output_dir, pseudopotentials, basissets, filename):
            path = Path(output_dir) / filename
            path.write_text("STRU\n", encoding="utf-8")
            return str(path)

    def fake_run(cmd, cwd, env, text, capture_output, timeout):
        return subprocess.CompletedProcess(cmd, 2, stdout="bad input", stderr="missing pp")

    monkeypatch.setattr(abacus_io, "read_structure", lambda path: object())
    monkeypatch.setattr(abacus_io, "_import_generalio", lambda: FakeGeneralIO)
    monkeypatch.setattr(abacus_io.subprocess, "run", fake_run)

    try:
        abacus_io.run_abacus_check_input_dry_run(
            {
                "calculation": {"type": "relax", "init_structure": "init.stru"},
                "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
            },
            str(config_path),
        )
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ABACUS check-input failure")

    assert "abacus --check-input failed" in message
    assert "bad input" in message
    assert "missing pp" in message


def test_run_abacus_check_input_dry_run_splits_multi_token_abacus_command(monkeypatch, tmp_path):
    from atst_tools.utils import abacus_io

    config_path = tmp_path / "config.yaml"
    config_path.write_text("config\n", encoding="utf-8")
    (tmp_path / "init.stru").write_text("structure\n", encoding="utf-8")
    captured = {}

    class FakeGeneralIO:
        @staticmethod
        def write_input(data, filename):
            Path(filename).write_text("INPUT\n", encoding="utf-8")
            return filename

        @staticmethod
        def write_kpt(kpts, filename):
            Path(filename).write_text("KPT\n", encoding="utf-8")
            return filename

        @staticmethod
        def write_stru(atoms, output_dir, pseudopotentials, basissets, filename):
            path = Path(output_dir) / filename
            path.write_text("STRU\n", encoding="utf-8")
            return str(path)

    def fake_run(cmd, cwd, env, text, capture_output, timeout):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(abacus_io, "read_structure", lambda path: object())
    monkeypatch.setattr(abacus_io, "_import_generalio", lambda: FakeGeneralIO)
    monkeypatch.setattr(abacus_io.subprocess, "run", fake_run)

    abacus_io.run_abacus_check_input_dry_run(
        {
            "calculation": {"type": "relax", "init_structure": "init.stru"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        str(config_path),
        abacus_executable="mpirun -np 4 abacus",
    )

    assert captured["cmd"] == ["mpirun", "-np", "4", "abacus", "--check-input"]


def test_run_abacus_check_input_dry_run_falls_back_when_config_dir_cannot_host_tempdir(monkeypatch, tmp_path):
    from atst_tools.utils import abacus_io

    config_path = tmp_path / "config.yaml"
    config_path.write_text("config\n", encoding="utf-8")
    (tmp_path / "init.stru").write_text("structure\n", encoding="utf-8")
    fallback_root = tmp_path / "fallback"
    fallback_root.mkdir()
    captured = {}
    real_temporary_directory = tempfile.TemporaryDirectory

    class FakeGeneralIO:
        @staticmethod
        def write_input(data, filename):
            Path(filename).write_text("INPUT\n", encoding="utf-8")
            return filename

        @staticmethod
        def write_kpt(kpts, filename):
            Path(filename).write_text("KPT\n", encoding="utf-8")
            return filename

        @staticmethod
        def write_stru(atoms, output_dir, pseudopotentials, basissets, filename):
            path = Path(output_dir) / filename
            path.write_text("STRU\n", encoding="utf-8")
            return str(path)

    def fake_temporary_directory(*args, **kwargs):
        if kwargs.get("dir") == str(tmp_path):
            raise PermissionError("read-only config dir")
        return real_temporary_directory(*args, **kwargs)

    def fake_run(cmd, cwd, env, text, capture_output, timeout):
        captured["cwd"] = cwd
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(abacus_io, "read_structure", lambda path: object())
    monkeypatch.setattr(abacus_io, "_import_generalio", lambda: FakeGeneralIO)
    monkeypatch.setattr(abacus_io.subprocess, "run", fake_run)
    monkeypatch.setattr(abacus_io.tempfile, "TemporaryDirectory", fake_temporary_directory)
    monkeypatch.setattr(abacus_io.tempfile, "gettempdir", lambda: str(fallback_root))

    result = abacus_io.run_abacus_check_input_dry_run(
        {
            "calculation": {"type": "relax", "init_structure": "init.stru"},
            "calculator": {"name": "abacus", "abacus": {"parameters": {}}},
        },
        str(config_path),
    )

    assert result["checked"] == 1
    assert Path(captured["cwd"]).is_relative_to(fallback_root)
    assert not Path(captured["cwd"]).exists()

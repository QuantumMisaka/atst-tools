"""Tests for the MPS probe and the workflow's own CUDA memory fact.

The sampler must never guess: an empty compute-process table stays
``unavailable`` and only gains a reason that names MPS when the probe
actually found an MPS daemon.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import types
from pathlib import Path

from atst_tools.runtime import evidence as runtime_evidence

UUID_A = "GPU-12345678-1234-1234-1234-123456789abc"
MPS_PS_ROW = "root 2545124 1 0 Sep11 ? 00:00:00 nvidia-cuda-mps-server\n"
SSHD_PS_ROW = "root 812 1 0 Sep11 ? 00:00:00 /usr/sbin/sshd -D\n"


def _process_table(tmp_path: Path, cmdlines: dict[int, bytes]) -> Path:
    """Build a fixture process table with one ``cmdline`` file per PID."""
    root = tmp_path / "proc"
    root.mkdir()
    for pid, cmdline in cmdlines.items():
        entry = root / str(pid)
        entry.mkdir()
        (entry / "cmdline").write_bytes(cmdline)
    return root


def _empty_process_table(tmp_path: Path) -> Path:
    """Return a fixture process table without any process in it."""
    root = tmp_path / "proc"
    root.mkdir()
    return root


def _stand_in(*, gpu: str = "", compute: str = "", processes: str = ""):
    """Return a ``subprocess.run`` stand-in keyed by the queried command.

    Every other command (for example the ``uname`` call of
    ``platform.platform``) keeps reaching the real implementation.
    """
    real_run = subprocess.run

    def run(argv, **kwargs):
        if argv[0] == "nvidia-smi":
            queried = gpu if any("--query-gpu" in arg for arg in argv) else compute
            return types.SimpleNamespace(returncode=0, stdout=queried)
        if argv[0] == "ps":
            return types.SimpleNamespace(returncode=0, stdout=processes)
        return real_run(argv, **kwargs)

    return run


def _no_socket(tmp_path: Path) -> Path:
    """Return an MPS socket prefix that does not exist on this host."""
    return tmp_path / "nvidia-mps"


def test_empty_compute_apps_under_mps_name_mps_and_stay_unavailable(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(runtime_evidence, "_PROC_ROOT", _empty_process_table(tmp_path))
    monkeypatch.setattr(runtime_evidence, "MPS_SOCKET_PREFIX", _no_socket(tmp_path))
    monkeypatch.setattr(
        runtime_evidence.subprocess, "run", _stand_in(compute="", processes=MPS_PS_ROW)
    )

    sample = runtime_evidence.sample_compute_processes()

    assert sample["status"] == runtime_evidence.STATUS_UNAVAILABLE
    assert sample["processes"] == []
    assert sample["mps"]["detected"] is True
    assert sample["mps"]["evidence"] == ["nvidia-cuda-mps-server pid 2545124"]
    # The reason keeps the legacy wording and names MPS instead of guessing.
    assert sample["reason"].startswith("no compute process was reported")
    assert "not attributable" in sample["reason"]
    assert "MPS is active" not in sample["reason"]


def test_mps_is_found_in_the_process_table_cmdlines(monkeypatch, tmp_path):
    table = _process_table(
        tmp_path,
        {
            812: b"/usr/sbin/sshd\0-D\0",
            2545124: b"nvidia-cuda-mps-server\0",
        },
    )
    monkeypatch.setattr(runtime_evidence, "_PROC_ROOT", table)
    monkeypatch.setattr(runtime_evidence, "MPS_SOCKET_PREFIX", _no_socket(tmp_path))

    def unexpected(argv, **kwargs):
        raise AssertionError(f"the fallback must not run: {argv!r}")

    monkeypatch.setattr(runtime_evidence.subprocess, "run", unexpected)

    fact = runtime_evidence.probe_mps()

    assert fact["detected"] is True
    assert fact["scope"] == "process-namespace"
    assert "nvidia-cuda-mps-server pid 2545124" in fact["evidence"]
    assert fact["reason"] is None
    assert "ps" not in fact["probes"]


def test_the_mps_socket_path_is_supporting_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_evidence, "_PROC_ROOT", _empty_process_table(tmp_path))
    socket_prefix = tmp_path / "nvidia-mps"
    monkeypatch.setattr(runtime_evidence, "MPS_SOCKET_PREFIX", socket_prefix)
    monkeypatch.setattr(
        runtime_evidence.subprocess, "run", _stand_in(processes=SSHD_PS_ROW)
    )
    socket_prefix.mkdir()

    fact = runtime_evidence.probe_mps()

    assert fact["detected"] is True
    assert f"{socket_prefix} exists" in fact["evidence"]


def test_an_unreadable_probe_is_recorded_as_unknown(monkeypatch, tmp_path):
    table = _process_table(tmp_path, {812: b"/usr/sbin/sshd\0-D\0"})
    # A command line that cannot be read stands in for a hidden or
    # permission-restricted process; a directory fails for every user.
    (table / "813").mkdir()
    (table / "813" / "cmdline").mkdir()
    monkeypatch.setattr(runtime_evidence, "_PROC_ROOT", table)
    monkeypatch.setattr(runtime_evidence, "MPS_SOCKET_PREFIX", _no_socket(tmp_path))

    def failing(argv, **kwargs):
        assert argv[0] == "ps"
        raise FileNotFoundError("ps")

    monkeypatch.setattr(runtime_evidence.subprocess, "run", failing)

    fact = runtime_evidence.probe_mps()

    assert fact["detected"] is None
    assert "could not be executed" in fact["reason"]
    assert fact["probes"]["proc_cmdline"].startswith("partial")
    assert fact["probes"]["ps"].startswith("failed")


def test_missing_tools_only_leave_an_unknown_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_evidence, "_PROC_ROOT", tmp_path / "absent")
    monkeypatch.setattr(runtime_evidence, "MPS_SOCKET_PREFIX", _no_socket(tmp_path))

    def failing(argv, **kwargs):
        if argv[0] == "ps":
            raise FileNotFoundError("ps")
        return types.SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(runtime_evidence.subprocess, "run", failing)

    fact = runtime_evidence.probe_mps()

    assert fact["detected"] is None
    assert fact["evidence"] == []
    assert fact["reason"] and "MPS could not be probed" in fact["reason"]


def test_reported_rows_keep_the_legacy_attribution(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_evidence, "_PROC_ROOT", _empty_process_table(tmp_path))
    monkeypatch.setattr(runtime_evidence, "MPS_SOCKET_PREFIX", _no_socket(tmp_path))
    monkeypatch.setattr(
        runtime_evidence.subprocess,
        "run",
        _stand_in(compute=f"4242, 1024, {UUID_A}\n", processes=SSHD_PS_ROW),
    )

    sample = runtime_evidence.sample_compute_processes()

    assert sample["status"] == runtime_evidence.STATUS_OBSERVED
    assert sample["reason"] is None
    assert sample["source"] == "nvidia-smi"
    assert sample["processes"] == [
        {
            "pid": 4242,
            "used_memory_mib": 1024.0,
            "gpu_uuid": UUID_A,
            "attribution": "reported",
        }
    ]
    assert sample["mps"]["detected"] is False
    assert sample["mps"]["reason"] is None
    assert sample["mps"]["evidence"] == []


def test_an_empty_table_without_mps_keeps_the_legacy_wording(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_evidence, "_PROC_ROOT", _empty_process_table(tmp_path))
    monkeypatch.setattr(runtime_evidence, "MPS_SOCKET_PREFIX", _no_socket(tmp_path))
    monkeypatch.setattr(
        runtime_evidence.subprocess, "run", _stand_in(compute="", processes=SSHD_PS_ROW)
    )

    sample = runtime_evidence.sample_compute_processes()

    assert sample["status"] == runtime_evidence.STATUS_UNAVAILABLE
    assert sample["reason"] == "no compute process was reported"
    assert sample["mps"]["detected"] is False


def test_the_sampler_probes_mps_once_and_records_the_reason(monkeypatch, tmp_path):
    probes: list[str] = []
    original_probe = runtime_evidence.probe_mps

    def counting_probe(*args, **kwargs):
        probes.append("probe")
        return original_probe(*args, **kwargs)

    monkeypatch.setattr(runtime_evidence, "_PROC_ROOT", _empty_process_table(tmp_path))
    monkeypatch.setattr(runtime_evidence, "MPS_SOCKET_PREFIX", _no_socket(tmp_path))
    monkeypatch.setattr(runtime_evidence, "probe_mps", counting_probe)
    monkeypatch.setattr(
        runtime_evidence.subprocess,
        "run",
        _stand_in(
            gpu=f"{UUID_A}, 42, 512, 32768\n", compute="", processes=MPS_PS_ROW
        ),
    )

    session = runtime_evidence.start_session(
        workflow_dir=tmp_path,
        workflow="relax",
        config_runtime={"telemetry": {"enabled": True, "interval_s": 0.05}},
        environ={},
        rank=0,
    )
    assert session is not None
    time.sleep(0.2)  # Let the sampler take more than one sample.
    session.finish("complete")

    payload = json.loads(
        (tmp_path / runtime_evidence.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    sampler = payload["telemetry"]["sampler"]
    assert probes == ["probe"]
    assert sampler["mps"]["detected"] is True
    assert sampler["sample_count"] >= 2
    for sample in sampler["samples"]:
        assert sample["processes"]["mps"]["detected"] is True
        assert "MPS" in sample["processes"]["reason"]


def test_a_disabled_sampler_reports_no_mps_claim(monkeypatch, tmp_path):
    def unexpected(*args, **kwargs):
        raise AssertionError("a disabled sampler must not probe MPS")

    monkeypatch.setattr(runtime_evidence, "probe_mps", unexpected)
    session = runtime_evidence.EvidenceSession(
        workflow_dir=tmp_path,
        workflow="relax",
        attempt=1,
        environ={},
        config_runtime={"telemetry": {"enabled": False}},
        telemetry_enabled=False,
        telemetry_interval_s=1.0,
    )

    assert session.finish("complete") == runtime_evidence.EVIDENCE_FILENAME

    payload = json.loads(
        (tmp_path / runtime_evidence.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    assert payload["telemetry"]["sampler"]["mps"] is None


class _FakeCuda:
    """Stand-in ``torch.cuda`` recording every call it receives."""

    def __init__(
        self, *, initialized: bool = True, peaks: tuple[float, ...] = (512.0,)
    ):
        self.calls: list[str] = []
        self._initialized = initialized
        self._peaks = peaks

    def is_initialized(self) -> bool:
        self.calls.append("is_initialized")
        return self._initialized

    def device_count(self) -> int:
        self.calls.append("device_count")
        return len(self._peaks)

    def max_memory_allocated(self, index: int | None = None) -> float:
        self.calls.append(f"max_memory_allocated({index})")
        return float(self._peaks[index or 0]) * 2**20

    def _forbidden(self, name: str):
        self.calls.append(name)
        raise AssertionError(f"the sampler must not call torch.cuda.{name}")

    def is_available(self):
        return self._forbidden("is_available")

    def init(self):
        return self._forbidden("init")

    def _lazy_init(self):
        return self._forbidden("_lazy_init")

    def current_device(self):
        return self._forbidden("current_device")

    def memory_allocated(self, index: int | None = None):
        return self._forbidden("memory_allocated")


def _install_torch(monkeypatch, cuda: _FakeCuda, *, cuda_build: str | None = "12.9"):
    """Expose a fake ``torch`` module for the duration of one test."""
    torch = types.SimpleNamespace(
        cuda=cuda, version=types.SimpleNamespace(cuda=cuda_build)
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    return torch


def test_self_report_is_null_when_torch_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)

    fact = runtime_evidence.sample_self_memory()

    assert fact["scope"] == "allocator"
    assert fact["source"] == "torch.cuda"
    assert fact["status"] == runtime_evidence.STATUS_UNAVAILABLE
    assert fact["devices"] == []
    assert fact["reason"] and "torch" in fact["reason"]


def test_self_report_is_null_when_cuda_is_not_initialised(monkeypatch):
    cuda = _FakeCuda(initialized=False)
    _install_torch(monkeypatch, cuda, cuda_build="12.9")

    fact = runtime_evidence.sample_self_memory()

    assert fact["status"] == runtime_evidence.STATUS_UNAVAILABLE
    assert fact["devices"] == []
    assert fact["reason"] and "not initialised" in fact["reason"]
    # Reading anything else would have initialised CUDA.
    assert cuda.calls == ["is_initialized"]


def test_self_report_is_null_for_a_cpu_only_build(monkeypatch):
    cuda = _FakeCuda(initialized=False)
    _install_torch(monkeypatch, cuda, cuda_build=None)

    fact = runtime_evidence.sample_self_memory()

    assert fact["status"] == runtime_evidence.STATUS_UNAVAILABLE
    assert fact["devices"] == []
    assert fact["reason"] and "no CUDA support" in fact["reason"]
    assert cuda.calls == ["is_initialized"]


def test_self_report_records_the_allocator_high_water_mark(monkeypatch):
    cuda = _FakeCuda(peaks=(512.0, 256.5))
    _install_torch(monkeypatch, cuda)

    fact = runtime_evidence.sample_self_memory()

    assert fact["status"] == runtime_evidence.STATUS_OBSERVED
    assert fact["reason"] is None
    assert fact["devices"] == [
        {"index": 0, "max_memory_allocated_mib": 512.0},
        {"index": 1, "max_memory_allocated_mib": 256.5},
    ]
    assert cuda.calls == [
        "is_initialized",
        "device_count",
        "max_memory_allocated(0)",
        "max_memory_allocated(1)",
    ]


def test_the_sidecar_records_self_reported_memory_without_initialising_cuda(
    monkeypatch, tmp_path
):
    cuda = _FakeCuda(peaks=(512.0,))
    _install_torch(monkeypatch, cuda)
    session = runtime_evidence.EvidenceSession(
        workflow_dir=tmp_path,
        workflow="relax",
        attempt=1,
        environ={},
        config_runtime=None,
        telemetry_enabled=False,
        telemetry_interval_s=1.0,
    )

    assert session.finish("complete") == runtime_evidence.EVIDENCE_FILENAME

    payload = json.loads(
        (tmp_path / runtime_evidence.EVIDENCE_FILENAME).read_text(encoding="utf-8")
    )
    assert payload["self_reported"]["scope"] == "allocator"
    assert payload["self_reported"]["source"] == "torch.cuda"
    assert payload["self_reported"]["devices"] == [
        {"index": 0, "max_memory_allocated_mib": 512.0}
    ]
    assert cuda.calls == ["is_initialized", "device_count", "max_memory_allocated(0)"]
    limitations = " ".join(payload["limitations"])
    assert "MPS" in limitations
    assert "allocator" in limitations


def test_a_mention_of_the_daemon_name_is_not_evidence(monkeypatch, tmp_path):
    """A command line that only mentions the name must not claim MPS."""
    from atst_tools.runtime import evidence as runtime_evidence

    assert runtime_evidence._mps_names_in("grep nvidia-cuda-mps-server /var/log/x") == []
    assert runtime_evidence._mps_names_in("/usr/bin/nvidia-cuda-mps-server -d") == [
        "nvidia-cuda-mps-server"
    ]

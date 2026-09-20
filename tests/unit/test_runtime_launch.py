"""Behaviour tests for runtime request merging, child env and binding contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from atst_tools.runtime import devices as runtime_devices
from atst_tools.runtime import launch as runtime_launch
from atst_tools.runtime.errors import RuntimeBindingError

UUID_A = "GPU-12345678-1234-1234-1234-123456789abc"


def test_merge_prefers_cli_then_yaml_then_environment():
    request = runtime_launch.merge_runtime_request(
        cli_devices="1",
        yaml_section={"devices": [0], "threads": 4, "binding": "inherit"},
        environ={"ATST_VISIBLE_DEVICES": "3"},
    )
    assert request.devices_source == "--devices"
    assert [token.ordinal for token in request.devices] == [1]
    assert request.threads == 4
    assert request.requested is True

    yaml_only = runtime_launch.merge_runtime_request(
        yaml_section={"devices": [0]}, environ={"ATST_VISIBLE_DEVICES": "3"}
    )
    assert yaml_only.devices_source == "runtime.devices"
    assert [token.ordinal for token in yaml_only.devices] == [0]

    env_only = runtime_launch.merge_runtime_request(
        yaml_section=None, environ={"ATST_VISIBLE_DEVICES": "3"}
    )
    assert env_only.devices_source == "ATST_VISIBLE_DEVICES"
    assert [token.ordinal for token in env_only.devices] == [3]
    assert env_only.requested is True


def test_merge_marks_telemetry_only_sections_as_requested_but_not_rebinding():
    request = runtime_launch.merge_runtime_request(
        yaml_section={"telemetry": {"enabled": True, "interval_s": 2.5}},
        environ={},
    )
    assert request.requested is True
    assert request.rebinds is False
    assert request.telemetry_enabled is True
    assert request.telemetry_interval_s == 2.5

    empty_section = runtime_launch.merge_runtime_request(
        yaml_section={}, environ={}
    )
    assert empty_section.requested is True
    assert empty_section.rebinds is False


def test_threads_auto_follows_the_cpu_affinity_mask(monkeypatch):
    monkeypatch.setattr(runtime_launch, "cpu_affinity_count", lambda: 12)
    auto_request = runtime_launch.merge_runtime_request(
        cli_threads="auto", environ={}
    )
    assert auto_request.threads == 12
    assert auto_request.threads_source == "auto"

    explicit = runtime_launch.merge_runtime_request(cli_threads="3", environ={})
    assert (explicit.threads, explicit.threads_source) == (3, "explicit")

    yaml_auto = runtime_launch.merge_runtime_request(
        yaml_section={"threads": "AUTO"}, environ={}
    )
    assert yaml_auto.threads == 12
    assert yaml_auto.threads_source == "auto"


def test_child_environment_sets_mask_threads_cache_and_facts(tmp_path):
    resolution = runtime_devices.resolve_devices(
        runtime_devices.parse_device_tokens([0]),
        environ={"CUDA_VISIBLE_DEVICES": "2,3"},
    )
    request = runtime_launch.merge_runtime_request(
        cli_devices="0",
        cli_threads="8",
        cli_telemetry=True,
        cli_interval="3",
        environ={},
    )
    env = runtime_launch.build_child_environment(
        request,
        resolution,
        base={"CUDA_VISIBLE_DEVICES": "2,3", "PATH": "/usr/bin"},
        workflow_dir=tmp_path,
        attempt=2,
        log_level="WARNING",
    )

    assert env["CUDA_VISIBLE_DEVICES"] == "2"
    for key in runtime_launch.THREAD_ENV_KEYS:
        assert env[key] == "8"
    cache_dir = tmp_path / ".atst_cache" / "attempt-2"
    assert cache_dir.is_dir()
    for key in runtime_launch.CACHE_ENV_KEYS:
        assert env[key] == str(cache_dir)
    assert env[runtime_devices.RUNTIME_BOUND_ENV] == "1"
    assert env[runtime_devices.INHERITED_DEVICES_ENV] == "2,3"
    assert env[runtime_devices.EFFECTIVE_DEVICES_ENV] == "2"
    assert env[runtime_devices.REQUESTED_DEVICES_ENV] == "0"
    assert env[runtime_devices.REQUESTED_SOURCE_ENV] == "--devices"
    assert env[runtime_devices.BINDING_ENV] == "inherit"
    assert env[runtime_launch.THREADS_SOURCE_ENV] == "explicit"
    assert env[runtime_launch.LOG_LEVEL_ENV] == "WARNING"
    assert env[runtime_launch.TELEMETRY_ENV] == "1"
    assert env[runtime_launch.TELEMETRY_INTERVAL_ENV] == "3.0"
    assert env["PATH"] == "/usr/bin"


def test_child_environment_inherit_leaves_the_caller_mask_untouched():
    resolution = runtime_devices.resolve_devices(
        None, environ={"CUDA_VISIBLE_DEVICES": "2,3"}
    )
    request = runtime_launch.merge_runtime_request(
        yaml_section={"binding": "inherit"}, environ={"CUDA_VISIBLE_DEVICES": "2,3"}
    )
    env = runtime_launch.build_child_environment(
        request, resolution, base={"CUDA_VISIBLE_DEVICES": "2,3"}
    )
    assert env["CUDA_VISIBLE_DEVICES"] == "2,3"
    assert env[runtime_devices.EFFECTIVE_DEVICES_ENV] == "2,3"
    assert runtime_launch.THREAD_ENV_KEYS[0] not in env


def test_worker_command_reuses_the_runner_protocol(tmp_path):
    command = runtime_launch.build_worker_command(
        tmp_path / "config.yaml",
        python="/usr/bin/python",
        workdir=tmp_path,
        restart=True,
        abacus_executable="abacus-custom",
    )
    assert command[0] == "/usr/bin/python"
    assert command[1:3] == ["-m", runtime_launch.WORKER_MODULE]
    assert command[3:5] == ["--config", str(tmp_path / "config.yaml")]
    assert "--workdir" in command
    assert "--restart" in command
    assert command[-2:] == ["--abacus-executable", "abacus-custom"]


def test_attempt_index_parsing():
    assert runtime_launch.attempt_index({}) == 1
    assert runtime_launch.attempt_index({"ATST_ATTEMPT": "3"}) == 3
    assert runtime_launch.attempt_index({"ATST_ATTEMPT": "0"}) == 1
    assert runtime_launch.attempt_index({"ATST_ATTEMPT": "x"}) == 1


def test_ensure_runtime_contract_allows_absent_or_telemetry_only_sections():
    runtime_launch.ensure_runtime_contract({}, environ={})
    runtime_launch.ensure_runtime_contract(
        {"runtime": {"telemetry": {"enabled": True}}}, environ={}
    )
    runtime_launch.ensure_runtime_contract(
        {"runtime": {"binding": "inherit"}}, environ={}
    )


def test_ensure_runtime_contract_refuses_embedded_rebinding():
    with pytest.raises(RuntimeBindingError) as caught:
        runtime_launch.ensure_runtime_contract(
            {"runtime": {"devices": [0]}}, workflow="relax", environ={}
        )
    assert runtime_launch.EMBEDDED_REFUSAL in str(caught.value)

    with pytest.raises(RuntimeBindingError):
        runtime_launch.ensure_runtime_contract(
            {"runtime": {"threads": 4}}, environ={}
        )
    with pytest.raises(RuntimeBindingError):
        runtime_launch.ensure_runtime_contract(
            {"runtime": {"binding": "round_robin"}}, environ={}
        )


def test_ensure_runtime_contract_verifies_bound_facts():
    bound = {
        runtime_devices.RUNTIME_BOUND_ENV: "1",
        runtime_devices.INHERITED_DEVICES_ENV: "2,3",
        runtime_devices.EFFECTIVE_DEVICES_ENV: "2",
        runtime_devices.CUDA_VISIBLE_DEVICES: "2",
    }
    runtime_launch.ensure_runtime_contract(
        {"runtime": {"devices": [0], "threads": 4}}, environ=bound
    )
    mismatched = dict(bound, **{runtime_devices.CUDA_VISIBLE_DEVICES: "3"})
    with pytest.raises(RuntimeBindingError):
        runtime_launch.ensure_runtime_contract(
            {"runtime": {"devices": [0]}}, environ=mismatched
        )


def test_round_robin_is_fail_closed_until_a_verified_pool_exists():
    requested = runtime_devices.parse_device_tokens([0])
    with pytest.raises(RuntimeBindingError) as caught:
        runtime_devices.resolve_devices(
            requested,
            binding="round_robin",
            environ={"CUDA_VISIBLE_DEVICES": "2,3"},
        )
    assert "more than one rank" in str(caught.value)

    with pytest.raises(RuntimeBindingError) as missing_rank:
        runtime_devices.resolve_devices(
            requested,
            binding="round_robin",
            environ={"CUDA_VISIBLE_DEVICES": "2,3", "OMPI_COMM_WORLD_SIZE": "2"},
        )
    assert "detectable local rank" in str(missing_rank.value)

    resolution = runtime_devices.resolve_devices(
        runtime_devices.parse_device_tokens([0, 1]),
        binding="round_robin",
        environ={
            "CUDA_VISIBLE_DEVICES": "2,3",
            "OMPI_COMM_WORLD_SIZE": "2",
            "OMPI_COMM_WORLD_LOCAL_RANK": "1",
        },
    )
    assert resolution.effective == ("3",)
    assert resolution.child_mask == "3"
    assert "round_robin_rank_device" in resolution.notes
    assert resolution.requested == ("0", "1")


def test_round_robin_refuses_multi_node_launcher_shapes():
    with pytest.raises(RuntimeBindingError) as caught:
        runtime_devices.resolve_devices(
            runtime_devices.parse_device_tokens([0, 1]),
            binding="round_robin",
            environ={
                "CUDA_VISIBLE_DEVICES": "2,3",
                "OMPI_COMM_WORLD_SIZE": "4",
                "OMPI_COMM_WORLD_LOCAL_RANK": "1",
                "SLURM_NNODES": "2",
            },
        )
    assert "single-node device pool" in str(caught.value)
    assert runtime_devices.declared_node_count({"SLURM_JOB_NUM_NODES": "3"}) == 3
    assert runtime_devices.declared_node_count({}) == 1


def test_round_robin_survives_the_worker_contract_check():
    """YAML round_robin and the bound worker must agree (review F1)."""
    environ = {
        "CUDA_VISIBLE_DEVICES": "2,3",
        "OMPI_COMM_WORLD_SIZE": "2",
        "OMPI_COMM_WORLD_LOCAL_RANK": "1",
    }
    request = runtime_launch.merge_runtime_request(
        cli_devices="0,1", cli_binding="round_robin", environ=environ
    )
    resolution = runtime_devices.resolve_devices(
        request.devices, binding=request.binding, environ=environ
    )
    assert resolution.effective == ("3",)
    child_env = runtime_launch.build_child_environment(request, resolution, base=environ)
    assert child_env[runtime_devices.BINDING_ENV] == "round_robin"

    yaml_section = {"runtime": {"devices": [0, 1], "binding": "round_robin"}}
    runtime_launch.ensure_runtime_contract(yaml_section, environ=child_env)
    runtime_launch.ensure_runtime_contract({}, environ=child_env)

    wrong_mask = dict(
        child_env, **{runtime_devices.CUDA_VISIBLE_DEVICES: "2"}
    )
    with pytest.raises(RuntimeBindingError):
        runtime_launch.ensure_runtime_contract({}, environ=wrong_mask)


def test_worker_verifies_the_merged_cli_request_not_the_raw_yaml():
    """CLI wins over YAML, so the worker must not reject that combination (review F7)."""
    environ = {"CUDA_VISIBLE_DEVICES": "2,3"}
    request = runtime_launch.merge_runtime_request(
        cli_devices="0", yaml_section={"devices": [1]}, environ=environ
    )
    resolution = runtime_devices.resolve_devices(request.devices, environ=environ)
    assert resolution.effective == ("2",)
    child_env = runtime_launch.build_child_environment(request, resolution, base=environ)

    runtime_launch.ensure_runtime_contract(
        {"runtime": {"devices": [1]}}, environ=child_env
    )

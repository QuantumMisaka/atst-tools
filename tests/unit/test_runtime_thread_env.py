"""Behaviour evidence for the DeepMD-kit thread-budget environment contract.

The claims pinned here are:

* the thread budget covers the DeepMD-kit intra/inter-op parallelism knobs next
  to the historical OMP/BLAS keys, and
* the budget keeps its single source (``runtime.threads`` with ``threads_source``)
  while an absent thread request still never overwrites the caller's own
  scientific configuration.
"""

from __future__ import annotations

import pytest

from atst_tools.runtime import devices as runtime_devices
from atst_tools.runtime import launch as runtime_launch

DP_THREAD_KEYS = (
    "DP_INTRA_OP_PARALLELISM_THREADS",
    "DP_INTER_OP_PARALLELISM_THREADS",
)
HISTORICAL_THREAD_KEYS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


def test_thread_keys_cover_the_deepmd_parallelism_knobs():
    """Both DP knobs join the thread keys and no historical key is dropped."""
    for key in DP_THREAD_KEYS + HISTORICAL_THREAD_KEYS:
        assert key in runtime_launch.THREAD_ENV_KEYS


def test_thread_keys_have_a_single_source_and_no_duplicates():
    """Every thread key is written from one source and listed exactly once."""
    keys = list(runtime_launch.THREAD_ENV_KEYS)
    assert len(keys) == len(set(keys))
    assert keys[: len(HISTORICAL_THREAD_KEYS)] == list(HISTORICAL_THREAD_KEYS)
    assert DP_THREAD_KEYS[0] in keys


def _resolution():
    """Return a child device resolution for the thread-budget cases."""
    return runtime_devices.resolve_devices(
        runtime_devices.parse_device_tokens([0]),
        environ={"CUDA_VISIBLE_DEVICES": "2,3"},
    )


def test_child_environment_budgets_deepmd_parallelism_from_the_same_source(tmp_path):
    """One explicit thread request reaches every key, DP knobs included."""
    request = runtime_launch.merge_runtime_request(
        cli_devices="0", cli_threads="8", environ={}
    )

    env = runtime_launch.build_child_environment(
        request,
        _resolution(),
        base={"CUDA_VISIBLE_DEVICES": "2,3"},
        workflow_dir=tmp_path,
        attempt=1,
    )

    for key in runtime_launch.THREAD_ENV_KEYS:
        assert env[key] == "8"
    assert env[runtime_launch.THREADS_SOURCE_ENV] == "explicit"


def test_auto_threads_reach_the_deepmd_parallelism_knobs(tmp_path, monkeypatch):
    """An affinity-derived budget is spelled the same way as an explicit one."""
    monkeypatch.setattr(runtime_launch, "cpu_affinity_count", lambda: 12)
    request = runtime_launch.merge_runtime_request(cli_threads="auto", environ={})

    env = runtime_launch.build_child_environment(
        request, _resolution(), base={}, workflow_dir=tmp_path, attempt=1
    )

    assert request.threads_source == "auto"
    for key in DP_THREAD_KEYS:
        assert env[key] == "12"
    assert env[runtime_launch.THREADS_SOURCE_ENV] == "auto"


def test_no_thread_request_leaves_the_caller_configuration_untouched(tmp_path):
    """Without ``runtime.threads`` no DP knob is written and OMP stays as given."""
    base = {
        "OMP_NUM_THREADS": "3",
        "DP_INTRA_OP_PARALLELISM_THREADS": "3",
        "CUDA_VISIBLE_DEVICES": "2,3",
    }
    request = runtime_launch.merge_runtime_request(
        yaml_section={"devices": [0]}, environ={"CUDA_VISIBLE_DEVICES": "2,3"}
    )

    env = runtime_launch.build_child_environment(
        request, _resolution(), base=base, workflow_dir=tmp_path, attempt=1
    )

    assert request.threads is None
    assert env["OMP_NUM_THREADS"] == "3"
    assert env["DP_INTRA_OP_PARALLELISM_THREADS"] == "3"
    assert runtime_launch.THREADS_SOURCE_ENV not in env


@pytest.mark.parametrize("key", DP_THREAD_KEYS)
def test_a_thread_request_overwrites_the_inherited_deepmd_budget(key, tmp_path):
    """An explicit request wins over an inherited DP knob value."""
    request = runtime_launch.merge_runtime_request(cli_threads="2", environ={})

    env = runtime_launch.build_child_environment(
        request, _resolution(), base={key: "64"}, workflow_dir=tmp_path, attempt=1
    )

    assert env[key] == "2"

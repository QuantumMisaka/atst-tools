"""Behaviour tests for the runtime device resolver (P0 interface sections 2-4)."""

from __future__ import annotations

import pytest

from atst_tools.runtime import devices as runtime_devices
from atst_tools.runtime import errors as runtime_errors

UUID_A = "GPU-12345678-1234-1234-1234-123456789abc"
UUID_B = "GPU-abcdefab-cdef-abcd-efab-cdefabcdefab"


def test_parse_device_tokens_accepts_scalars_lists_and_uuids():
    assert [t.ordinal for t in runtime_devices.parse_device_tokens(0)] == [0]
    assert [t.ordinal for t in runtime_devices.parse_device_tokens("2")] == [2]
    assert [t.uuid for t in runtime_devices.parse_device_tokens(UUID_A)] == [UUID_A]
    tokens = runtime_devices.parse_device_tokens([0, UUID_A])
    assert [t.raw for t in tokens] == ["0", UUID_A]
    comma_separated = runtime_devices.parse_device_tokens("0, 1")
    assert [token.ordinal for token in comma_separated] == [0, 1]
    mixed = runtime_devices.parse_device_tokens(f"0,{UUID_A}")
    assert [token.raw for token in mixed] == ["0", UUID_A]


def test_parse_device_tokens_rejects_malformed_comma_separated_specs():
    for value in ("0,,1", "0,", ",1", "0,x"):
        with pytest.raises(runtime_errors.RuntimeConfigError):
            runtime_devices.parse_device_tokens(value)


@pytest.mark.parametrize(
    "value,needle",
    [
        ([], "must not be empty"),
        ("", "must not be empty"),
        ([1, 1], "duplicate entries"),
        ([0, "0"], "duplicate entries"),
        ([UUID_A, UUID_A], "duplicate entries"),
        (True, "not a valid 0-based device index"),
        (False, "not a valid 0-based device index"),
        (1.5, "not a valid 0-based device index"),
        (-1, "not a valid 0-based device index"),
        ({"devices": 0}, "device index, GPU UUID or a list of them"),
        ("abc", "not a valid 0-based device index"),
        ("GPU-1234", "not a valid 0-based device index"),
    ],
)
def test_parse_device_tokens_rejects_invalid_requests(value, needle):
    with pytest.raises(runtime_errors.RuntimeConfigError) as caught:
        runtime_devices.parse_device_tokens(value)
    assert needle in str(caught.value)


def test_parse_device_tokens_rejects_mig_selection():
    with pytest.raises(runtime_errors.RuntimeConfigError) as caught:
        runtime_devices.parse_device_tokens("MIG-aa11bb22-cc33-4455-6677-8899aabbccdd")
    assert "does not support MIG device selection" in str(caught.value)


def test_parse_threads_and_binding_rules():
    assert runtime_devices.parse_threads(None) is None
    assert runtime_devices.parse_threads(4) == 4
    for value in (0, -2, True, "4"):
        with pytest.raises(runtime_errors.RuntimeConfigError) as caught:
            runtime_devices.parse_threads(value)
        assert "runtime.threads must be a positive integer" in str(caught.value)
    assert runtime_devices.parse_binding(None) == "inherit"
    assert runtime_devices.parse_binding("round_robin") == "round_robin"
    with pytest.raises(runtime_errors.RuntimeConfigError) as caught:
        runtime_devices.parse_binding("pinned")
    assert "is not one of: inherit, round_robin" in str(caught.value)


def test_parse_allocation_supports_counts_and_token_lists():
    assert runtime_devices.parse_allocation_value(None) is None
    counted = runtime_devices.parse_allocation_value("count=4")
    assert (counted.count, counted.tokens) == (4, None)
    listed = runtime_devices.parse_allocation_value("2, 3, 3")
    assert listed.tokens == ("2", "3")
    assert listed.count == 2
    for value in (
        "count=0",
        "count=abc",
        "",
        "MIG-aa11bb22-cc33-4455-6677-8899aabbccdd",
        "gpu-x",
    ):
        with pytest.raises(runtime_errors.RuntimeConfigError):
            runtime_devices.parse_allocation_value(value)


def test_resolve_inherit_keeps_caller_environment_untouched():
    resolution = runtime_devices.resolve_devices(
        None, environ={"CUDA_VISIBLE_DEVICES": "2,3"}
    )
    assert resolution.caller_bound is True
    assert resolution.inherited == ("2", "3")
    assert resolution.effective == ("2", "3")
    assert resolution.child_mask is None
    assert resolution.allocation_identity == "unknown"


def test_resolve_explicit_empty_cuda_mask_is_zero_devices_not_missing():
    resolution = runtime_devices.resolve_devices(
        None, environ={"CUDA_VISIBLE_DEVICES": ""}
    )
    assert resolution.caller_bound is False
    assert resolution.inherited == ()
    assert resolution.allocation_identity == "unverified"


def test_resolve_narrows_within_caller_bound_mask():
    resolution = runtime_devices.resolve_devices(
        runtime_devices.parse_device_tokens([0]),
        environ={"CUDA_VISIBLE_DEVICES": "2,3"},
    )
    assert resolution.effective == ("2",)
    assert resolution.child_mask == "2"
    assert resolution.allocation_identity == "unverified"
    assert resolution.requested == ("0",)


def test_resolve_maps_logical_index_to_uuid_mask():
    resolution = runtime_devices.resolve_devices(
        runtime_devices.parse_device_tokens([1, 0]),
        environ={"CUDA_VISIBLE_DEVICES": f"{UUID_A},{UUID_B}"},
    )
    assert resolution.effective == (UUID_B, UUID_A)
    assert resolution.child_mask == f"{UUID_B},{UUID_A}"


def test_resolve_rejects_ordinal_outside_inherited_set():
    with pytest.raises(runtime_errors.RuntimeBindingError) as caught:
        runtime_devices.resolve_devices(
            runtime_devices.parse_device_tokens([2]),
            environ={"CUDA_VISIBLE_DEVICES": "2,3"},
        )
    assert "device index 2 is outside the inherited visible set (size 2)" in str(
        caught.value
    )


def test_resolve_rejects_uuid_not_present_in_inherited_mask():
    with pytest.raises(runtime_errors.RuntimeBindingError) as caught:
        runtime_devices.resolve_devices(
            runtime_devices.parse_device_tokens([UUID_A]),
            environ={"CUDA_VISIBLE_DEVICES": UUID_B},
        )
    assert (
        f"explicit device selection is refused: '{UUID_A}' is not part of the "
        "inherited visible set"
    ) in str(caught.value)


def test_resolve_refuses_explicit_selection_when_whole_node_visible_and_unbound():
    with pytest.raises(runtime_errors.RuntimeBindingError) as caught:
        runtime_devices.resolve_devices(
            runtime_devices.parse_device_tokens([0]),
            environ={},
        )
    assert "is not caller-bound and the trusted allocation is unknown" in str(
        caught.value
    )
    assert "explicit device selection is refused" in str(caught.value)


def test_resolve_refuses_when_enumeration_alone_does_not_bound_the_caller():
    with pytest.raises(runtime_errors.RuntimeBindingError):
        runtime_devices.resolve_devices(
            runtime_devices.parse_device_tokens([0]),
            environ={},
            enumerate_devices=lambda: (UUID_A, UUID_B),
        )


def test_resolve_narrows_inside_count_only_allocation_covering_visible_set():
    resolution = runtime_devices.resolve_devices(
        runtime_devices.parse_device_tokens([0]),
        environ={
            "CUDA_VISIBLE_DEVICES": "0,1,2,3",
            "ATST_ALLOCATION_DEVICES": "count=4",
        },
    )
    assert resolution.effective == ("0",)
    assert resolution.allocation_identity == "unverified"
    assert resolution.notes == ("allocation_count_covers_visible_set",)


def test_count_only_allocation_covers_enumeration_without_caller_binding():
    """count=N >= visible set is admissible even on an unbound whole node."""
    resolution = runtime_devices.resolve_devices(
        runtime_devices.parse_device_tokens([0]),
        environ={"ATST_ALLOCATION_DEVICES": "count=4"},
        enumerate_devices=lambda: (UUID_A, UUID_B),
    )
    assert resolution.effective == (UUID_A,)
    assert resolution.allocation_identity == "unverified"


def test_resolve_refuses_count_only_allocation_smaller_than_visible_set():
    with pytest.raises(runtime_errors.RuntimeBindingError) as caught:
        runtime_devices.resolve_devices(
            runtime_devices.parse_device_tokens([0]),
            environ={
                "CUDA_VISIBLE_DEVICES": "0,1,2,3",
                "ATST_ALLOCATION_DEVICES": "count=1",
            },
        )
    assert "exceeds the trusted allocation and device identity is unverified" in str(
        caught.value
    )


def test_resolve_narrows_inside_verified_allocation_tokens():
    resolution = runtime_devices.resolve_devices(
        runtime_devices.parse_device_tokens([0]),
        environ={
            "CUDA_VISIBLE_DEVICES": "2,3",
            "ATST_ALLOCATION_DEVICES": "2,3",
        },
    )
    assert resolution.effective == ("2",)
    assert resolution.allocation_identity == "verified"


def test_resolve_refuses_token_outside_verified_allocation():
    with pytest.raises(runtime_errors.RuntimeBindingError) as caught:
        runtime_devices.resolve_devices(
            runtime_devices.parse_device_tokens([0]),
            environ={
                "CUDA_VISIBLE_DEVICES": "2,3",
                "ATST_ALLOCATION_DEVICES": "3",
            },
        )
    assert "is not part of the trusted allocation" in str(caught.value)


def test_verify_bound_devices_accepts_consistent_facts():
    runtime_devices.verify_bound_devices(
        runtime_devices.parse_device_tokens([0]),
        environ={
            "ATST_INHERITED_DEVICES": "2,3",
            "ATST_EFFECTIVE_DEVICES": "2",
            "CUDA_VISIBLE_DEVICES": "2",
        },
    )


def test_verify_bound_devices_rejects_mismatched_mask_and_missing_facts():
    with pytest.raises(runtime_errors.RuntimeBindingError):
        runtime_devices.verify_bound_devices(
            runtime_devices.parse_device_tokens([0]),
            environ={
                "ATST_INHERITED_DEVICES": "2,3",
                "ATST_EFFECTIVE_DEVICES": "2",
                "CUDA_VISIBLE_DEVICES": "3",
            },
        )
    with pytest.raises(runtime_errors.RuntimeBindingError):
        runtime_devices.verify_bound_devices(
            runtime_devices.parse_device_tokens([0]), environ={}
        )


def test_verify_bound_devices_replays_round_robin_rotation():
    environ = {
        "ATST_INHERITED_DEVICES": "2,3",
        "ATST_EFFECTIVE_DEVICES": "3",
        "CUDA_VISIBLE_DEVICES": "3",
        "OMPI_COMM_WORLD_SIZE": "2",
        "OMPI_COMM_WORLD_LOCAL_RANK": "1",
    }
    runtime_devices.verify_bound_devices(None, environ=environ, binding="round_robin")
    runtime_devices.verify_bound_devices(
        runtime_devices.parse_device_tokens([0, 1]),
        environ=environ,
        binding="round_robin",
    )
    wrong_rank = dict(
        environ, **{"ATST_EFFECTIVE_DEVICES": "2", "CUDA_VISIBLE_DEVICES": "2"}
    )
    with pytest.raises(runtime_errors.RuntimeBindingError):
        runtime_devices.verify_bound_devices(
            None, environ=wrong_rank, binding="round_robin"
        )


def test_round_robin_inherit_respects_the_trusted_allocation():
    """Inherit + round_robin must rotate only inside the allocation (review 1)."""
    environ = {
        "CUDA_VISIBLE_DEVICES": "2,3",
        runtime_devices.ALLOCATION_DEVICES_ENV: "2",
        "OMPI_COMM_WORLD_SIZE": "2",
        "OMPI_COMM_WORLD_LOCAL_RANK": "1",
    }
    resolution = runtime_devices.resolve_devices(
        None, binding="round_robin", environ=environ
    )
    assert resolution.inherited == ("2", "3")
    assert resolution.effective == ("2",)
    assert resolution.allocation_identity == "verified"


def test_round_robin_inherit_refuses_a_count_below_the_visible_set():
    environ = {
        "CUDA_VISIBLE_DEVICES": "2,3",
        runtime_devices.ALLOCATION_DEVICES_ENV: "count=1",
        "OMPI_COMM_WORLD_SIZE": "2",
        "OMPI_COMM_WORLD_LOCAL_RANK": "0",
    }
    with pytest.raises(runtime_errors.RuntimeBindingError) as caught:
        runtime_devices.resolve_devices(None, binding="round_robin", environ=environ)
    assert "exceeds the trusted allocation" in str(caught.value)

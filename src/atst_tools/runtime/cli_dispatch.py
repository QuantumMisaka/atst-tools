"""Light argv planning for the ``atst`` entry point and the API runner.

The planning functions import no scientific stack: they decide whether a
workflow runs through the isolated, bound worker path or the legacy in-process
path (frozen P6/R6 contract in the P0 interface design).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from atst_tools.runtime import devices as _devices
from atst_tools.runtime import launch
from atst_tools.runtime.errors import RuntimeBindingError

CLI_SUBCOMMAND = "run"


@dataclass(frozen=True)
class LaunchPlan:
    """Resolved isolated launch: worker command plus its bound environment."""

    command: list[str]
    environment: dict[str, str]
    resolution: _devices.DeviceResolution
    request: launch.RuntimeRequest

    def execute(self) -> None:
        """Replace the coordinator with the bound worker process."""
        launch.exec_worker(self.command, self.environment)


def _add_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--devices", default=None)
    parser.add_argument("--binding", default=None, choices=("inherit", "round_robin"))
    parser.add_argument("--threads", default=None)
    parser.add_argument(
        "--telemetry", dest="telemetry", action="store_true", default=None
    )
    parser.add_argument("--no-telemetry", dest="telemetry", action="store_false")
    parser.add_argument("--telemetry-interval", dest="telemetry_interval", default=None)


def _has_runtime_options(parsed: argparse.Namespace) -> bool:
    return (
        parsed.devices is not None
        or parsed.binding is not None
        or parsed.threads is not None
        or parsed.telemetry is not None
        or parsed.telemetry_interval is not None
    )


def _cli_parser() -> argparse.ArgumentParser:
    """Mirror of the ``atst run`` surface plus the runtime options."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("config", nargs="?")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-input", action="store_true")
    parser.add_argument("--check-input-timeout", default=None)
    parser.add_argument("--abacus-executable", default=None)
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--list-types", action="store_true")
    parser.add_argument("--show-template", default=None)
    parser.add_argument("--calculator", default=None)
    parser.add_argument("--log-level", default=None)
    _add_runtime_arguments(parser)
    return parser


def _runner_parser() -> argparse.ArgumentParser:
    """Mirror of the ``python -m atst_tools.api.runner`` surface plus runtime."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--config", default=None)
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--result-json", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--check-input", action="store_true")
    parser.add_argument("--check-input-timeout", default=None)
    parser.add_argument("--abacus-executable", default=None)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--profiles", action="store_true")
    parser.add_argument("--plots", action="store_true")
    _add_runtime_arguments(parser)
    return parser


def read_runtime_section(config_path: str | Path | None) -> Mapping[str, Any] | None:
    """Read the raw ``runtime`` YAML section, or ``None`` when absent/unreadable."""
    if config_path is None:
        return None
    try:
        from atst_tools.utils.config import ConfigLoader

        raw = ConfigLoader.load(str(config_path))
    except Exception:
        return None
    if isinstance(raw, Mapping) and "runtime" in raw:
        section = raw["runtime"]
        return section if isinstance(section, Mapping) else {"devices": section}
    return None


def _build_plan(
    *,
    config_path: Path,
    request: launch.RuntimeRequest,
    environ: Mapping[str, str],
    workdir: Path,
    command: list[str],
    log_level: str | None,
) -> LaunchPlan:
    resolution = _devices.resolve_devices(
        request.devices,
        binding=request.binding,
        environ=environ,
        enumerate_devices=_devices.enumerate_visible_devices,
    )
    environment = launch.build_child_environment(
        request,
        resolution,
        base=environ,
        workflow_dir=workdir,
        attempt=launch.attempt_index(environ),
        log_level=log_level,
    )
    return LaunchPlan(
        command=command,
        environment=environment,
        resolution=resolution,
        request=request,
    )


def plan_runtime_launch(
    argv: Sequence[str], *, environ: Mapping[str, str] | None = None
) -> LaunchPlan | None:
    """Plan an isolated ``atst run`` launch, or ``None`` for the legacy path."""
    env = os.environ if environ is None else environ
    args = list(argv)
    if not args or args[0] != CLI_SUBCOMMAND:
        return None
    parsed, extras = _cli_parser().parse_known_args(args[1:])
    if extras and not _has_runtime_options(parsed):
        return None
    if parsed.dry_run or parsed.list_types or parsed.show_template or parsed.check_input:
        return None
    config_path = Path(parsed.config).resolve() if parsed.config else None
    request = launch.merge_runtime_request(
        cli_devices=parsed.devices,
        cli_binding=parsed.binding,
        cli_threads=parsed.threads,
        cli_telemetry=parsed.telemetry,
        cli_interval=parsed.telemetry_interval,
        yaml_section=read_runtime_section(config_path),
        environ=env,
    )
    if not request.requested:
        return None
    if config_path is None:
        raise RuntimeBindingError(
            "atst run requires a configuration path when runtime options are used"
        )
    workdir = Path.cwd()
    command = launch.build_worker_command(
        config_path,
        workdir=workdir,
        restart=bool(parsed.restart),
        abacus_executable=parsed.abacus_executable,
    )
    return _build_plan(
        config_path=config_path,
        request=request,
        environ=env,
        workdir=workdir,
        command=command,
        log_level=parsed.log_level,
    )


def plan_runner_launch(
    argv: Sequence[str],
    *,
    environ: Mapping[str, str] | None = None,
    workdir: Path | None = None,
) -> LaunchPlan | None:
    """Plan a bind-and-re-exec launch for a direct runner invocation.

    Args:
        argv: Raw runner arguments (runtime flags included).
        environ: Environment to plan against; defaults to ``os.environ``.
        workdir: Already-resolved workflow directory; when omitted it is taken
            from ``--workdir`` or the current directory.
    """
    env = os.environ if environ is None else environ
    if env.get(_devices.RUNTIME_BOUND_ENV) == "1":
        return None
    args = list(argv)
    if not args:
        return None
    parsed, extras = _runner_parser().parse_known_args(args)
    if extras and not _has_runtime_options(parsed):
        return None
    if parsed.dry_run:
        return None
    if parsed.config is None:
        return None
    config_path = Path(parsed.config).resolve()
    request = launch.merge_runtime_request(
        cli_devices=parsed.devices,
        cli_binding=parsed.binding,
        cli_threads=parsed.threads,
        cli_telemetry=parsed.telemetry,
        cli_interval=parsed.telemetry_interval,
        yaml_section=read_runtime_section(config_path),
        environ=env,
    )
    if not request.requested:
        return None
    resolved_workdir = (
        Path(workdir).resolve()
        if workdir is not None
        else Path(parsed.workdir or ".").resolve()
    )
    command = [
        command_part
        for command_part in _runner_command_from(parsed, config_path, resolved_workdir)
    ]
    return _build_plan(
        config_path=config_path,
        request=request,
        environ=env,
        workdir=resolved_workdir,
        command=command,
        log_level=None,
    )


def _runner_command_from(
    parsed: argparse.Namespace, config_path: Path, workdir: Path
) -> list[str]:
    """Rebuild the worker argv with absolute paths (no runtime flags).

    The worker replaces this process image while the coordinator may already
    sit inside the workflow directory, so relative paths would resolve against
    the wrong base in the child.
    """
    command = launch.build_worker_command(
        config_path,
        workdir=workdir,
        restart=bool(parsed.restart),
        abacus_executable=parsed.abacus_executable,
    )
    if parsed.result_json:
        command += ["--result-json", str(parsed.result_json)]
    if parsed.check_input:
        command.append("--check-input")
    if parsed.check_input_timeout is not None:
        command += ["--check-input-timeout", str(parsed.check_input_timeout)]
    if parsed.progress:
        command.append("--progress")
    if parsed.profiles:
        command.append("--profiles")
    if parsed.plots:
        command.append("--plots")
    return command

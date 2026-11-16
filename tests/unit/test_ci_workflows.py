"""Validate CI contracts through YAML structure and controlled shell execution."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
GENERAL_TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"
PUBLISH_WORKFLOW = ROOT / ".github" / "workflows" / "publish-pypi.yml"


def _workflow(path):
    # BaseLoader preserves GitHub's `on` key instead of YAML 1.1's boolean alias.
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _action_steps(job, action):
    return [
        step for step in job["steps"]
        if step.get("uses", "").split("@", 1)[0] == action
    ]


def _one_action(job, action):
    steps = _action_steps(job, action)
    assert len(steps) == 1
    return steps[0]


def _python_recorder(tmp_path):
    """Record CI's Python invocations without installing or publishing anything."""
    executable = tmp_path / "bin" / "python"
    executable.parent.mkdir(parents=True)
    executable.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "with open(os.environ['COMMAND_LOG'], 'a') as stream:\n"
        "    stream.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1:3] == ['-m', 'venv']:\n"
        "    target = pathlib.Path(sys.argv[3]) / 'bin' / 'python'\n"
        "    target.parent.mkdir(parents=True, exist_ok=True)\n"
        "    target.symlink_to(pathlib.Path(sys.argv[0]).resolve())\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _run_steps(steps, tmp_path, **environment):
    executable = _python_recorder(tmp_path)
    log = tmp_path / "commands.jsonl"
    env = {
        **os.environ,
        "PATH": f"{executable.parent}{os.pathsep}{os.environ['PATH']}",
        "COMMAND_LOG": str(log),
        **environment,
    }
    for step in steps:
        if "run" in step:
            subprocess.run(
                ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
                cwd=tmp_path, env=env, check=True, capture_output=True, text=True,
            )
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_general_ci_covers_supported_matrix_and_documentation(tmp_path):
    workflow = _workflow(GENERAL_TESTS_WORKFLOW)
    triggers = workflow["on"]
    assert {"pull_request", "push", "workflow_dispatch", "schedule"} <= triggers.keys()
    assert triggers["push"]["branches"] == ["main"]
    job = workflow["jobs"]["test"]
    assert job["strategy"]["matrix"] == {
        "python-version": ["3.10", "3.12"],
        "ase-version": ["3.28.0", "latest"],
    }
    assert _one_action(job, "actions/setup-python")["with"]["python-version"] == (
        "${{ matrix.python-version }}"
    )
    assert any(
        step.get("env", {}).get("ASE_VERSION") == "${{ matrix.ase-version }}"
        for step in job["steps"]
    )
    commands = _run_steps(job["steps"], tmp_path, ASE_VERSION="3.28.0")
    assert ["-m", "pip", "install", "-e", ".[test]"] in commands
    assert ["-m", "pip", "install", "ase==3.28.0"] in commands
    assert ["-m", "pytest", "tests", "-q"] in commands

    docs_job = workflow["jobs"]["documentation-governance"]
    commands = _run_steps(docs_job["steps"], tmp_path / "docs")
    assert ["scripts/check_docs_governance.py"] in commands
    assert workflow["permissions"] == {"contents": "read"}
    for ci_job in workflow["jobs"].values():
        assert ci_job.get("permissions", workflow["permissions"]).get("id-token") != "write"


def test_installed_consumer_runs_and_verifies_the_same_external_report(tmp_path):
    workflow = _workflow(GENERAL_TESTS_WORKFLOW)
    assert "abacuslite_ref" in workflow["on"]["workflow_dispatch"]["inputs"]
    job = workflow["jobs"]["installed-abacuslite-consumer"]
    candidates = [
        step for step in _action_steps(job, "actions/checkout")
        if step.get("with", {}).get("repository") == "QuantumMisaka/abacuslite"
    ]
    assert len(candidates) == 1
    assert candidates[0]["with"]["ref"] == "${{ inputs.abacuslite_ref }}"
    steps = [
        step for step in job["steps"]
        if "scripts/run_abacuslite_consumer.py" in step.get("run", "")
    ]
    assert len(steps) == 1
    runtime = tmp_path / "runtime"
    executable = runtime / "venv-external" / "bin" / "python"
    executable.parent.mkdir(parents=True)
    # The runner's own suite validates installed provenance and report contents.
    executable.symlink_to(tmp_path / "bin" / "python")
    commands = _run_steps(
        steps, tmp_path,
        RUNNER_TEMP=str(runtime), GITHUB_WORKSPACE=str(ROOT),
    )
    runner = str(ROOT / "scripts/run_abacuslite_consumer.py")
    report = str(runtime / "external.json")
    assert commands == [
        [runner, "--atst-root", str(ROOT), "--backend", "external", "--report", report],
        [runner, "--verify-report", report],
    ]


@pytest.mark.parametrize(
    ("event", "ref", "plugin"),
    [
        ("push", "", "abacuslite==1.2.1"),
        ("schedule", "", "abacuslite>=1.2.1,<2"),
        ("workflow_dispatch", "candidate", "candidate-wheel"),
    ],
)
def test_installed_consumer_selects_published_scheduled_or_candidate_plugin(
    tmp_path, event, ref, plugin
):
    job = _workflow(GENERAL_TESTS_WORKFLOW)["jobs"]["installed-abacuslite-consumer"]
    steps = [step for step in job["steps"] if "-m venv" in step.get("run", "")]
    assert len(steps) == 1
    for folder, filename in (("atst-dist", "atst.whl"), ("plugin-dist", "plugin.whl")):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / filename).touch()
    commands = _run_steps(
        steps, tmp_path, RUNNER_TEMP=str(tmp_path),
        GITHUB_EVENT_NAME=event, DISPATCH_REF=ref,
        GITHUB_ENV=str(tmp_path / "github-env"),
    )
    expected = str(tmp_path / "plugin-dist/plugin.whl") if ref else plugin
    plugin_installs = [
        command for command in commands
        if command[:3] == ["-m", "pip", "install"] and "--report" in command
    ]
    assert len(plugin_installs) == 1
    assert plugin_installs[0][-1] == expected
    assert commands[-1] == ["-m", "pip", "check"]


@pytest.mark.parametrize(
    ("event", "dispatch", "push", "expected"),
    [
        ("workflow_dispatch", "v2.3.3", "ignored", "v2.3.3"),
        ("push", "ignored", "v2.3.4", "v2.3.4"),
        ("workflow_dispatch", "main", "v2.3.3", None),
        ("push", "v2.3.3", "v2.3.3; echo unsafe", None),
    ],
)
def test_release_resolver_validates_selected_tag_before_emitting_outputs(
    tmp_path, event, dispatch, push, expected
):
    job = _workflow(PUBLISH_WORKFLOW)["jobs"]["resolve-release"]
    step, = job["steps"]
    assert step["env"] == {
        "DISPATCH_TAG": "${{ inputs.tag }}", "EVENT_NAME": "${{ github.event_name }}",
        "PUSH_TAG": "${{ github.ref_name }}",
    }
    output = tmp_path / "github-output"
    result = subprocess.run(
        ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
        env={**os.environ, "EVENT_NAME": event, "DISPATCH_TAG": dispatch,
             "PUSH_TAG": push, "GITHUB_OUTPUT": str(output)},
        capture_output=True, text=True,
    )
    if expected is None:
        assert result.returncode != 0
        assert not output.exists() or not output.read_text()
    else:
        assert result.returncode == 0
        assert dict(line.split("=", 1) for line in output.read_text().splitlines()) == {
            "tag": expected, "ref": f"refs/tags/{expected}",
        }


def test_release_preflight_validates_source_before_uploading_distributions(tmp_path):
    workflow = _workflow(PUBLISH_WORKFLOW)
    assert workflow["on"]["push"]["tags"] == ["v*"]
    assert set(workflow["on"]["workflow_dispatch"]["inputs"]) == {"tag"}
    jobs = workflow["jobs"]
    resolver = jobs["resolve-release"]
    assert resolver["outputs"] == {
        "tag": "${{ steps.resolve-release.outputs.tag }}",
        "ref": "${{ steps.resolve-release.outputs.ref }}",
    }
    preflight = jobs["release-preflight"]
    assert preflight["needs"] == "resolve-release"
    assert _one_action(preflight, "actions/checkout")["with"]["ref"] == (
        "${{ needs.resolve-release.outputs.ref }}"
    )
    checkout = _one_action(preflight, "actions/checkout")
    assert preflight["steps"].index(checkout) < next(
        index for index, step in enumerate(preflight["steps"]) if "run" in step
    )
    assert any(
        step.get("env", {}).get("RELEASE_TAG") == "${{ needs.resolve-release.outputs.tag }}"
        for step in preflight["steps"]
    )
    upload = _one_action(preflight, "actions/upload-artifact")
    assert upload["with"] == {
        "name": "python-distributions", "path": "dist/*", "if-no-files-found": "error",
    }
    upload_index = preflight["steps"].index(upload)
    assert not any("run" in step for step in preflight["steps"][upload_index + 1:])
    commands = _run_steps(preflight["steps"][:upload_index], tmp_path, RELEASE_TAG="v2.3.3")
    assert commands[-6:] == [
        ["scripts/check_release_readiness.py", "--tag", "v2.3.3"],
        ["-m", "pytest", "tests", "-q"],
        ["scripts/check_docs_governance.py"],
        ["-m", "build"],
        ["-m", "twine", "check", "--strict", "dist/*"],
        ["scripts/verify_wheel_api.py", "--wheel", "dist/*.whl"],
    ]


def test_release_publishes_verified_artifact_with_exclusive_oidc_permission():
    workflow = _workflow(PUBLISH_WORKFLOW)
    jobs = workflow["jobs"]
    publish = jobs["publish"]
    assert publish["needs"] == "release-preflight"
    assert workflow["permissions"] == {"contents": "read"}
    assert publish["permissions"] == {"id-token": "write"}
    assert all(
        job.get("permissions", workflow["permissions"]).get("id-token") != "write"
        for name, job in jobs.items() if name != "publish"
    )
    assert publish["environment"]["name"] == "pypi"
    assert not any("run" in step for step in publish["steps"])
    assert not _action_steps(publish, "actions/checkout")
    download = _one_action(publish, "actions/download-artifact")
    upload = _one_action(jobs["release-preflight"], "actions/upload-artifact")
    assert download["with"]["name"] == upload["with"]["name"]
    assert download["with"]["path"] == "dist"
    publisher = _one_action(publish, "pypa/gh-action-pypi-publish")
    assert publish["steps"].index(download) < publish["steps"].index(publisher)

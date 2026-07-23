# ABACUS Agent ATST API Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move ABACUS Agent from its 1.2.8 ATST CLI subprocess integration to the stable ATST 2.2.0 API runner while preserving every existing ATP Tool, input/output, resource, YAML, MPI, and result-evidence contract.

**Spec:** `/home/james/work/deepmodeling/atst-tools-python-api/docs/superpowers/specs/2026-07-22-abacus-agent-api-runner-design.html`

**Architecture:** Develop in a dedicated app-tools Git worktree from the clean 1.2.8 code baseline. Keep YAML preparation and resource/MPI launch policy in `toolkits/transition_atst.py`, replace only the child command with `python -m atst_tools.api.runner`, validate its JSON handoff, and adapt the manifest into the existing result-evidence path. Update the ATST submodule and SIF pins only after an ATST 2.2.0 commit/tag is available.

**Tech Stack:** Python 3.10+, Adam ATP `Tool`/`@tool_io`, subprocess, JSON/YAML, pytest, adam-cli parser/build, Git submodules, Apptainer Layer 2, Slurm/SAI, AsterFire CLI 0.3.5.

**Development environment:** All local ABACUS Agent inspection, test, parser, build, and validation commands run with `conda run -n abacus-env`. Do not use the login shell's default Python.

## Global Constraints

- Use `/home/james/work/sidereus/app-tools/.worktrees/abacus-atst-api-runner` on branch `codex/abacus-atst-api-runner`; do not modify or clean the primary `/home/james/work/sidereus/app-tools` checkout.
- Base behavior is ABACUS Agent `1.2.8` at the current `abacus-develop` parent-repository commit `fc140ff`; the integration candidate becomes `1.2.9` only after local contract gates pass.
- Preserve the seven current transition Tool classes, direct class metadata, `calltype="python"`, docstrings, arguments, `@tool_io` output keys, resource defaults, YAML format, and result-evidence handoff (spec R5).
- Do not expose the runner JSON as a required Tool argument or a new DAG output. It is an internal tracked/display artifact named `atst_api_result.json`.
- Keep NEB/AutoNEB outer MPI and SAI launcher policy in the Agent; ATST starts no launcher. Keep Sella/CCQN serial and CCQN on the configuration-driven `run_workflow` route.
- Do not advance the submodule to a local-only ATST commit or claim 2.2.0 compatibility before an installable, verifiable ATST 2.2.0 artifact exists.
- Before baseline tests, initialize every recorded Agent submodule recursively. The initial Agent worktree intentionally contains unpopulated gitlinks; this is not a test failure or an API compatibility signal.
- Toolbox upload, cloud-file upload, AsterFire task creation, production upload, tag, push, and release remain separate explicit-authority checkpoints.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `toolbox/ABACUS/toolkits/transition_atst.py` | Runner command construction, JSON validation, existing outer MPI launch, and internal result-path propagation. |
| `toolbox/ABACUS/toolkits/transition_result_evidence.py` | Consume the runner-declared manifest and register the internal result JSON without changing DAG outputs. |
| `toolbox/ABACUS/tests/test_atst_transition_tools.py` | Serial, dry-run, restart, command, outer-MPI, failure, and public Tool behavior. |
| `toolbox/ABACUS/tests/test_transition_result_evidence.py` | JSON/manifest-to-evidence and tracked/display file behavior. |
| `toolbox/ABACUS/abacus_transition_state.py` | Existing Tool classes; only additive internal handoff wiring if required. |
| `toolbox/ABACUS/deps/atst-tools` | Git submodule advanced to the released ATST 2.2.0 commit after the release checkpoint. |
| `toolbox/ABACUS/config/configure.json` | Candidate version `1.2.9` and dependency metadata. |
| `toolbox/ABACUS/container/2.0/shared/abacus-layer2.def.in` | Exact ATST 2.2.0/[parallel] installation and runner smoke. |
| `toolbox/ABACUS/container/2.0/sai/validate_adam_sif.py` | Installed version, runner, API root, mpi4py/OpenMPI, and Agent workflow validation. |
| `toolbox/ABACUS/container/2.0/sai/validate_atst_image_parallel_sif.py` | NEB/AutoNEB runner-based image-parallel validation. |
| `toolbox/ABACUS/container/2.0/docs/PYTHON_DEPENDENCY_AUDIT_20260626.md` | Dependency and `[parallel]` rationale. |
| `toolbox/ABACUS/container/2.0/docs/ADAM_ABACUS_SIF_STATUS.md` | Candidate image build/validation state. |
| `toolbox/ABACUS/demos/demos.json` and `toolbox/ABACUS/demos/strus/atst/` | Existing user-facing transition demo entry and package-relative fixture. |
| `toolbox/ABACUS/docs/guides/release-and-platform-validation.md` | Maintainer validation sequence and rollback rule. |
| `toolbox/ABACUS/docs/tools/transition-state.md` | User-visible behavior, without runner internals becoming user parameters. |
| `toolbox/ABACUS/docs/superpowers/plans/2026-07-22-abacus-agent-atst-api-adoption.md` | In-repository copy of this approved execution plan. |

### Task 0: Create and verify the dedicated Agent worktree

**Files:**
- Create worktree: `/home/james/work/sidereus/app-tools/.worktrees/abacus-atst-api-runner`
- Create branch: `codex/abacus-atst-api-runner`
- No tracked file changes.

**Test strategy:**
- Behavior boundary: the new checkout starts from the 1.2.8 parent commit, contains no unrelated dirty changes, and has an initialized ATST submodule.
- Existing suite to extend: none.
- New test file justification: none.
- Temporary probes: none.

**Interfaces:**
- Consumes: parent repository commit `fc140ff` on `abacus-develop`.
- Produces: the only Agent development directory used by Tasks 1–6.

- [x] **Step 1: Confirm branch/path availability and current isolation**

Run: `git worktree list --porcelain`

Expected: the dedicated worktree exists only at `/home/james/work/sidereus/app-tools/.worktrees/abacus-atst-api-runner`, on `codex/abacus-atst-api-runner` at `fc140ff`.

- [x] **Step 2: Create the worktree without touching the primary checkout**

Run from `/home/james/work/sidereus/app-tools`:

```bash
git worktree add .worktrees/abacus-atst-api-runner -b codex/abacus-atst-api-runner fc140ff
```

Expected: a new branch and checkout at the requested absolute path.

- [x] **Step 3: Initialize the recorded Agent submodules at the 1.2.8 baseline**

Run: `git submodule update --init --recursive`

Expected: `git submodule status --recursive` reports all recorded `toolbox/ABACUS/deps/*` revisions without a leading `-` or `+`; the ATST entry is `ea36eb8...`.

- [x] **Step 4: Verify the clean 1.2.8 baseline**

Run: `conda run -n abacus-env python -c 'import json; print(json.load(open("toolbox/ABACUS/config/configure.json"))["version"])'`

Expected: `1.2.8`.

Run: `conda run -n abacus-env pytest toolbox/ABACUS/tests/test_atst_transition_tools.py toolbox/ABACUS/tests/test_transition_result_evidence.py -q`

Expected: PASS. If it fails, stop and report the baseline failure before implementing.

### Task 1: Replace CLI child commands with the API runner

**Files:**
- Modify: `toolbox/ABACUS/toolkits/transition_atst.py`
- Modify: `toolbox/ABACUS/tests/test_atst_transition_tools.py`

**Test strategy:**
- Behavior boundary: serial, dry-run/check-input, restart, NEB/AutoNEB outer MPI, and prepared-config execution invoke the runner with a fixed internal result path and never invoke `atst_tools.scripts.cli`.
- Existing suite to extend: `tests/test_atst_transition_tools.py` owns the adapter and Tool runtime behavior.
- New test file justification: none.
- Temporary probes: none.

**Interfaces:**
- Consumes: `python -m atst_tools.api.runner --config ... --workdir ... --result-json atst_api_result.json` from the ATST plan.
- Produces: `_build_atst_runner_command()`, `_read_atst_api_result()`, and additive `TransitionWorkflowResult.api_result_path/artifact_manifest_path` fields for Task 2.

- [ ] **Step 1: Write failing command and payload tests**

```python
def test_formal_transition_uses_api_runner_and_preserves_restart(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        result_path = Path(kwargs["cwd"]) / "atst_api_result.json"
        result_path.write_text(json.dumps({
            "schema": "atst-api-result-v1",
            "status": "success",
            "workflow": "sella",
            "is_root": True,
            "workdir": str(Path(kwargs["cwd"]).resolve()),
            "artifact_manifest": str(Path(kwargs["cwd"]) / "atst_artifacts.json"),
            "artifacts": [],
            "metadata": {},
        }), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = transition_atst._run_transition_config_process(
        workflow="sella", calculation={"type": "sella"},
        config_path=tmp_path / "atst_sella.yaml", output_dir=tmp_path,
        normalized_path=tmp_path / "atst_sella.normalized.yaml",
        normalized={"calculation": {"type": "sella"}}, generated=[],
        n_gpu=1, restart=True,
    )

    assert "atst_tools.api.runner" in captured["cmd"]
    assert "atst_tools.scripts.cli" not in captured["cmd"]
    assert "--restart" in captured["cmd"]
    assert result.api_result_path.endswith("atst_api_result.json")
```

Add separate cases for dry-run `--check-input`, API status `error`, malformed JSON, schema mismatch, workflow mismatch, and NEB/AutoNEB command prefix `[launcher, "-np", ranks, ...]`.

- [ ] **Step 2: Run the adapter tests and verify RED**

Run: `conda run -n abacus-env pytest toolbox/ABACUS/tests/test_atst_transition_tools.py -q`

Expected: FAIL because commands still target `atst_tools.scripts.cli` and the result model has no API JSON fields.

- [ ] **Step 3: Implement the minimal runner adapter**

```python
# toolbox/ABACUS/toolkits/transition_atst.py
ATST_API_RESULT_NAME = "atst_api_result.json"


@dataclass
class TransitionWorkflowResult:
    # retain all current fields
    api_result_path: str | None = None
    artifact_manifest_path: str | None = None


def _build_atst_runner_command(
    *, config_path: Path, output_dir: Path, restart: bool,
    dry_run: bool = False, check_input: bool = False,
) -> list[str]:
    cmd = [
        sys.executable, "-m", "atst_tools.api.runner",
        "--config", str(config_path),
        "--workdir", str(output_dir),
        "--result-json", ATST_API_RESULT_NAME,
    ]
    if dry_run:
        cmd.append("--dry-run")
    if check_input:
        cmd.append("--check-input")
    if restart:
        cmd.append("--restart")
    return cmd


def _read_atst_api_result(
    path: Path, *, workflow: str, require_manifest: bool,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"ATST API result unreadable: {path}") from exc
    if payload.get("schema") != "atst-api-result-v1":
        raise RuntimeError("ATST API result schema mismatch")
    if payload.get("status") != "success":
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        raise RuntimeError(f"ATST API runner failed: {error.get('type')}: {error.get('message')}")
    if payload.get("workflow") != workflow:
        raise RuntimeError("ATST API result workflow mismatch")
    manifest = Path(str(payload.get("artifact_manifest", "")))
    if require_manifest and (not manifest.is_absolute() or not manifest.is_file()):
        raise RuntimeError("ATST API result manifest is missing")
    return payload
```

Build the formal and dry-run subprocess commands through this helper. Parse preflight/dry-run results with `require_manifest=False`, because API validation does not claim completed scientific artifacts; parse formal results with `require_manifest=True`. For image-parallel execution, prepend the existing resolved launcher, `-np`, rank count, and `_image_parallel_mpi_args()` to the same runner command. After a formal subprocess exit `0`, include the JSON and declared manifest in `generated_files` and the additive result fields.

- [ ] **Step 4: Run adapter tests and verify GREEN**

Run: `conda run -n abacus-env pytest toolbox/ABACUS/tests/test_atst_transition_tools.py -q`

Expected: PASS with no CLI module command remaining in formal or dry-run adapter assertions.

- [ ] **Step 5: Refactor the test portfolio**

Parameterize serial workflow command cases, keep independent MPI and malformed-payload regressions, and remove tests that assert duplicate command-list construction details. Preserve tests of observable Tool results and resource routing.

Run: `conda run -n abacus-env pytest toolbox/ABACUS/tests/test_atst_transition_tools.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add toolbox/ABACUS/toolkits/transition_atst.py toolbox/ABACUS/tests/test_atst_transition_tools.py
git commit -m "feat(abacus): consume ATST API runner"
```

### Task 2: Adapt runner JSON into existing result evidence

**Files:**
- Modify: `toolbox/ABACUS/toolkits/transition_result_evidence.py`
- Modify: `toolbox/ABACUS/tests/test_transition_result_evidence.py`
- Modify only if required for wiring: `toolbox/ABACUS/abacus_transition_state.py`

**Test strategy:**
- Behavior boundary: evidence uses the absolute manifest declared by the validated runner JSON, tracks the JSON as an internal provenance artifact, and returns exactly the existing four DAG output keys.
- Existing suite to extend: `tests/test_transition_result_evidence.py`.
- New test file justification: none.
- Temporary probes: none.

**Interfaces:**
- Consumes: Task 1 `TransitionWorkflowResult.api_result_path` and `.artifact_manifest_path`.
- Produces: unchanged `publish_outputs({work_dir, config_path, normalized_config_path, result_evidence_file})` plus an internal `atst_api_result` provenance artifact.

- [ ] **Step 1: Write failing evidence contract tests**

```python
def test_transition_evidence_uses_runner_manifest_and_keeps_dag_keys(tmp_path):
    result = SimpleNamespace(
        workflow="sella", status="success", work_dir=str(tmp_path),
        config_path=str(tmp_path / "atst_sella.yaml"),
        normalized_config_path=str(tmp_path / "atst_sella.normalized.yaml"),
        normalized_config={"calculation": {"type": "sella"}},
        api_result_path=str(tmp_path / "atst_api_result.json"),
        artifact_manifest_path=str(tmp_path / "declared_manifest.json"),
    )

    outputs = _publish_transition_evidence(kwargs, result, tool_data, tool="abacus_worker_transition_sella")

    assert set(outputs) == {"work_dir", "config_path", "normalized_config_path", "result_evidence_file"}
    evidence = json.loads((tmp_path / "result_evidence.json").read_text())
    assert any(item["id"] == "atst_api_result" for item in evidence["artifacts"])
    assert any(item["path_rel"] == "declared_manifest.json" for item in evidence["artifacts"])
```

- [ ] **Step 2: Run the evidence suite and verify RED**

Run: `conda run -n abacus-env pytest toolbox/ABACUS/tests/test_transition_result_evidence.py -q`

Expected: FAIL because evidence currently reconstructs the manifest name from normalized YAML and does not register the API result.

- [ ] **Step 3: Implement manifest/result evidence wiring**

Prefer `result.artifact_manifest_path` over YAML reconstruction, falling back only for prepared-only results that have no runner document. Add `result.api_result_path` through `_transition_artifact()` with id `atst_api_result`, role `provenance_manifest`, stage `workflow`, and visibility `agent_digest`. Do not add it to `_DAG_OUTPUT_KEYS` or returned `publish_outputs`.

- [ ] **Step 4: Run Tool and evidence suites and verify GREEN**

Run: `conda run -n abacus-env pytest toolbox/ABACUS/tests/test_atst_transition_tools.py toolbox/ABACUS/tests/test_transition_result_evidence.py -q`

Expected: PASS.

- [ ] **Step 5: Verify ATP Tool contracts before committing**

Run: `conda run -n abacus-env python toolbox/ABACUS/scripts/check_abacus_tool_integrity.py --root toolbox/ABACUS --parser-command "conda run -n abacus-env make -C toolbox/ABACUS ADAM_CLI=adam-cli parse"`

Expected: exit `0`; all seven transition Tools retain their current arguments, direct metadata, and output ports.

- [ ] **Step 6: Commit**

```bash
git add toolbox/ABACUS/toolkits/transition_result_evidence.py toolbox/ABACUS/tests/test_transition_result_evidence.py toolbox/ABACUS/abacus_transition_state.py
git commit -m "feat(abacus): publish ATST API result evidence"
```

### Task 3: Advance the released ATST dependency and SIF contract

**Files:**
- Modify gitlink: `toolbox/ABACUS/deps/atst-tools`
- Modify: `toolbox/ABACUS/config/configure.json`
- Modify: `toolbox/ABACUS/container/2.0/shared/abacus-layer2.def.in`
- Modify: `toolbox/ABACUS/container/2.0/sai/validate_adam_sif.py`
- Modify: `toolbox/ABACUS/container/2.0/sai/validate_atst_image_parallel_sif.py`
- Modify: `toolbox/ABACUS/container/2.0/docs/PYTHON_DEPENDENCY_AUDIT_20260626.md`
- Modify: `toolbox/ABACUS/container/2.0/docs/ADAM_ABACUS_SIF_STATUS.md`
- Modify corresponding dependency/version tests found by `rg -n '2\.1\.3|atst-tools' toolbox/ABACUS/tests toolbox/ABACUS/container/2.0`.

**Test strategy:**
- Behavior boundary: the candidate records and installs exact ATST 2.2.0, has `[parallel]` for image-parallel execution, preserves the same OpenMPI stack, and verifies both stable root imports and runner execution inside the SIF.
- Existing suite to extend: container version and dependency tests plus `validate_adam_sif.py`.
- New test file justification: none.
- Temporary probes: no committed SIF, build log, wheel, token, or generated definition.

**Interfaces:**
- Consumes: a published/reachable ATST 2.2.0 commit/tag and Task 1 runner contract.
- Produces: Agent version `1.2.9` candidate metadata and reproducible SIF validation.

- [ ] **Step 1: Stop at the release dependency checkpoint if ATST 2.2.0 is not reachable**

Run in the submodule: `git fetch --tags origin`.

Then run: `git rev-parse --verify refs/tags/2.2.0^{commit}`.

Expected: one commit hash. If the tag is absent, do not change the gitlink or SIF release pin; report this task as waiting on the ATST release checkpoint while Tasks 1–2 remain reviewable.

- [ ] **Step 2: Write failing version/runner/SIF tests**

Update existing assertions to require `2.2.0`, `atst_tools.api.__all__` with six names, `python -m atst_tools.api.runner --help`, and mpi4py/OpenMPI compatibility. Run those focused tests and confirm they fail against 2.1.3.

- [ ] **Step 3: Advance the submodule and candidate metadata**

Checkout the exact `2.2.0` tag in `toolbox/ABACUS/deps/atst-tools`, stage the parent gitlink, change `config/configure.json` version from `1.2.8` to `1.2.9`, and update its ATST dependency metadata. Pin Layer 2 to `atst-tools[parallel]==2.2.0`; retain the existing mpi4py build against `/opt/devtools/openmpi/openmpi-5.0.8-nvhpc257-gnu-avx512`.

- [ ] **Step 4: Extend SIF validation**

In `validate_adam_sif.py`, assert package version `2.2.0`, exact six-name root API, successful runner `--help`, a temporary serial dry-run result JSON, `pip check`, and existing launcher provenance. Change the image-parallel validator's child command from the CLI module to the API runner and require root-only JSON plus the artifact manifest.

- [ ] **Step 5: Run local dependency, container, and package gates**

Run: `conda run -n abacus-env python3 toolbox/ABACUS/scripts/check_abacus_deps.py`

Expected: exit `0` with ATST 2.2.0 recorded consistently.

Run: `conda run -n abacus-env pytest toolbox/ABACUS/tests -q`

Expected: all tests PASS.

Run: `conda run -n abacus-env python3 toolbox/ABACUS/scripts/check_build_package_contents.py`

Expected: exit `0`; the candidate zip contains required source/submodule content and no credentials, caches, logs, or temporary files.

- [ ] **Step 6: Commit**

```bash
git add toolbox/ABACUS/deps/atst-tools toolbox/ABACUS/config/configure.json toolbox/ABACUS/container/2.0 toolbox/ABACUS/tests
git commit -m "build(abacus): require ATST Tools 2.2.0"
```

### Task 4: Update demo and long-term documentation

**Files:**
- Modify: `toolbox/ABACUS/demos/demos.json`
- Modify only if fixture content must change: `toolbox/ABACUS/demos/strus/atst/`
- Modify: `toolbox/ABACUS/docs/tools/transition-state.md`
- Modify: `toolbox/ABACUS/docs/guides/release-and-platform-validation.md`
- Modify: `toolbox/ABACUS/docs/superpowers/plans/README.md`
- Create: `toolbox/ABACUS/docs/superpowers/plans/2026-07-22-abacus-agent-atst-api-adoption.md`

**Test strategy:**
- Behavior boundary: at least one existing ATST demo remains user-oriented and package-relative; maintainer docs describe the API-runner/SIF/SAI/AsterFire validation order and CLI rollback without exposing internal JSON as a Tool parameter.
- Existing suite to extend: `tests/test_atst_demo_assets.py`, prompt/reference contracts, and `make docs-check`.
- New test file justification: none.
- Temporary probes: none.

**Interfaces:**
- Consumes: exact runner behavior, Agent version, fixture path, and evidence keys from Tasks 1–3.
- Produces: governed Agent documentation and one user-reachable demo path.

- [ ] **Step 1: Add failing demo/documentation contract assertions**

Require the selected demo entry to retain exactly `name`, `description`, `onlineUrl`, `_taskid`, `message`, and `files`; require every fixture to be package-relative and present; reject `runner`, `result JSON`, and `subprocess` from the user message.

- [ ] **Step 2: Run the focused checks and verify RED**

Run: `conda run -n abacus-env pytest toolbox/ABACUS/tests/test_atst_demo_assets.py toolbox/ABACUS/tests/test_prompt_reference_contracts.py -q`

Expected: FAIL on the newly required 1.2.9/API adoption documentation marker or updated demo contract.

- [ ] **Step 3: Update user and maintainer content**

Keep the user prompt scientific and unchanged unless the fixture requires correction. Explain in maintainer documentation that Agent 1.2.9 consumes ATST 2.2.0 through its runner, owns outer MPI/resources/result-evidence, retains a migration-only CLI fallback, and requires local → SIF/SAI → AsterFire dev validation. Copy this approved plan into the Agent plan directory and add its categorized index entry.

- [ ] **Step 4: Run docs and demo checks and verify GREEN**

Run: `conda run -n abacus-env pytest toolbox/ABACUS/tests/test_atst_demo_assets.py toolbox/ABACUS/tests/test_prompt_reference_contracts.py -q`

Expected: PASS.

Run: `conda run -n abacus-env make -C toolbox/ABACUS docs-check`

Expected: exit `0`.

- [ ] **Step 5: Check documentation diff hygiene**

Run: `git diff --check -- toolbox/ABACUS/docs toolbox/ABACUS/demos toolbox/ABACUS/AGENTS.md`

Expected: exit `0`.

- [ ] **Step 6: Commit**

```bash
git add toolbox/ABACUS/demos toolbox/ABACUS/docs
git commit -m "docs(abacus): document ATST API adoption"
```

### Task 5: Run local build and SAI validation gates

**Files:**
- Modify only if the existing validation harness needs runner arguments: `toolbox/ABACUS/container/2.0/sai/validate-atst-image-parallel-sif.sbatch`
- Create governed validation report after jobs finish: `toolbox/ABACUS/docs/reports/atst-api-runner-validation-2026-07.md`
- Modify: `toolbox/ABACUS/docs/reports/README.md`

**Test strategy:**
- Behavior boundary: the 1.2.9 build preserves ATP exposure locally and the candidate SIF completes serial runner, CLI comparison, and image-parallel runner jobs on SAI with ABACUS LTS 3.10.1.
- Existing suite to extend: Adam parser/build, SIF validators, and existing Slurm harness.
- New test file justification: no new unit test; this task generates runtime evidence.
- Temporary probes: Slurm scripts/logs/result directories stay outside tracked source until condensed into the governed report.

**Interfaces:**
- Consumes: Tasks 1–4 and an exact built candidate SIF.
- Produces: local package evidence and SAI job IDs/log summaries required before AsterFire dev upload.

- [ ] **Step 1: Run full local Agent gates**

Run: `conda run -n abacus-env pytest toolbox/ABACUS/tests -q`

Expected: all tests PASS.

Run: `conda run -n abacus-env make -C toolbox/ABACUS ADAM_CLI=adam-cli parse`

Expected: all seven transition Tools and unchanged ports/metadata are present.

Run: `conda run -n abacus-env make -C toolbox/ABACUS build`

Expected: exit `0` and one version-1.2.9 zip.

Run: `conda run -n abacus-env python3 toolbox/ABACUS/scripts/check_build_package_contents.py`

Expected: exit `0`.

- [ ] **Step 2: Build and validate the SIF through the existing container workflow**

Use `container/2.0/sai` and its existing Makefile/sbatch entry, with local-source ATST only for candidate-image development and the exact 2.2.0 release spec for the release-candidate image. Do not build on a login node. Record the build job ID, SIF checksum, installed package versions, `pip check`, MPI paths, and `validate_adam_sif.py` output.

- [ ] **Step 3: Submit the serial API/CLI comparison job**

Submit a GPU Slurm job based on `/opt/sbatch_examples/gpu_abacus.sbatch` using ABACUS LTS 3.10.1 and the H2/Au relax fixture. Run the API runner and retained CLI path in separate work directories with identical YAML; require `ks_solver cusolver`, result JSON/manifest consistency, final-energy capture, and zero exits.

- [ ] **Step 4: Submit the image-parallel Agent job**

Use the existing NEB or AutoNEB fixture with one rank/GPU per interior image or `n_simul`. Source `/opt/sai_config/mps_mapping.d/${SLURM_JOB_PARTITION}.bash`, use the LTS-compatible OpenMPI launcher, and validate root-only JSON, peer termination, manifest, and Agent result-evidence.

- [ ] **Step 5: Collect evidence and update the governed report**

For each job, run `sacct -j "$ATST_JOB_ID" --format=JobID,State,ExitCode` with a task-specific `ATST_JOB_ID`. Record `COMPLETED|0:0`, stdout/stderr conclusions, ABACUS version, MPI paths, JSON/manifest/evidence paths, SIF checksum, and numerical comparison. Add the report to `docs/reports/README.md`; do not commit raw SIFs or bulky calculation outputs.

- [ ] **Step 6: Commit**

```bash
git add toolbox/ABACUS/container/2.0/sai toolbox/ABACUS/docs/reports
git commit -m "test(abacus): validate ATST API runner on SAI"
```

### Task 6: AsterFire dev validation and release readiness

**Files:**
- Modify the Task 5 report with authorized platform evidence: `toolbox/ABACUS/docs/reports/atst-api-runner-validation-2026-07.md`
- No credentials or profile files are tracked.

**Test strategy:**
- Behavior boundary: the exact locally validated 1.2.9 zip is visible in the AsterFire dev profile and completes the selected existing demo with correct tool steps and file handoff.
- Existing suite to extend: none; platform evidence is captured in the governed report.
- New test file justification: none.
- Temporary probes: cloud file IDs and task IDs are recorded only as non-secret evidence; local upload responses stay outside source.

**Interfaces:**
- Consumes: Task 5 candidate zip, selected demo fixture/message, and explicit authorization for upload and task creation.
- Produces: dev-platform evidence required for release readiness; it does not authorize production publication.

- [ ] **Step 1: Perform read-only readiness checks**

```bash
command -v asterfire
asterfire version --json
ASTERFIRE_DEV_HOME=/home/james/.local/share/asterfire/profiles/dev-home
HOME="$ASTERFIRE_DEV_HOME" asterfire me --json
HOME="$ASTERFIRE_DEV_HOME" asterfire toolboxes list --json
```

Expected: CLI `0.3.5`, authenticated dev identity, and readable toolbox list.

- [ ] **Step 2: Pause for explicit upload/task authorization**

Report the exact zip path/hash, fixture path, demo message, dev profile, and commands. Do not continue until the user explicitly authorizes toolbox upload, cloud upload, and task creation.

- [ ] **Step 3: Upload the exact candidate and verify its identity**

Run after authorization: `HOME="$ASTERFIRE_DEV_HOME" asterfire toolboxes upload "$ABACUS_AGENT_ZIP" --json`.

Expected: the response and subsequent toolbox list identify ABACUS version `1.2.9`, matching `config/configure.json` and the local zip hash.

- [ ] **Step 4: Upload the current fixture and create the existing demo task**

Use `asterfire cloud upload "$ATST_DEMO_FIXTURE" --id-only`, then `asterfire tasks create --toolbox ABACUS --message "$ATST_DEMO_MESSAGE" --file "$ATST_FILE_ID" --json` under the dev HOME. Do not reuse old `onlineUrl` or `_taskid` as current evidence.

- [ ] **Step 5: Poll to terminal state and audit the result**

Use `asterfire tasks status "$ATST_TASK_ID" --json` until terminal, then `asterfire tasks get "$ATST_TASK_ID" --json`. Require successful transition Tool steps, final scientific reply, and retrievable result JSON, artifact manifest, and result-evidence handoff. A running task or CLI connectivity alone is not a pass.

- [ ] **Step 6: Record evidence and commit the report update**

```bash
git add toolbox/ABACUS/docs/reports/atst-api-runner-validation-2026-07.md
git commit -m "docs(abacus): record ATST API dev validation"
```

## Release Checkpoint

After independent review and fresh execution of local, parser, build, dependency, SIF, SAI, and authorized AsterFire dev gates, the branch is eligible for the repository's normal merge/release decision. Production Toolbox upload, image publication, Git push/tag, and production task creation are separate actions and require separate explicit authorization.

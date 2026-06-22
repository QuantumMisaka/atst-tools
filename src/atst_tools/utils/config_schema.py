"""Pydantic schemas for ATST-Tools YAML configuration."""

from __future__ import annotations

from types import UnionType
from typing import Annotated, Any, Dict, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

VALID_CALCULATION_TYPES = (
    "neb",
    "autoneb",
    "dimer",
    "sella",
    "ccqn",
    "d2s",
    "relax",
    "vibration",
    "irc",
    "md",
    "dmf",
)
VALID_CALCULATORS = ("abacus", "dp", "deepmd")


class StrictConfig(BaseModel):
    """Base model for governed YAML sections."""

    model_config = ConfigDict(extra="forbid")


class NEBMakeConfig(StrictConfig):
    """Configuration for generating an initial NEB chain inside `atst run`."""

    init_structure: str = Field(description="Initial-state structure file.")
    final_structure: str = Field(description="Final-state structure file.")
    n_images: int = Field(gt=0, description="Number of intermediate NEB images, excluding endpoints.")
    method: Literal["IDPP", "linear"] = Field(default="IDPP", description="Interpolation method.")
    output: str = Field(default="init_neb_chain.traj", description="Generated chain trajectory path.")
    ts_guess: str | None = Field(default=None, description="Optional transition-state guess for segmented interpolation.")
    fix: str | Dict[str, Any] | None = Field(default=None, description="Optional fixed-atom rule, e.g. HEIGHT:DIR.")
    magmom: str | Dict[str, float] | None = Field(default=None, description="Optional magnetic moments by element.")
    no_align: bool = Field(default=False, description="Disable atom-index alignment before interpolation.")
    format: str | None = Field(default=None, description="Optional ASE input format override.")


class NEBEndpointOptimizationConfig(StrictConfig):
    """Ordinary NEB endpoint optimization configuration."""

    enabled: bool = Field(default=False, description="Relax endpoints before ordinary NEB.")
    skip_if_has_results: bool = Field(default=True, description="Skip endpoints that already have energy and forces.")
    fmax: float = Field(default=0.05, gt=0, description="Endpoint optimization force threshold.")
    max_steps: int = Field(default=100, gt=0, description="Endpoint optimization step limit.")


class NEBCalculation(StrictConfig):
    """Nudged elastic band workflow configuration."""

    type: Literal["neb"] = Field(description="Select the ordinary NEB or DyNEB workflow.")
    init_chain: str | None = Field(default=None, description="Initial NEB chain trajectory.")
    make: NEBMakeConfig | None = Field(default=None, description="Nested chain generation configuration.")
    trajectory: str = Field(default="neb.traj", description="NEB trajectory output.")
    artifact_manifest: str = Field(default="atst_artifacts.json", description="Workflow artifact manifest JSON output.")
    restart: bool = Field(default=False, description="Restart from the latest complete trajectory band.")
    climb: bool = Field(default=True, description="Enable climbing-image NEB.")
    two_stage: bool = Field(default=False, description="Run a short ordinary NEB warm-up before CI-NEB.")
    stage1_steps: Annotated[int, Field(gt=0)] | None = Field(
        default=20,
        description=(
            "Maximum ordinary NEB warm-up steps for two-stage NEB; the warm-up "
            "stops when stage1_fmax is reached or this step limit is exhausted. "
            "Null uses the ASE optimizer default step limit."
        ),
    )
    stage1_fmax: float = Field(default=0.20, gt=0, description="Force threshold for ordinary NEB warm-up.")
    fmax: float = Field(default=0.05, gt=0, description="Force convergence threshold in eV/Ang.")
    k: float | list[float] = Field(default=0.1, description="NEB spring constant(s) in eV/Ang^2.")
    algorism: str = Field(default="improvedtangent", description="ASE NEB tangent method.")
    neb_backend: Literal["atst", "ase"] = Field(
        default="atst",
        description="NEB implementation backend: ATST compatibility wrapper or native ASE.",
    )
    parallel: bool = Field(default=True, description="Enable image-level parallelism when MPI is available.")
    max_steps: int = Field(default=100, gt=0, description="Maximum optimizer steps.")
    optimizer: str = Field(default="FIRE", description="ASE optimizer name.")
    optimizer_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments forwarded to the ASE optimizer constructor.",
    )
    endpoint_singlepoint: Literal["auto", "always", "never"] = Field(
        default="auto",
        description="Endpoint result policy before NEB starts.",
    )
    endpoint_optimization: NEBEndpointOptimizationConfig = Field(
        default_factory=NEBEndpointOptimizationConfig,
        description="Optional endpoint relaxation before ordinary NEB.",
    )

    @field_validator("k")
    @classmethod
    def _validate_k(cls, value: float | list[float]) -> float | list[float]:
        values = value if isinstance(value, list) else [value]
        if any(float(item) <= 0 for item in values):
            raise ValueError("calculation.k must be positive")
        return value

    @model_validator(mode="after")
    def _validate_chain_source(self) -> "NEBCalculation":
        if bool(self.init_chain) == bool(self.make):
            raise ValueError("calculation.type=neb requires exactly one of 'init_chain' or 'make'")
        return self


class AutoNEBCalculation(StrictConfig):
    """AutoNEB workflow configuration."""

    type: Literal["autoneb"] = Field(description="Select the AutoNEB workflow.")
    init_chain: str = Field(description="Initial NEB chain trajectory.")
    prefix: str = Field(default="run_autoneb", description="AutoNEB per-image output prefix.")
    n_simul: Annotated[int, Field(gt=0)] | None = Field(
        default=None,
        description="Number of images optimized simultaneously.",
    )
    n_max: int = Field(default=10, gt=1, description="Maximum number of AutoNEB images.")
    algorism: str = Field(default="improvedtangent", description="ASE NEB tangent method.")
    neb_backend: Literal["atst", "ase"] = Field(
        default="atst",
        description="AutoNEB implementation backend: ATST compatibility wrapper or native ASE.",
    )
    parallel: bool = Field(default=True, description="Enable image-level parallelism when MPI is available.")
    optimizer: Literal["FIRE", "BFGS"] = Field(default="FIRE", description="Optimizer used for AutoNEB iterations.")
    optimizer_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments forwarded to the ASE optimizer constructor.",
    )
    fmax: float | list[float] = Field(default=0.05, description="Force threshold or AutoNEB threshold schedule.")
    maxsteps: int | list[int] = Field(default=100, description="Maximum optimizer steps per AutoNEB iteration or two-stage schedule.")
    climb: bool = Field(default=True, description="Enable climbing image in AutoNEB refinement.")
    iter_folder: str = Field(default="AutoNEB_iter", description="Directory for AutoNEB iteration history.")
    restart: bool = Field(default=False, description="Reuse existing AutoNEB image files.")
    directory: str = Field(default="autoneb_run", description="Base calculator directory.")
    endpoint_singlepoint: Literal["auto", "always", "never"] = Field(default="auto", description="Endpoint result policy.")

    @field_validator("fmax")
    @classmethod
    def _validate_fmax(cls, value: float | list[float]) -> float | list[float]:
        values = value if isinstance(value, list) else [value]
        if any(float(item) <= 0 for item in values):
            raise ValueError("calculation.fmax must be positive")
        return value

    @field_validator("maxsteps")
    @classmethod
    def _validate_maxsteps(cls, value: int | list[int]) -> int | list[int]:
        values = value if isinstance(value, list) else [value]
        if any(int(item) <= 0 for item in values):
            raise ValueError("calculation.maxsteps must be positive")
        if isinstance(value, list) and len(value) != 2:
            raise ValueError("calculation.maxsteps schedule must contain exactly two values")
        return value


class DimerCalculation(StrictConfig):
    """Standalone Dimer saddle-point search configuration."""

    type: Literal["dimer"] = Field(description="Select the standalone ASE Dimer workflow.")
    init_structure: str = Field(description="Initial transition-state guess.")
    trajectory: str = Field(default="dimer.traj", description="Dimer trajectory output.")
    restart: bool = Field(default=False, description="Restart from the last trajectory frame.")
    fmax: float = Field(default=0.05, gt=0, description="Force convergence threshold in eV/Ang.")
    max_steps: int | None = Field(default=None, gt=0, description="Maximum optimizer steps.")
    init_eigenmode_method: Literal["displacement", "gauss"] = Field(
        default="displacement",
        description="Initial eigenmode strategy.",
    )
    displacement_vector: str | None = Field(default=None, description="Path to a NumPy displacement vector.")
    dimer_separation: float = Field(default=0.01, gt=0, description="Finite-difference dimer separation.")
    max_num_rot: int = Field(default=3, gt=0, description="Maximum dimer rotations per step.")
    directory: str = Field(default="dimer_run", description="Calculator working directory.")


class SellaCalculation(StrictConfig):
    """Standalone Sella saddle-point search configuration."""

    type: Literal["sella"] = Field(description="Select the standalone Sella saddle-point workflow.")
    init_structure: str = Field(description="Initial transition-state guess.")
    trajectory: str = Field(default="sella.traj", description="Sella trajectory output.")
    restart: bool = Field(default=False, description="Restart from the last trajectory frame.")
    fmax: float = Field(default=0.05, gt=0, description="Force convergence threshold in eV/Ang.")
    max_steps: int | None = Field(default=None, gt=0, description="Maximum optimizer steps.")
    eta: float = Field(default=0.005, gt=0, description="Sella eta parameter.")
    order: int = Field(default=1, gt=0, description="Saddle-point order.")
    directory: str = Field(default="sella_run", description="Calculator working directory.")


class AutoReactiveBondsConfig(StrictConfig):
    """Automatic CCQN reactive-bond enumeration configuration."""

    enabled: bool = Field(default=False, description="Enable reactive-bond mode enumeration.")
    molecule_indices: str | list[int] | None = Field(default=None, description="1-based adsorbate or molecule indices.")
    active_molecule_indices: str | list[int] | None = Field(default=None, description="Optional active molecule atoms.")
    active_catalyst_indices: str | list[int] | None = Field(default=None, description="Optional active catalyst atoms.")
    cutoff_A: float = Field(default=3.0, gt=0, description="Maximum molecule-catalyst pair distance.")
    max_modes: int = Field(default=20, gt=0, description="Maximum ranked modes to write to the manifest.")
    max_bonds_per_mode: int = Field(default=1, gt=0, description="Maximum bond count in a mode.")
    bond_detect_scale: float = Field(default=1.2, gt=0, description="Covalent radii multiplier used for labels.")


class CCQNCalculation(StrictConfig):
    """Standalone CCQN saddle-point search configuration."""

    type: Literal["ccqn"] = Field(description="Select the standalone CCQN saddle-point workflow.")
    init_structure: str = Field(description="Initial transition-state guess.")
    trajectory: str = Field(default="ccqn.traj", description="CCQN trajectory output.")
    logfile: str = Field(default="ccqn.log", description="CCQN optimizer log file.")
    final_structure: str = Field(default="ccqn_final.extxyz", description="Final optimized structure output.")
    artifact_manifest: str = Field(default="atst_artifacts.json", description="Workflow artifact manifest JSON output.")
    restart: bool = Field(default=False, description="Restart from the last trajectory frame.")
    fmax: float = Field(default=0.05, gt=0, description="Force convergence threshold in eV/Ang.")
    max_steps: int | None = Field(default=200, gt=0, description="Maximum optimizer steps.")
    e_vector_method: Literal["ic", "interp"] = Field(default="ic", description="CCQN cone-axis construction method.")
    reactive_bonds: str | list[list[int]] | None = Field(default=None, description="1-based reactive bonds for IC mode.")
    product_file: str | None = Field(default=None, description="Product-like structure for interpolation mode.")
    align_product_indices: bool = Field(default=False, description="Align product atom indices to the initial structure.")
    auto_reactive_bonds: AutoReactiveBondsConfig = Field(
        default_factory=AutoReactiveBondsConfig,
        description="Automatic reactive-bond mode enumeration.",
    )
    mode_manifest: str = Field(default="ccqn_mode_manifest.json", description="CCQN reactive-mode manifest JSON.")
    diagnostics_file: str | None = Field(default="ccqn_diagnostics.json", description="CCQN optimizer diagnostics JSON.")
    ic_mode: Literal["democratic", "sum"] = Field(default="democratic", description="IC bond contribution mode.")
    cos_phi: float = Field(default=0.5, gt=0, lt=1, description="Cosine of the cone half angle.")
    trust_radius_uphill: float = Field(default=0.1, gt=0, description="Fixed uphill trust radius in Ang.")
    trust_radius_saddle_initial: float = Field(default=0.05, gt=0, description="Initial PRFO trust radius in Ang.")
    hessian: bool = Field(default=False, description="Use calculator Hessian when available.")
    accept_initial_converged: bool = Field(
        default=False,
        description="Accept an already force-converged TS guess before taking an uphill CCQN step.",
    )
    directory: str = Field(default="ccqn_run", description="Calculator working directory.")

    @model_validator(mode="after")
    def _validate_direction_inputs(self) -> "CCQNCalculation":
        if self.e_vector_method == "ic" and not self.reactive_bonds and not self.auto_reactive_bonds.enabled:
            raise ValueError("calculation.reactive_bonds is required when e_vector_method=ic")
        if self.e_vector_method == "interp" and not self.product_file:
            raise ValueError("calculation.product_file is required when e_vector_method=interp")
        return self


class RelaxCalculation(StrictConfig):
    """Structure relaxation workflow configuration."""

    type: Literal["relax"] = Field(description="Select the structure relaxation workflow.")
    init_structure: str = Field(description="Initial structure file.")
    fmax: float = Field(default=0.05, gt=0, description="Force convergence threshold in eV/Ang.")
    max_steps: int = Field(default=200, gt=0, description="Maximum optimizer steps.")
    optimizer: str = Field(default="FIRE", description="ASE optimizer name.")
    trajectory: str = Field(default="relax.traj", description="Relaxation trajectory output.")
    logfile: str = Field(default="relax.log", description="Optimizer log file.")
    restart: bool = Field(default=False, description="Restart from the last trajectory frame.")
    directory: str = Field(default="relax_run", description="Calculator working directory.")


class ThermochemistryConfig(StrictConfig):
    """Vibrational thermochemistry configuration."""

    model: Literal["harmonic", "ideal_gas"] = Field(default="harmonic", description="Thermochemistry model.")
    temperature: float = Field(default=300.0, gt=0, description="Temperature in Kelvin.")
    ignore_imag_modes: bool = Field(default=True, description="Ignore imaginary modes in thermochemistry.")
    energy_threshold: float = Field(
        default=1.0e-6,
        ge=0,
        description="Minimum real vibration energy in eV included in thermochemistry.",
    )
    pressure: float = Field(default=101325.0, gt=0, description="Pressure in Pa for ideal-gas thermo.")
    geometry: Literal["monatomic", "linear", "nonlinear"] = Field(
        default="nonlinear",
        description="Molecular geometry for ideal-gas thermo.",
    )
    symmetrynumber: int = Field(default=1, gt=0, description="Rotational symmetry number.")
    spin: float = Field(default=0.0, ge=0, description="Spin for ideal-gas thermo.")
    potentialenergy: float = Field(default=0.0, description="Potential energy override for ideal-gas thermo.")


class VibrationCalculation(StrictConfig):
    """Finite-difference vibration workflow configuration."""

    type: Literal["vibration"] = Field(description="Select the finite-difference vibration workflow.")
    init_structure: str = Field(description="Optimized structure for finite-difference vibrations.")
    delta: float = Field(default=0.01, gt=0, description="Finite-difference displacement in Ang.")
    nfree: Literal[2, 4] = Field(default=2, description="Number of displacements per degree of freedom.")
    indices: list[int] | None = Field(default=None, description="Atom indices to vibrate; None means all atoms.")
    name: str = Field(default="vib", description="ASE vibration cache prefix.")
    results_file: str = Field(default="vibration_results.json", description="Vibration JSON output.")
    validation_file: str = Field(default="ts_validation.json", description="Transition-state validation JSON output.")
    artifact_manifest: str = Field(default="atst_artifacts.json", description="Workflow artifact manifest JSON output.")
    restart: bool = Field(default=False, description="Reuse existing vibration cache files.")
    directory: str = Field(default="vib_run", description="Calculator working directory.")
    thermochemistry: ThermochemistryConfig = Field(
        default_factory=ThermochemistryConfig,
        description="Thermochemistry settings.",
    )


class DMFSettings(StrictConfig):
    """Direct MaxFlux method settings shared by standalone DMF and D2S."""

    directory: str = Field(default="dmf_run", description="Calculator working directory.")
    trajectory: str = Field(default="dmf_path.traj", description="DMF evaluation path trajectory output.")
    tmax_trajectory: str = Field(
        default="dmf_tmax.traj",
        description="Highest-energy DMF candidate trajectory output with single-point energy/forces.",
    )
    summary_file: str = Field(default="dmf_summary.json", description="DMF JSON summary output.")
    artifact_manifest: str = Field(default="atst_artifacts.json", description="Workflow artifact manifest JSON output.")
    initial_path: Literal["linear", "fbenm", "cfbenm"] = Field(
        default="cfbenm",
        description="Initial path generator before accurate DirectMaxFlux optimization.",
    )
    nsegs: int = Field(default=4, gt=0, description="Number of B-spline segments.")
    dspl: int = Field(default=3, gt=0, description="B-spline polynomial degree.")
    nmove: int = Field(
        default=10,
        gt=0,
        description="Number of movable DMF evaluation images; the written path has nmove + 2 images including endpoints.",
    )
    beta: float | None = Field(default=None, gt=0, description="Optional DirectMaxFlux beta override.")
    update_teval: bool = Field(default=True, description="Enable adaptive t_eval updates during DirectMaxFlux.")
    tol: float | Literal["tight", "middle", "loose"] = Field(default="middle", description="IPOPT dual tolerance preset or value.")
    ipopt_options: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional IPOPT options forwarded to PyDMF, e.g. max_iter or print_level.",
    )
    parallel: bool = Field(default=False, description="Enable PyDMF threaded energy/force evaluation.")
    remove_rotation_and_translation: bool = Field(
        default=True,
        description="Remove global translational and rotational degrees of freedom in non-periodic DMF.",
    )
    pbc_mode: Literal["reject", "cartesian_unwrapped"] = Field(
        default="reject",
        description="PBC handling mode; cartesian_unwrapped is experimental and assumes pre-unwrapped Cartesian endpoints.",
    )
    confirm_pbc_risk: bool = Field(
        default=False,
        description="Required acknowledgement for experimental cartesian_unwrapped PBC mode.",
    )

    @model_validator(mode="after")
    def _validate_pbc_mode_options(self) -> "DMFSettings":
        if self.pbc_mode == "cartesian_unwrapped":
            if not self.confirm_pbc_risk:
                raise ValueError("calculation.confirm_pbc_risk=true is required for pbc_mode=cartesian_unwrapped")
            if self.remove_rotation_and_translation:
                raise ValueError(
                    "calculation.remove_rotation_and_translation=false is required for pbc_mode=cartesian_unwrapped"
                )
            if self.initial_path != "linear":
                raise ValueError("calculation.initial_path=linear is required for pbc_mode=cartesian_unwrapped")
        return self


class DMFCalculation(DMFSettings):
    """Standalone experimental Direct MaxFlux transition-state candidate workflow."""

    type: Literal["dmf"] = Field(description="Select the experimental standalone Direct MaxFlux workflow.")
    init_file: str = Field(description="Initial-state structure file.")
    final_file: str = Field(description="Final-state structure file.")


class D2SDMFConfig(DMFSettings):
    """D2S rough Direct MaxFlux phase configuration."""

    artifact_manifest: str = Field(default="dmf_artifacts.json", description="Nested DMF artifact manifest JSON output.")


class EndpointOptimizationConfig(StrictConfig):
    """D2S endpoint optimization configuration."""

    enabled: bool = Field(default=True, description="Optimize endpoints before rough DyNEB.")
    skip_if_has_results: bool = Field(default=True, description="Skip endpoints that already have energy and forces.")
    fmax: float = Field(default=0.05, gt=0, description="Endpoint optimization force threshold.")
    max_steps: int = Field(default=200, gt=0, description="Endpoint optimization step limit.")


class D2SNEBConfig(StrictConfig):
    """D2S rough DyNEB phase configuration."""

    n_images: int = Field(default=8, gt=0, description="Number of intermediate rough DyNEB images.")
    fmax: float = Field(default=0.8, gt=0, description="Rough DyNEB force threshold.")
    algorism: str = Field(default="improvedtangent", description="DyNEB tangent method.")
    climb: bool = Field(default=True, description="Enable climbing image in rough DyNEB.")
    scale_fmax: float = Field(default=0.0, ge=0, description="DyNEB dynamic-relaxation force scaling.")
    idpp_maxiter: int = Field(default=2000, gt=0, description="Maximum iterations for the rough-path Fast IDPP optimizer.")
    idpp_tol: float = Field(default=1e-4, gt=0, description="Gradient tolerance for the rough-path Fast IDPP optimizer.")
    max_steps: int = Field(default=200, gt=0, description="Rough DyNEB maximum steps.")
    optimizer_kwargs: dict[str, Any] = Field(
        default_factory=dict,
        description="Keyword arguments forwarded to the rough DyNEB FIRE optimizer.",
    )


class D2SDimerConfig(StrictConfig):
    """D2S Dimer refinement configuration."""

    fmax: float = Field(default=0.05, gt=0, description="Dimer force threshold.")
    max_steps: int | None = Field(default=None, gt=0, description="Dimer maximum steps.")
    trajectory: str = Field(default="dimer.traj", description="Dimer trajectory output.")
    directory: str | None = Field(default=None, description="Dimer calculator directory.")
    init_eigenmode_method: Literal["displacement", "gauss"] = Field(default="displacement", description="Dimer eigenmode method.")
    dimer_separation: float = Field(default=0.01, gt=0, description="Dimer separation.")
    max_num_rot: int = Field(default=3, gt=0, description="Maximum dimer rotations per step.")


class D2SSellaConfig(StrictConfig):
    """D2S Sella refinement configuration."""

    fmax: float = Field(default=0.05, gt=0, description="Sella force threshold.")
    max_steps: int | None = Field(default=None, gt=0, description="Sella maximum steps.")
    trajectory: str = Field(default="sella.traj", description="Sella trajectory output.")
    directory: str | None = Field(default=None, description="Sella calculator directory.")
    eta: float = Field(default=0.005, gt=0, description="Sella eta parameter.")
    order: int = Field(default=1, gt=0, description="Saddle-point order.")


class D2SCCQNConfig(StrictConfig):
    """D2S CCQN refinement configuration."""

    fmax: float = Field(default=0.05, gt=0, description="CCQN force threshold.")
    max_steps: int | None = Field(default=200, gt=0, description="CCQN maximum steps.")
    trajectory: str = Field(default="ccqn.traj", description="CCQN trajectory output.")
    logfile: str = Field(default="ccqn.log", description="CCQN optimizer log file.")
    final_structure: str = Field(default="ccqn_final.extxyz", description="Final optimized structure output.")
    directory: str | None = Field(default=None, description="CCQN calculator directory.")
    e_vector_method: Literal["interp", "ic"] = Field(default="interp", description="CCQN cone-axis method.")
    reactive_bonds: str | list[list[int]] | None = Field(default=None, description="1-based reactive bonds for IC mode.")
    align_product_indices: bool = Field(default=False, description="Align product atom indices to the initial structure.")
    auto_reactive_bonds: AutoReactiveBondsConfig = Field(
        default_factory=AutoReactiveBondsConfig,
        description="Automatic reactive-bond mode enumeration.",
    )
    mode_manifest: str = Field(default="ccqn_mode_manifest.json", description="CCQN reactive-mode manifest JSON.")
    diagnostics_file: str | None = Field(default="ccqn_diagnostics.json", description="CCQN optimizer diagnostics JSON.")
    ic_mode: Literal["democratic", "sum"] = Field(default="democratic", description="IC bond contribution mode.")
    cos_phi: float = Field(default=0.5, gt=0, lt=1, description="Cosine of the cone half angle.")
    trust_radius_uphill: float = Field(default=0.1, gt=0, description="Fixed uphill trust radius in Ang.")
    trust_radius_saddle_initial: float = Field(default=0.05, gt=0, description="Initial PRFO trust radius in Ang.")
    hessian: bool = Field(default=False, description="Use calculator Hessian when available.")
    accept_initial_converged: bool = Field(
        default=False,
        description="Accept an already force-converged TS guess before taking an uphill CCQN step.",
    )


class D2SVibrationConfig(StrictConfig):
    """Optional D2S vibration analysis configuration."""

    enabled: bool = Field(default=False, description="Run vibration after single-ended refinement.")
    indices: Literal["auto", "all"] | list[int] = Field(default="auto", description="Atom index selection.")
    threshold: float = Field(default=0.10, ge=0, description="Displacement threshold for auto indices.")
    delta: float = Field(default=0.01, gt=0, description="Finite-difference displacement in Ang.")
    nfree: Literal[2, 4] = Field(default=2, description="Number of displacements per degree of freedom.")
    name: str = Field(default="d2s_vib", description="ASE vibration cache prefix.")
    results_file: str = Field(default="d2s_vibration_results.json", description="Vibration JSON output.")
    validation_file: str = Field(default="d2s_ts_validation.json", description="Transition-state validation JSON output.")
    directory: str = Field(default="VIBRATION", description="Vibration calculator directory.")
    thermochemistry: ThermochemistryConfig = Field(default_factory=ThermochemistryConfig, description="Thermochemistry settings.")


class D2SCalculation(StrictConfig):
    """Double-ended to single-ended transition-state workflow configuration."""

    type: Literal["d2s"] = Field(description="Select the double-ended to single-ended transition-state workflow.")
    method: Literal["dimer", "sella", "ccqn"] = Field(default="dimer", description="Single-ended refinement method.")
    rough_method: Literal["neb", "dmf"] = Field(
        default="neb",
        description="Double-ended rough path method; dmf is experimental and neb remains the supported default.",
    )
    init_file: str = Field(description="Initial-state structure file.")
    final_file: str = Field(description="Final-state structure file.")
    directory: str = Field(default="run_d2s", description="Base workflow directory.")
    artifact_manifest: str = Field(default="atst_artifacts.json", description="Workflow artifact manifest JSON output.")
    restart: bool = Field(default=False, description="Reuse rough NEB and single-ended checkpoints.")
    endpoint_singlepoint: Literal["auto", "always", "never"] = Field(default="auto", description="Endpoint result policy.")
    endpoint_optimization: EndpointOptimizationConfig = Field(
        default_factory=EndpointOptimizationConfig,
        description="Endpoint optimization policy.",
    )
    neb: D2SNEBConfig = Field(default_factory=D2SNEBConfig, description="Rough DyNEB configuration.")
    dmf: D2SDMFConfig = Field(default_factory=D2SDMFConfig, description="Experimental rough DMF configuration.")
    dimer: D2SDimerConfig = Field(default_factory=D2SDimerConfig, description="Dimer refinement configuration.")
    sella: D2SSellaConfig = Field(default_factory=D2SSellaConfig, description="Sella refinement configuration.")
    ccqn: D2SCCQNConfig = Field(default_factory=D2SCCQNConfig, description="CCQN refinement configuration.")
    vibration: D2SVibrationConfig = Field(default_factory=D2SVibrationConfig, description="Optional vibration configuration.")


class IRCCalculation(StrictConfig):
    """IRC workflow configuration."""

    type: Literal["irc"] = Field(description="Select the intrinsic reaction coordinate workflow.")
    backend: Literal["sella", "descent"] = Field(default="sella", description="IRC backend.")
    init_structure: str = Field(description="Transition-state structure file.")
    trajectory: str = Field(default="irc_log.traj", description="IRC trajectory output.")
    artifact_manifest: str = Field(default="atst_artifacts.json", description="Workflow artifact manifest JSON output.")
    normalized_trajectory: str | None = Field(default=None, description="Normalized trajectory for direction=both.")
    mode_vector: str | None = Field(default=None, description="NumPy mode vector for descent IRC backend.")
    descent_delta: float = Field(default=0.1, gt=0, description="Initial displacement along the descent IRC mode.")
    direction: Literal["both", "forward", "reverse"] = Field(default="both", description="IRC direction.")
    restart: bool = Field(default=False, description="Append from the last trajectory frame.")
    directory: str = Field(default="irc_run", description="Calculator working directory.")
    fmax: float = Field(default=0.05, gt=0, description="IRC force threshold.")
    max_steps: int = Field(default=1000, gt=0, description="Maximum steps per IRC direction.")
    dx: float = Field(default=0.1, gt=0, description="IRC step size.")
    eta: float = Field(default=0.0001, gt=0, description="Sella IRC eta parameter.")
    gamma: float = Field(default=0.1, gt=0, description="Sella IRC gamma parameter.")
    irctol: float = Field(default=0.01, gt=0, description="IRC tolerance.")
    keep_going: bool = Field(default=False, description="Forwarded to sella.IRC.")

    @model_validator(mode="after")
    def _validate_backend_inputs(self) -> "IRCCalculation":
        if self.backend == "descent" and not self.mode_vector:
            raise ValueError("calculation.mode_vector is required when backend=descent")
        return self


class MDPostSummaryConfig(StrictConfig):
    """MD post-processing summary configuration."""

    enabled: bool = Field(default=True, description="Write MD post-processing summary after workflow completion.")
    output: str = Field(default="md_post_summary.json", description="MD post-processing summary JSON output.")
    tail: int | None = Field(default=None, gt=0, description="Only include the last N frames in the summary table.")


class MDPostConvertConfig(StrictConfig):
    """MD post-processing trajectory conversion configuration."""

    enabled: bool = Field(default=False, description="Convert MD trajectory after workflow completion.")
    format: Literal["traj", "extxyz", "cif", "stru", "xyz"] = Field(
        default="extxyz",
        description="ASE output format for MD trajectory conversion.",
    )
    output_prefix: str = Field(default="md_post", description="Output prefix or directory for converted MD frames.")
    frame: int | None = Field(default=None, description="Optional single frame index to convert.")
    stride: int = Field(default=1, gt=0, description="Frame stride for trajectory conversion.")


class MDPostprocessConfig(StrictConfig):
    """MD post-processing configuration."""

    summary: MDPostSummaryConfig = Field(default_factory=MDPostSummaryConfig, description="MD summary settings.")
    convert: MDPostConvertConfig = Field(default_factory=MDPostConvertConfig, description="MD conversion settings.")


class MDCalculation(StrictConfig):
    """Molecular dynamics workflow configuration."""

    type: Literal["md"] = Field(description="Select the molecular dynamics workflow.")
    driver: Literal["ase", "abacus_native"] = Field(
        default="ase",
        description="MD driver: ASE dynamics or ABACUS native MD.",
    )
    init_structure: str = Field(description="Initial structure file.")
    steps: int = Field(default=100, gt=0, description="Number of MD steps.")
    ensemble: Literal["nve", "nvt", "npt"] = Field(default="nvt", description="ASE MD ensemble.")
    algorithm: str = Field(default="bussi", description="ASE MD algorithm.")
    timestep_fs: float = Field(default=1.0, gt=0, description="ASE MD timestep in fs.")
    temperature_K: float = Field(default=300.0, gt=0, description="Target or initial temperature in K.")
    seed: int | None = Field(default=None, description="Random seed for initial velocities.")
    force_temperature: bool = Field(default=False, description="Rescale initial velocities to the exact target temperature.")
    stationary: bool = Field(default=True, description="Remove center-of-mass translation after velocity initialization.")
    zero_rotation: bool = Field(default=False, description="Remove angular momentum after velocity initialization.")
    friction_fs_inv: float = Field(default=0.01, gt=0, description="Langevin friction in fs^-1.")
    taut_fs: float = Field(default=10.0, gt=0, description="Thermostat time constant in fs.")
    taup_fs: float = Field(default=1000.0, gt=0, description="Barostat time constant in fs.")
    pressure_bar: float = Field(default=1.0, description="Target pressure in bar for NPT.")
    compressibility_bar_inv: float | None = Field(default=None, gt=0, description="Compressibility in bar^-1.")
    trajectory: str = Field(default="md.traj", description="MD trajectory output.")
    logfile: str = Field(default="md.log", description="MD log file.")
    loginterval: int = Field(default=1, gt=0, description="MD logging interval in steps.")
    summary_file: str = Field(default="md_summary.json", description="MD JSON summary output.")
    final_structure: str = Field(default="md_final.traj", description="Final structure output.")
    artifact_manifest: str = Field(default="atst_artifacts.json", description="Workflow artifact manifest JSON output.")
    postprocess: MDPostprocessConfig = Field(
        default_factory=MDPostprocessConfig,
        description="MD post-processing settings.",
    )
    restart: bool = Field(default=False, description="Restart from existing trajectory or native MD output.")
    directory: str = Field(default="md_run", description="Workflow run directory.")
    poll_interval_seconds: float = Field(default=5.0, ge=0, description="ABACUS native MD process polling interval.")
    timeout_seconds: float | None = Field(default=None, gt=0, description="Optional ABACUS native MD timeout.")

    @model_validator(mode="after")
    def _validate_driver_algorithm(self) -> "MDCalculation":
        algorithm = self.algorithm.lower()
        allowed = {
            "nve": {"velocityverlet"},
            "nvt": {"bussi", "langevin", "nvtberendsen"},
            "npt": {"nptberendsen"},
        }
        if self.driver == "ase" and algorithm not in allowed[self.ensemble]:
            raise ValueError(
                f"calculation.algorithm={self.algorithm!r} is not supported for ensemble={self.ensemble!r}"
            )
        return self


CalculationConfig = Annotated[
    Union[
        NEBCalculation,
        AutoNEBCalculation,
        DimerCalculation,
        SellaCalculation,
        CCQNCalculation,
        D2SCalculation,
        RelaxCalculation,
        VibrationCalculation,
        IRCCalculation,
        MDCalculation,
        DMFCalculation,
    ],
    Field(discriminator="type"),
]

CALCULATION_SCHEMA_BY_TYPE: dict[str, type[StrictConfig]] = {
    "neb": NEBCalculation,
    "autoneb": AutoNEBCalculation,
    "dimer": DimerCalculation,
    "sella": SellaCalculation,
    "ccqn": CCQNCalculation,
    "d2s": D2SCalculation,
    "relax": RelaxCalculation,
    "vibration": VibrationCalculation,
    "irc": IRCCalculation,
    "md": MDCalculation,
    "dmf": DMFCalculation,
}


def _field_default(field) -> Any:
    if field.is_required():
        return None
    if field.default_factory is not None:
        value = field.default_factory()
        if isinstance(value, BaseModel):
            return value.model_dump(mode="python")
        return value
    return field.default


def _schema_defaults(model: type[BaseModel]) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {}
    for name, field in model.model_fields.items():
        value = _field_default(field)
        if value is not None or not field.is_required():
            defaults[name] = value
    return defaults


def _model_from_annotation(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    if get_origin(annotation) in (UnionType, Union):
        for arg in get_args(annotation):
            nested = _model_from_annotation(arg)
            if nested is not None:
                return nested
    return None


def _apply_model_defaults(model: type[BaseModel], values: Dict[str, Any]) -> Dict[str, Any]:
    merged = _schema_defaults(model)
    for key, value in values.items():
        field = model.model_fields.get(key)
        nested_model = _model_from_annotation(field.annotation) if field is not None else None
        if nested_model is not None and isinstance(value, dict):
            merged[key] = _apply_model_defaults(nested_model, value)
        else:
            merged[key] = value
    return merged


def apply_calculation_defaults(calc_config: Dict[str, Any]) -> Dict[str, Any]:
    """Return calculation config with schema-managed defaults filled.

    This helper supports internal tests and direct workflow construction that
    bypass `ConfigLoader.normalize()`. It does not replace full validation at
    `atst run` entrypoints.
    """
    calc_type = calc_config.get("type")
    model = CALCULATION_SCHEMA_BY_TYPE.get(calc_type)
    if model is None:
        return dict(calc_config)
    return _apply_model_defaults(model, dict(calc_config))


class AbacusConfig(BaseModel):
    """ABACUS calculator configuration.

    Unknown top-level keys are preserved and passed to abacuslite for backwards
    compatibility. Prefer placing ABACUS INPUT variables under `parameters`.
    """

    model_config = ConfigDict(extra="allow")

    command: str = Field(default="abacus", description="ABACUS execution command.")
    version_command: str | None = Field(
        default=None,
        description="Optional full command used for ABACUS version probing.",
    )
    mpi: int = Field(default=1, gt=0, description="MPI process count used when command is not already parallel.")
    omp: int = Field(default=1, gt=0, description="OpenMP thread count.")
    directory: str = Field(default=".", description="Calculator working directory.")
    kpts: list[int] | Dict[str, Any] | None = Field(default=None, description="K-point sampling settings.")
    pseudopotentials: Dict[str, str] | None = Field(default=None, description="Element to UPF filename mapping.")
    basissets: Dict[str, str] | None = Field(default=None, description="Element to orbital filename mapping.")
    pp: Dict[str, str] | None = Field(default=None, description="Alias of pseudopotentials.")
    basis: Dict[str, str] | None = Field(default=None, description="Alias of basissets.")
    pseudo_dir: str | None = Field(default=None, description="Pseudopotential directory.")
    orbital_dir: str | None = Field(default=None, description="Orbital directory.")
    basis_dir: str | None = Field(default=None, description="Alias of orbital_dir.")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="ABACUS INPUT parameters.")


class DPConfig(StrictConfig):
    """DeepMD-kit calculator configuration."""

    model: str = Field(description="Path to the DeepMD-kit model file.")
    head: str | None = Field(default=None, description="Model head for multi-head DPA/DPA3 models.")
    type_map: list[str] | None = Field(
        default=None,
        description=(
            "Optional: Element order converted to deepmd-kit type_dict. "
            "In most cases not needed, the model already contains type information."
        ),
    )
    type_dict: Dict[str, int] | None = Field(
        default=None,
        description=(
            "Optional: Explicit element to type-index mapping. "
            "In most cases not needed, the model already contains type information."
        ),
    )
    omp: int | None = Field(default=None, gt=0, description="Optional OMP_NUM_THREADS value.")
    share_calculator: bool = Field(default=True, description="Share DP calculators where ASE permits it.")

    @model_validator(mode="after")
    def _validate_type_mapping(self) -> "DPConfig":
        if self.type_map is not None and self.type_dict is not None:
            raise ValueError("calculator.dp.type_map and calculator.dp.type_dict are mutually exclusive")
        return self


class CalculatorConfig(StrictConfig):
    """Calculator selection and engine-specific configuration."""

    name: Literal["abacus", "dp", "deepmd"] = Field(description="Calculator backend name.")
    abacus: AbacusConfig | None = Field(default=None, description="ABACUS calculator settings.")
    dp: DPConfig | None = Field(default=None, description="DeepMD-kit calculator settings.")

    @model_validator(mode="after")
    def _validate_matching_section(self) -> "CalculatorConfig":
        if self.name == "abacus" and self.abacus is None:
            raise ValueError("Missing calculator.abacus section for calculator.name=abacus")
        if self.name in {"dp", "deepmd"} and self.dp is None:
            raise ValueError("Missing calculator.dp section for calculator.name=dp")
        return self


class ATSTConfig(StrictConfig):
    """Top-level ATST-Tools YAML configuration."""

    calculation: CalculationConfig = Field(description="Workflow configuration.")
    calculator: CalculatorConfig = Field(description="Calculator configuration.")

    @model_validator(mode="after")
    def _validate_cross_section_rules(self) -> "ATSTConfig":
        if isinstance(self.calculation, MDCalculation):
            if self.calculation.driver == "abacus_native" and self.calculator.name != "abacus":
                raise ValueError("calculation.driver=abacus_native requires calculator.name=abacus")
        return self


def _preprocess_legacy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize legacy top-level calculator sections before schema validation."""
    normalized = dict(config)
    if "calculator" not in normalized and "abacus" in normalized:
        normalized["calculator"] = {"name": "abacus", "abacus": normalized.pop("abacus")}
    elif "calculator" in normalized:
        calculator = dict(normalized["calculator"] or {})
        if calculator.get("name") == "deepmd" and "dp" not in calculator and "deepmd" in calculator:
            calculator["dp"] = calculator.pop("deepmd")
        normalized["calculator"] = calculator
    return normalized


def _format_validation_error(exc: Exception) -> str:
    """Format pydantic errors with YAML-style dotted paths."""
    if not hasattr(exc, "errors"):
        return str(exc)
    lines = ["Invalid YAML configuration:"]
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ())) or "<root>"
        lines.append(f"- {loc}: {error.get('msg', 'invalid value')}")
    return "\n".join(lines)


def parse_config(config: Dict[str, Any]) -> ATSTConfig:
    """Validate and parse a raw YAML mapping into an ATSTConfig model."""
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a YAML mapping")
    calc_type = (config.get("calculation") or {}).get("type") if isinstance(config.get("calculation"), dict) else None
    if calc_type is not None and calc_type not in VALID_CALCULATION_TYPES:
        raise ValueError(f"Unsupported calculation type: {calc_type}. Supported: {list(VALID_CALCULATION_TYPES)}")
    try:
        return ATSTConfig.model_validate(_preprocess_legacy_config(config))
    except Exception as exc:
        raise ValueError(_format_validation_error(exc)) from exc


def normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return a schema-validated config dictionary with defaults populated."""
    parsed = parse_config(config)
    return parsed.model_dump(mode="python", exclude_none=True)


def json_schema() -> Dict[str, Any]:
    """Return the JSON schema for ATST-Tools YAML configuration."""
    return TypeAdapter(ATSTConfig).json_schema()

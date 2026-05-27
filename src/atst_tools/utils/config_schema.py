"""Pydantic schemas for ATST-Tools YAML configuration."""

from __future__ import annotations

from types import UnionType
from typing import Annotated, Any, Dict, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


CONFIG_VERSION = "2.0.0"
VALID_CALCULATION_TYPES = ("neb", "autoneb", "dimer", "sella", "d2s", "relax", "vibration", "irc")
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


class NEBCalculation(StrictConfig):
    """Nudged elastic band workflow configuration."""

    type: Literal["neb"] = Field(description="Select the ordinary NEB or DyNEB workflow.")
    init_chain: str | None = Field(default=None, description="Initial NEB chain trajectory.")
    make: NEBMakeConfig | None = Field(default=None, description="Nested chain generation configuration.")
    trajectory: str = Field(default="neb.traj", description="NEB trajectory output.")
    restart: bool = Field(default=False, description="Restart from the latest complete trajectory band.")
    climb: bool = Field(default=True, description="Enable climbing-image NEB.")
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
    restart: bool = Field(default=False, description="Reuse existing vibration cache files.")
    directory: str = Field(default="vib_run", description="Calculator working directory.")
    thermochemistry: ThermochemistryConfig = Field(
        default_factory=ThermochemistryConfig,
        description="Thermochemistry settings.",
    )


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


class D2SVibrationConfig(StrictConfig):
    """Optional D2S vibration analysis configuration."""

    enabled: bool = Field(default=False, description="Run vibration after single-ended refinement.")
    indices: Literal["auto", "all"] | list[int] = Field(default="auto", description="Atom index selection.")
    threshold: float = Field(default=0.10, ge=0, description="Displacement threshold for auto indices.")
    delta: float = Field(default=0.01, gt=0, description="Finite-difference displacement in Ang.")
    nfree: Literal[2, 4] = Field(default=2, description="Number of displacements per degree of freedom.")
    name: str = Field(default="d2s_vib", description="ASE vibration cache prefix.")
    results_file: str = Field(default="d2s_vibration_results.json", description="Vibration JSON output.")
    directory: str = Field(default="VIBRATION", description="Vibration calculator directory.")
    thermochemistry: ThermochemistryConfig = Field(default_factory=ThermochemistryConfig, description="Thermochemistry settings.")


class D2SCalculation(StrictConfig):
    """Double-ended to single-ended transition-state workflow configuration."""

    type: Literal["d2s"] = Field(description="Select the double-ended to single-ended transition-state workflow.")
    method: Literal["dimer", "sella"] = Field(default="dimer", description="Single-ended refinement method.")
    init_file: str = Field(description="Initial-state structure file.")
    final_file: str = Field(description="Final-state structure file.")
    directory: str = Field(default="run_d2s", description="Base workflow directory.")
    restart: bool = Field(default=False, description="Reuse rough NEB and single-ended checkpoints.")
    endpoint_singlepoint: Literal["auto", "always", "never"] = Field(default="auto", description="Endpoint result policy.")
    endpoint_optimization: EndpointOptimizationConfig = Field(
        default_factory=EndpointOptimizationConfig,
        description="Endpoint optimization policy.",
    )
    neb: D2SNEBConfig = Field(default_factory=D2SNEBConfig, description="Rough DyNEB configuration.")
    dimer: D2SDimerConfig = Field(default_factory=D2SDimerConfig, description="Dimer refinement configuration.")
    sella: D2SSellaConfig = Field(default_factory=D2SSellaConfig, description="Sella refinement configuration.")
    vibration: D2SVibrationConfig = Field(default_factory=D2SVibrationConfig, description="Optional vibration configuration.")


class IRCCalculation(StrictConfig):
    """Sella IRC workflow configuration."""

    type: Literal["irc"] = Field(description="Select the Sella intrinsic reaction coordinate workflow.")
    init_structure: str = Field(description="Transition-state structure file.")
    trajectory: str = Field(default="irc_log.traj", description="IRC trajectory output.")
    normalized_trajectory: str | None = Field(default=None, description="Normalized trajectory for direction=both.")
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


CalculationConfig = Annotated[
    Union[
        NEBCalculation,
        AutoNEBCalculation,
        DimerCalculation,
        SellaCalculation,
        D2SCalculation,
        RelaxCalculation,
        VibrationCalculation,
        IRCCalculation,
    ],
    Field(discriminator="type"),
]

CALCULATION_SCHEMA_BY_TYPE: dict[str, type[StrictConfig]] = {
    "neb": NEBCalculation,
    "autoneb": AutoNEBCalculation,
    "dimer": DimerCalculation,
    "sella": SellaCalculation,
    "d2s": D2SCalculation,
    "relax": RelaxCalculation,
    "vibration": VibrationCalculation,
    "irc": IRCCalculation,
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

    config_version: str = Field(default=CONFIG_VERSION, description="Configuration schema version.")
    calculation: CalculationConfig = Field(description="Workflow configuration.")
    calculator: CalculatorConfig = Field(description="Calculator configuration.")


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

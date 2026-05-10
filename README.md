# ATST-Tools

ATST-Tools is a pip-installable CLI + YAML toolkit for ASE-based transition-state, relaxation, and vibration workflows with ABACUS as the primary calculator backend.

## Install

```bash
git clone https://github.com/deepmodeling/atst-tools.git
cd atst-tools
pip install -e .
```

## Run

```bash
cd examples/06_relax_H2-Au
atst run config.yaml
```

Validate a config without starting a calculation:

```bash
atst run --dry-run examples/06_relax_H2-Au/config.yaml
```

## Documentation

Start from [docs/index.md](docs/index.md).

## License

LGPL-v3 License

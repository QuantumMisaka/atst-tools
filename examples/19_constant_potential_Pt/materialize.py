"""Materialize a self-contained Pt gate-field SCF fixture (no computation)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import re


def materialize(destination: Path, basis: str, electrons: float, spin: int = 1,
                *, dipole: bool = False, block_height: float | None = None,
                density_precision: int = 12) -> Path:
    """Copy pinned inputs/assets and record every derived setting."""
    source = Path(__file__).resolve().parent
    destination.mkdir(parents=True, exist_ok=False)
    data = source.parent / "data"
    pp = "Pt_ONCV_PBE-1.0.upf"
    orb = "Pt_gga_7au_100Ry_4s2p2d1f.orb"
    shutil.copy2(data / pp, destination / pp)
    stru = (source / "inputs/STRU").read_text()
    if basis == "lcao":
        shutil.copy2(data / orb, destination / orb)
        stru = stru.replace("LATTICE_CONSTANT", f"NUMERICAL_ORBITAL\n{orb}\n\nLATTICE_CONSTANT")
    (destination / "STRU").write_text(stru)
    shutil.copy2(source / "inputs/KPT", destination / "KPT")
    inp = (source / "inputs/INPUT").read_text()
    inp = inp.replace("basis_type lcao", f"basis_type {basis}")
    inp = inp.replace("ks_solver cusolver", "ks_solver cg" if basis == "pw" else "ks_solver cusolver")
    inp = inp.replace("nelec 217", f"nelec {electrons:.12g}")
    inp = inp.replace("nspin 1", f"nspin {spin}")
    inp = re.sub(r'(?m)^out_chg\s+.*$', f'out_chg 1 {density_precision}', inp)
    if block_height is not None:
        inp = re.sub(r'(?m)^block_height\s+.*$', f'block_height {block_height:.12g}', inp)
    if dipole:
        inp += '\nefield_flag 1\ndip_cor_flag 1\nefield_pos_max 0.8\nefield_pos_dec 0.1\nefield_amp 0\n'
    (destination / "INPUT").write_text(inp)
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.iterdir() if p.is_file()}
    manifest = {"upstream": "deepmodeling/abacus-develop", "revision": "f71921fe848659deac8db319cd4311b55b5ad480", "source": "examples/compensating_charge/Pt-slab", "basis": basis, "electrons": electrons, "nspin": spin, "neutral_electrons": 216, "vacuum_axis": 0, "changes": ["explicit x gate axis", "out_pot=2 and out_chg=1", "scf_thr=1e-9, ecutwfc=100, nbands=130", "explicit Gamma 1x1x1 mesh", "LCAO uses existing ATST Pt orbital and cusolver; PW uses cg", "assets copied from ATST examples/data"], "sha256": files}
    manifest['changes'][1] = f'out_pot=2 and out_chg=1 {density_precision}'
    if dipole:
        manifest['changes'].append('Explicit dipole .8/.1/0 from dipole_correction/Pt-slab/INPUT1; this also changes the block ramp')
    if block_height is not None:
        manifest['changes'].append(f'Fixed block_height={block_height:.12g} Ry')
    (destination / "fixture.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--basis", choices=("lcao", "pw"), default="lcao")
    parser.add_argument("--electrons", type=float, default=217.0)
    parser.add_argument("--spin", type=int, choices=(1, 2), default=1)
    parser.add_argument('--dipole', action='store_true')
    parser.add_argument('--block-height', type=float)
    parser.add_argument('--density-precision', type=int, default=12)
    args = parser.parse_args()
    print(materialize(args.destination, args.basis, args.electrons, args.spin,
                      dipole=args.dipole, block_height=args.block_height,
                      density_precision=args.density_precision))

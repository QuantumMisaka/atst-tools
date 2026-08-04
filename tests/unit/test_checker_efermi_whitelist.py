"""checker 对 efermi 语义补丁的登记行为（spec R3/P1）。"""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_abacuslite_snapshot.py"


def _load_checker():
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_abacuslite_snapshot", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


_UPSTREAM_READ_RESULTS = '''\
def read_results(directory) -> Dict:
    read_abacus_out = lambda fn: None
    global __LEGACYIO__
    if __LEGACYIO__:
        from abacuslite.io.legacyio import read_abacus_out
    else:
        from abacuslite.io.latestio import read_abacus_out

    outdir = directory / f'OUT.{self.suffix}'
    # only the last frame
    atoms: Optional[Atoms] = read_abacus_out(
        outdir / f'running_{self.calculation}.log',
        sort_atoms_with=self.atomorder)[-1]
    assert atoms is not None

    return dict(atoms.calc.properties())
'''


_FRAME_SELECTION_VENDORED = '''\
def _stru_positions_in_ase_order(directory, stru_file, atomorder):
    """读取本次 write_input 落盘 STRU 的坐标，统一到与帧相同的 ASE 原子序并换算为 Cartesian Å。"""
    return []


def _frame_coordinate_is_direct(log_path):
    """从 running log 的实际坐标头推导帧侧坐标系，不依赖 STRU 的 coord_type。"""
    return True


def _select_scf_frame_for_structure(frames, log_path, directory, atomorder, atol=1e-4):
    """返回坐标与当前 STRU 一致（绝对 Å 容差）的最后一帧；无匹配 fail-closed。"""
    return frames[-1]


def read_results(directory) -> Dict:
    read_abacus_out = lambda fn: None
    global __LEGACYIO__
    if __LEGACYIO__:
        from abacuslite.io.legacyio import read_abacus_out
    else:
        from abacuslite.io.latestio import read_abacus_out

    outdir = directory / f'OUT.{self.suffix}'
    log = outdir / f'running_{self.calculation}.log'
    # 读取全部帧；scf 下按坐标选择当前结构帧，非 scf（relax/md）保持末帧语义（spec R1/R2）
    frames = read_abacus_out(log, sort_atoms_with=self.atomorder)
    if not frames:
        raise RuntimeError(f"no ABACUS running-log frames in {log}")
    if self.calculation != 'scf':
        atoms: Optional[Atoms] = frames[-1]  # 原生 relax/md：既有末帧语义（spec R2/P2）
    else:
        atomorder = self.atomorder or list(range(len(frames[0])))
        atoms = _select_scf_frame_for_structure(frames, log, directory, atomorder)
    assert atoms is not None

    return dict(atoms.calc.properties())
'''


def _revert_efermi_patch(upstream: Path) -> None:
    """把上游树还原为严格形式（ener['E_Fermi']）。

    本地 vendored 树已携带 efermi 容错补丁（b1ebd4c），故拷贝作上游后需反向
    还原，才能构造"仅 efermi 一处语义 diff"的对比场景（ener.get -> ener['E_Fermi']）。
    """
    for rel in ["abacuslite/io/legacyio.py", "abacuslite/io/latestio.py"]:
        path = upstream / rel
        text = path.read_text(encoding="utf-8")
        text = text.replace("efermi=ener.get('E_Fermi')", "efermi=ener['E_Fermi']")
        path.write_text(text, encoding="utf-8")


def test_checker_exits_zero_when_only_documented_efermi_patch(tmp_path, monkeypatch):
    """登记后的语义补丁（efermi）不产生 drift；未登记的新改动仍 exit 1。"""
    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    shutil.copytree(ROOT / "src/atst_tools/external/ASE_interface", upstream)
    shutil.copytree(ROOT / "src/atst_tools/external/ASE_interface", vendored)
    _revert_efermi_patch(upstream)

    monkeypatch.setattr(sys, "argv", [str(CHECKER)])
    import importlib.util

    spec = importlib.util.spec_from_file_location("check_abacuslite_snapshot", CHECKER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.compare_snapshots(upstream, vendored) == 0

    # 未登记的 drift（改一行注释之外的代码）应返回 1
    target = vendored / "abacuslite/io/legacyio.py"
    text = target.read_text(encoding="utf-8")
    target.write_text(text.replace("efermi=ener.get('E_Fermi')", "efermi=None"), encoding="utf-8")
    assert mod.compare_snapshots(upstream, vendored) == 1


def test_checker_exits_zero_with_registered_vendored_only_files(tmp_path, capsys):
    """atst 自有文件（顶层 SNAPSHOT/PATCHES + multiframe_* 金样，含 STRU-less md 目录）不再报 vendored-only。"""
    mod = _load_checker()
    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    _write(upstream / "abacuslite" / "core.py", "VALUE = 1\n")
    _write(vendored / "abacuslite" / "core.py", "VALUE = 1\n")
    _write(vendored / "ABACUSLITE_SNAPSHOT.md", "# snapshot baseline\n")
    _write(vendored / "PATCHES.md", "# semantic patches\n")
    # multiframe 金样（md 目录无 STRU，兼容 STRU-less）
    _write(vendored / "abacuslite" / "io" / "testfiles" / "multiframe_scf_trial_last" / "running_scf.log", "x\n")
    _write(vendored / "abacuslite" / "io" / "testfiles" / "multiframe_md_legacy" / "running_md.log", "x\n")
    _write(vendored / "abacuslite" / "io" / "testfiles" / "multiframe_md_latest" / "eig_occ.txt", "x\n")

    assert mod.compare_snapshots(upstream, vendored) == 0
    assert capsys.readouterr().out == ""


def test_checker_reports_unregistered_vendored_only_file(tmp_path, capsys):
    """未登记的新 vendored-only 文件仍 exit 1（spec R3/P1）。"""
    mod = _load_checker()
    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    _write(upstream / "abacuslite" / "core.py", "VALUE = 1\n")
    _write(vendored / "abacuslite" / "core.py", "VALUE = 1\n")
    _write(vendored / "abacuslite" / "io" / "testfiles" / "extra_golden" / "file.txt", "x\n")

    assert mod.compare_snapshots(upstream, vendored) == 1
    output = capsys.readouterr().out
    assert "Unexpected vendored-only files" in output
    assert "abacuslite/io/testfiles/extra_golden/file.txt" in output


def test_checker_exits_zero_with_documented_core_frame_selection_patch(tmp_path, capsys):
    """core.py 帧选择语义补丁（PATCHES.md 登记）归一化后与上游一致 → exit 0。"""
    mod = _load_checker()
    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    _write(upstream / "abacuslite" / "core.py", _UPSTREAM_READ_RESULTS)
    _write(vendored / "abacuslite" / "core.py", _FRAME_SELECTION_VENDORED)

    assert mod.compare_snapshots(upstream, vendored) == 0
    assert capsys.readouterr().out == ""


def test_checker_reports_unregistered_core_frame_selection_variant(tmp_path, capsys):
    """帧选择补丁改动（read_results 分支结构变化）未登记 → 归一化不匹配 → exit 1。"""
    mod = _load_checker()
    upstream = tmp_path / "upstream"
    vendored = tmp_path / "vendored"
    _write(upstream / "abacuslite" / "core.py", _UPSTREAM_READ_RESULTS)
    variant = _FRAME_SELECTION_VENDORED.replace(
        "if self.calculation != 'scf':", "if self.calculation in ('relax', 'md'):"
    )
    _write(vendored / "abacuslite" / "core.py", variant)

    assert mod.compare_snapshots(upstream, vendored) == 1
    output = capsys.readouterr().out
    assert "Implementation drift detected" in output

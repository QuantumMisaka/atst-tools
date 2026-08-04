"""checker 对 efermi 语义补丁的登记行为（spec R3/P1）。"""
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_abacuslite_snapshot.py"


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

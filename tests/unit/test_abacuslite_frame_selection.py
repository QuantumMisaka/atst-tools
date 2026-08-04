"""scf 多帧累积下 read_results 必须返回当前结构帧的力（spec R1/R2，legacyio 主路径）。

Task 3 GREEN：`AbacusTemplate.read_results` 对 calculation=='scf' 按坐标选择"当前结构帧"
（core.py::_select_scf_frame_for_structure），非 scf（relax/md）保持 [-1] 末帧语义。
金样 multiframe_scf_trial_last/running_scf.log 共 4 帧：帧 0（ION=1）= INIT（== 当前 STRU），
帧 1-2 为位移/trial 试探结构，末帧（ION=4）= P0 重算（≠ STRU）。
"""
import re
from pathlib import Path

import numpy as np
import pytest

from atst_tools.external.ASE_interface.abacuslite.core import AbacusTemplate
from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_stru
from atst_tools.external.ASE_interface.abacuslite.io.legacyio import read_abacus_out


TESTFILES = (
    Path(__file__).resolve().parents[2]
    / "src/atst_tools/external/ASE_interface/abacuslite/io/testfiles"
)
GOLD = TESTFILES / "multiframe_scf_trial_last"
LOG = GOLD / "running_scf.log"

# 帧 0（INIT，== 当前 STRU）的力；末帧（P0 重算）力不同，用于断言"返回当前结构帧而非末帧"
STRU_FRAME_FORCES = np.array(
    [[-0.5, -0.01, 0.0], [0.5, 0.01, 0.0], [0.0, 0.0, 0.0]]
)
LAST_FRAME_FORCES = np.array(
    [[-0.45, -0.014, 0.0], [0.45, 0.014, 0.0], [0.0, 0.0, 0.0]]
)

# tauc_/taud_ 原子坐标行（x y z mag vx vy vz）：前 3 个浮点为坐标
_COORD_LINE = re.compile(r"^(taud_\S+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)(.*)$")


def _stru_positions_cartesian(stru, cell):
    """read_stru 的 DIRECT 分数坐标 -> Cartesian Å（与 running log 同源晶胞换算）。

    STRU 与 running log 描述同一晶胞，直接用帧的 cell（Å）换算（ase 3.28 无 abacus
    STRU 读取器，故用 read_stru）。与 core.py 帧选择采用同一坐标系/容差口径（spec P3 ③）。
    """
    frac = np.array(
        [a["coord"] for sp in stru["species"] for a in sp["atom"]], dtype=float
    )
    return frac @ np.asarray(cell)


def _cartesian_stru_text():
    """把金样 DIRECT STRU 变换为同结构的 Cartesian STRU（write_stru 默认即 Cartesian）。

    体系与金样一致：H(0.4,0.5,0.5)/H(0.6,0.5,0.5)/Au(0.5,0.5,0.1)（Direct）⇔
    H(4,5,5)/H(6,5,5)/Au(5,5,1)（Cartesian Å，晶胞 10 Å 立方）。
    """
    return (
        (GOLD / "STRU")
        .read_text()
        .replace("Direct", "Cartesian")
        .replace("0.4000000000 0.5000000000 0.5000000000",
                 "4.0000000000 5.0000000000 5.0000000000")
        .replace("0.6000000000 0.5000000000 0.5000000000",
                 "6.0000000000 5.0000000000 5.0000000000")
        .replace("0.5000000000 0.5000000000 0.1000000000",
                 "5.0000000000 5.0000000000 1.0000000000")
    )


def _cartesian_log_text():
    """把金样 DIRECT running log 变换为同结构的 CARTESIAN 日志（tauc_ + 坐标×10 Å）。

    仅变换原子坐标头（^DIRECT COORDINATES$）/前缀（taud_→tauc_）/坐标值（×晶胞 10 Å），
    K-POINTS 等其余内容保持不变；read_abacus_out 可正常解析为 4 个 Cartesian 帧。
    """
    lines = []
    for line in (GOLD / "running_scf.log").read_text().splitlines(keepends=True):
        if re.match(r"^DIRECT COORDINATES\s*$", line.rstrip("\n")):
            lines.append("CARTESIAN COORDINATES\n")
            continue
        m = _COORD_LINE.match(line.rstrip("\n"))
        if m:
            x, y, z = (float(m.group(i)) * 10.0 for i in (2, 3, 4))
            lines.append(f"{m.group(1)} {x:20.10f} {y:20.10f} {z:20.10f}{m.group(5)}\n")
            continue
        lines.append(line)
    return "".join(lines)


def _template(calc="scf", atomorder=None):
    """构造最小 AbacusTemplate：仅 read_results 依赖的字段（suffix/calculation/atomorder）。"""
    template = AbacusTemplate()
    template.suffix = "ABACUS"
    template.calculation = calc
    template.atomorder = [0, 1, 2] if atomorder is None else atomorder
    return template


def _read_results_fixture(tmp_path, calc="scf", stru_text=None, log_text=None):
    """把金样布置成 read_results 期望的目录布局（STRU + OUT.ABACUS/running_<calc>.log）。

    非 scf 时把同一 running_scf.log 复制为 running_<calc>.log，仅用于验证非 scf 分支
    保持 [-1] 末帧语义（不做坐标匹配）；stru_text/log_text 可覆盖 STRU 与日志内容。
    """
    (tmp_path / "STRU").write_text(
        stru_text if stru_text is not None else (GOLD / "STRU").read_text(),
        encoding="utf-8",
    )
    out = tmp_path / "OUT.ABACUS"
    out.mkdir()
    (out / f"running_{calc}.log").write_text(
        log_text if log_text is not None else (GOLD / "running_scf.log").read_text(),
        encoding="utf-8",
    )
    return tmp_path


def test_golden_last_frame_differs_from_current_structure():
    """金样语义：末帧为试探/P0 重算结构，与当前 STRU 不一致（RED 场景前提）。"""
    frames = read_abacus_out(LOG, sort_atoms_with=None)
    stru = read_stru(GOLD / "STRU")
    last_cart = frames[-1].positions @ np.asarray(frames[-1].cell)
    current_cart = _stru_positions_cartesian(stru, frames[-1].cell)
    assert not np.allclose(last_cart, current_cart, atol=1e-4)


def test_golden_first_frame_is_current_structure():
    """金样语义：帧 0（INIT）== 当前 STRU，是 read_results 应返回的帧。"""
    frames = read_abacus_out(LOG, sort_atoms_with=None)
    stru = read_stru(GOLD / "STRU")
    first_cart = frames[0].positions @ np.asarray(frames[0].cell)
    current_cart = _stru_positions_cartesian(stru, frames[0].cell)
    assert np.allclose(first_cart, current_cart, atol=1e-4)


def test_multiframe_scf_read_results_returns_current_structure_force(tmp_path):
    """scf 多帧累积：read_results 返回当前结构帧（帧 0）的力，而非末帧试探结构的力。"""
    directory = _read_results_fixture(tmp_path)
    results = _template().read_results(directory)

    assert not np.allclose(STRU_FRAME_FORCES, LAST_FRAME_FORCES)  # 语义：两帧力不同
    assert np.allclose(results["forces"], STRU_FRAME_FORCES, atol=1e-12)


def test_scf_read_results_fails_closed_when_no_frame_matches(tmp_path):
    """无匹配帧：STRU 与 running log 全部帧不一致时 fail-closed（含 log 路径/帧数/差异摘要）。"""
    stru_text = (
        (GOLD / "STRU")
        .read_text()
        .replace("0.4000000000 0.5000000000 0.5000000000",
                 "0.4300000000 0.5000000000 0.5000000000")
        .replace("0.6000000000 0.5000000000 0.5000000000",
                 "0.5700000000 0.5000000000 0.5000000000")
    )
    directory = _read_results_fixture(tmp_path, stru_text=stru_text)
    with pytest.raises(RuntimeError) as excinfo:
        _template().read_results(directory)
    msg = str(excinfo.value)
    assert "running_scf.log" in msg
    assert "4 帧" in msg
    assert "fail-closed" in msg


def test_non_scf_read_results_keeps_last_frame_semantics(tmp_path):
    """非 scf（relax）：read_results 保持 [-1] 末帧语义，不做坐标帧选择（spec R2/P2）。"""
    directory = _read_results_fixture(tmp_path, calc="relax")
    results = _template(calc="relax").read_results(directory)

    assert not np.allclose(STRU_FRAME_FORCES, LAST_FRAME_FORCES)  # 语义：两帧力不同
    assert np.allclose(results["forces"], LAST_FRAME_FORCES, atol=1e-12)


def test_scf_frame_selection_respects_atomorder_revmap(tmp_path):
    """统一排列：非平凡 atomorder（revmap）下 STRU 与帧仍按同一映射对齐（spec P3 ①）。"""
    directory = _read_results_fixture(tmp_path)
    # ASE 序 [H, Au, H] 的 revmap：species 序 [H, H, Au] -> ASE 序
    results = _template(atomorder=[0, 2, 1]).read_results(directory)

    assert np.allclose(results["forces"][1], 0.0, atol=1e-12)  # 中间原子为 Au，力为 0
    assert np.allclose(results["forces"][0], [-0.5, -0.01, 0.0], atol=1e-12)
    assert np.allclose(results["forces"][2], [0.5, 0.01, 0.0], atol=1e-12)


def test_scf_frame_selection_uses_log_coordinate_system_not_stru(tmp_path):
    """F1：帧侧坐标系以 running log 实际坐标头为准，而非 STRU coord_type。

    STRU 为 Cartesian（write_stru 默认），金样日志为 DIRECT（分数帧）——旧实现按 STRU
    判 is_direct=False 会把分数坐标当 Cartesian Å，合法 scf 假 fail-closed；修复后正常
    返回当前结构帧的力。
    """
    directory = _read_results_fixture(tmp_path, stru_text=_cartesian_stru_text())
    results = _template().read_results(directory)
    assert np.allclose(results["forces"], STRU_FRAME_FORCES, atol=1e-12)


def test_scf_frame_selection_cartesian_log_branch(tmp_path):
    """F1：帧侧 Cartesian 分支——running log 为 CARTESIAN（帧坐标已是 Å）时不做 cell 换算。"""
    directory = _read_results_fixture(tmp_path, log_text=_cartesian_log_text())
    results = _template().read_results(directory)
    assert np.allclose(results["forces"], STRU_FRAME_FORCES, atol=1e-12)


def test_scf_read_results_without_atomorder_uses_identity(tmp_path):
    """F2：atomorder=None（未走 write_input 直接 read_results）时按 identity 守卫，
    scf 帧选择正常工作而非裸 TypeError（与 read_abacus_out sort_atoms_with=None 语义一致）。"""
    directory = _read_results_fixture(tmp_path)
    template = _template()
    template.atomorder = None
    results = template.read_results(directory)
    assert np.allclose(results["forces"], STRU_FRAME_FORCES, atol=1e-12)

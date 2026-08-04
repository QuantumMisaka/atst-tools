"""scf 多帧累积下 read_results 必须返回当前结构帧的力（spec R1/R2，legacyio 主路径）。

RED：当前实现 `AbacusTemplate.read_results` 无条件取末帧 `[-1]`（core.py:370-372）；
本金样 `multiframe_scf_trial_last/running_scf.log` 的末帧为试探（P0 重算）结构，
与当前落盘 `STRU` 不一致，因此断言"末帧就是当前结构"必然失败——为 Task 3 的
read_results 帧选择修复建立失败基线。
"""
from pathlib import Path

import numpy as np

from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_stru
from atst_tools.external.ASE_interface.abacuslite.io.legacyio import read_abacus_out


TESTFILES = (
    Path(__file__).resolve().parents[2]
    / "src/atst_tools/external/ASE_interface/abacuslite/io/testfiles"
)
LOG = TESTFILES / "multiframe_scf_trial_last" / "running_scf.log"


def _stru_positions_cartesian(stru, cell):
    """read_stru 的 DIRECT 分数坐标 -> Cartesian Å（与 running log 同源晶胞换算）。

    ase 3.28 无 abacus STRU 读取器（`ase.io.read(..., format='abacus')` 不可用），
    故按 plan Task 2 的 Consumes 接口改用 `read_stru`（generalio）读取当前结构；
    STRU 与 running log 描述同一晶胞，直接用帧的 cell（Å）换算。
    """
    frac = np.array(
        [a["coord"] for sp in stru["species"] for a in sp["atom"]], dtype=float
    )
    return frac @ np.asarray(cell)


def test_multiframe_scf_reads_current_structure_force_not_last_frame():
    """末帧为试探结构时，返回的力必须属于 STRU 当前结构（绝对 Å 容差匹配）。"""
    frames = read_abacus_out(LOG, sort_atoms_with=None)
    last = frames[-1]
    stru = read_stru(LOG.parent / "STRU")

    # 帧坐标：read_abacus_out 对 DIRECT 日志返回分数坐标（原样），与 STRU 同为 DIRECT；
    # 统一换算到 Cartesian Å 后按 atol=1e-4（Å）比较（spec P3 ③）。
    last_cart = last.positions @ np.asarray(last.cell)
    current_cart = _stru_positions_cartesian(stru, last.cell)

    # RED：当前实现 read_results 取 [-1]，此处断言"末帧就是当前结构"将失败（末帧是试探结构）
    assert np.allclose(last_cart, current_cart, atol=1e-4), (
        "末帧为试探结构，坐标与当前 STRU 不一致——read_results 必须按坐标选择帧"
    )

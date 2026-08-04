#!/usr/bin/env python3
"""Phase 0 SAI 取证脚本：ABACUS running log 多帧一致性诊断。

用途
----
对 sella_repro（或任意 ABACUS 工作目录）的 running log 做**只读**取证，
输出 spec P7 的判定证据，用于区分三种候选子机制：

    (a)  帧错位       —— trajectory/forces 子列表等长但内容错位
    (b') 末次调用未产新帧 —— 末次 ABACUS 调用 exit 0 但未追加任何帧，
                           ``[-1]`` 静默返回上一结构力
    (c)  读入后日志增长   —— 缓存读入后又追加了帧（读入/读取时序问题）

输出内容
--------
- 帧数（解析器轨迹帧数 + 原始坐标头计数）
- 逐帧坐标头（DIRECT/CARTESIAN + ION 序号 + 力块标记）
- 逐帧 TOTAL-FORCE 块计数（原始扫描 + 解析器力块数）
- 末帧坐标 vs STRU 差异（统一 Cartesian Å，绝对 Å 容差）
- INPUT calculation 值
- 调用时间线（ION MOVE / PW ALGORITHM ION 头、READING UNITCELL 调用计数、
  DONE Time 行、MD STEP，按文件行号顺序）

解析器复用 abacuslite.io.legacyio / latestio 的
``read_forces_from_running_log`` / ``read_traj_from_running_log``
（本脚本不调用 ``read_abacus_out``，故不触发 latestio 的 eig_occ.txt
一次性消费/unlink 副作用；spec P5）。

本脚本为只读：不写任何文件、不修改输入。SAI 节点运行与 running log 取回
属外部依赖（plan Task 7 执行注记）；本任务仅本地静态自检。

自检
----
    conda run -n abacus-env env PYTHONPATH=$PWD/src \\
        python3 tools/abacuslite_phase0_diagnosis.py --help
    conda run -n abacus-env env PYTHONPATH=$PWD/src \\
        python3 tools/abacuslite_phase0_diagnosis.py \\
            --log   src/atst_tools/external/ASE_interface/abacuslite/io/testfiles/multiframe_scf_trial_last/running_scf.log \\
            --stru  src/atst_tools/external/ASE_interface/abacuslite/io/testfiles/multiframe_scf_trial_last/STRU \\
            --input src/atst_tools/external/ASE_interface/abacuslite/io/testfiles/multiframe_scf_trial_last/INPUT
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# 只读 marker 扫描：不依赖 parser，先建立文件结构时间线（帧/力块/ION 头/调用）
# ---------------------------------------------------------------------------
_COORD_RE = re.compile(r"^\s*(DIRECT|CARTESIAN) COORDINATES\s*$")
_ION_PW_RE = re.compile(r"PW ALGORITHM\b.*?\bION=\s*(\d+)")
_ION_MOVE_RE = re.compile(r"#ION MOVE#\s*(\d+)")
_FORCE_RE = re.compile(r"#?\s*TOTAL-FORCE\s*\(eV\s*/Angstrom\)\s*#?")
_INVOC_RE = re.compile(r"^READING UNITCELL INFORMATION")
_ATOMNUM_RE = re.compile(r"TOTAL ATOM NUMBER\s*=\s*(\d+)")
_MDSTEP_RE = re.compile(r"STEP OF MOLECULAR DYNAMICS:\s*(\d+)")
_TIME_RE = re.compile(r"DONE\s*:\s*(.*?)\s*Time\s*:\s*([\d.eE+-]+)\s*\(SEC\)")


# ---------------------------------------------------------------------------
# 后端导入与解析
# ---------------------------------------------------------------------------
def _import_parsers() -> Tuple[Any, Any]:
    """导入 abacuslite.io 双后端（legacyio, latestio）。

    优先走 ``atst_tools`` 包路径（文档化调用设置 PYTHONPATH=$PWD/src）；
    失败时相对本脚本位置向上查找仓库 ``src/`` 兜底，便于在 SAI 节点直接运行
    （不硬编码任何 SAI 路径，仅相对脚本定位）。
    """
    try:
        from atst_tools.external.ASE_interface.abacuslite.io import (
            latestio,
            legacyio,
        )
    except ImportError as first_err:
        here = Path(__file__).resolve()
        for parent in here.parents:
            candidate = parent / "src"
            if (candidate / "atst_tools").is_dir():
                sys.path.insert(0, str(candidate))
                from atst_tools.external.ASE_interface.abacuslite.io import (
                    latestio,
                    legacyio,
                )
                return legacyio, latestio
        raise first_err
    return legacyio, latestio


def _parse_backend(module: Any, log_path: Path) -> Tuple[Any, Any]:
    """用指定 backend 解析轨迹与力块；解析失败抛异常（由调用方记录）。"""
    traj = module.read_traj_from_running_log(str(log_path))
    forces = module.read_forces_from_running_log(str(log_path))
    return traj, forces


def _select_primary_backend(
    args: argparse.Namespace,
    legacyio: Any,
    latestio: Any,
) -> Tuple[str, Dict[str, Dict[str, Any]], List[Any], List[Any]]:
    """双后端交叉解析，返回 (primary_name, per_backend_results, traj, forces)。

    ``--backend auto``（默认）按 ``abacuslite.core.__LEGACYIO__`` 优先对应后端
    （SAI/SIF 生产路径 LTS 3.10.x -> legacyio），若其解析不出帧则回退另一后端；
    无论如何两个后端的帧/力块计数都输出（后端间差异本身即 (a) 证据）。
    """
    results: Dict[str, Dict[str, Any]] = {}
    for name, module in (("legacyio", legacyio), ("latestio", latestio)):
        try:
            traj, forces = _parse_backend(module, args.log)
            results[name] = {
                "ok": True,
                "error": None,
                "nframe": len(traj),
                "nforce": len(forces),
                "traj": traj,
                "forces": forces,
            }
        except Exception as exc:  # noqa: BLE001 取证脚本：记录并继续
            results[name] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "nframe": 0,
                "nforce": 0,
                "traj": [],
                "forces": [],
            }

    if args.backend != "auto":
        chosen = args.backend
        return chosen, results, results[chosen]["traj"], results[chosen]["forces"]

    preferred = "legacyio"
    try:
        from atst_tools.external.ASE_interface.abacuslite import core

        preferred = "legacyio" if core.__LEGACYIO__ else "latestio"
    except Exception:  # noqa: BLE001 core 不可导入时按 SAI 生产默认 legacyio
        pass

    if results[preferred].get("ok") and results[preferred]["nframe"] > 0:
        return preferred, results, results[preferred]["traj"], results[preferred]["forces"]
    for name in ("legacyio", "latestio"):
        if results[name].get("ok") and results[name]["nframe"] > 0:
            return name, results, results[name]["traj"], results[name]["forces"]
    # 双后端均无帧：以 preferred 名占位（详细分析走原始 marker 扫描）
    return preferred, results, results[preferred]["traj"], results[preferred]["forces"]


# ---------------------------------------------------------------------------
# 原始 marker 扫描与时间线
# ---------------------------------------------------------------------------
def _scan_markers(lines: List[str]) -> List[Tuple[int, str, Any]]:
    """扫描 running log 的结构 marker，返回按行号（0-based）排序的列表。"""
    markers: List[Tuple[int, str, Any]] = []
    for i, line in enumerate(lines):
        s = line.rstrip("\n")
        m = _COORD_RE.match(s)
        if m:
            markers.append((i, "coord", m.group(1)))
        m = _ION_PW_RE.search(s)
        if m:
            markers.append((i, "ion_pw", int(m.group(1))))
        m = _ION_MOVE_RE.search(s)
        if m:
            markers.append((i, "ion_move", int(m.group(1))))
        if _FORCE_RE.search(s):
            markers.append((i, "force", None))
        if _INVOC_RE.match(s):
            markers.append((i, "invocation", None))
        m = _ATOMNUM_RE.search(s)
        if m:
            markers.append((i, "natoms", int(m.group(1))))
        m = _MDSTEP_RE.search(s)
        if m:
            markers.append((i, "md_step", int(m.group(1))))
        m = _TIME_RE.search(s)
        if m:
            markers.append((i, "time", (m.group(1).strip(), m.group(2))))
    markers.sort(key=lambda item: item[0])
    return markers


def _build_frame_table(
    markers: List[Tuple[int, str, Any]],
) -> List[Dict[str, Any]]:
    """把坐标头与其后的 ION 头、TOTAL-FORCE 块配对为逐帧表。"""
    coords = [(ln, val) for ln, kind, val in markers if kind == "coord"]
    ions = [(ln, kind, val) for ln, kind, val in markers if kind in ("ion_pw", "ion_move")]
    forces = [ln for ln, kind, _ in markers if kind == "force"]
    rows: List[Dict[str, Any]] = []
    for ln, coord_kind in coords:
        ion = next(((iln, ik, iv) for iln, ik, iv in ions if iln > ln), None)
        force_line = next((fln for fln in forces if fln > ln), None)
        rows.append(
            {
                "coord_line": ln,
                "coord_kind": coord_kind,
                "ion": ion,
                "force_line": force_line,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# 坐标换算（统一 Cartesian Å）与比较
# ---------------------------------------------------------------------------
def _stru_cartesian_angstrom(stru: Dict[str, Any]) -> Any:
    """STRU 物种分组序坐标 -> Cartesian Å（spec P3 ③ 口径，与 core.py 一致）。"""
    from ase.units import Bohr

    lat = stru["lat"]
    const = float(lat["const"])
    cell = np.asarray(lat["vec"], dtype=float) * const * Bohr
    coords = np.asarray(
        [np.asarray(a["coord"], dtype=float) for sp in stru["species"] for a in sp["atom"]],
        dtype=float,
    ).reshape(-1, 3)
    if str(stru["coord_type"]).lower().startswith("d"):
        return coords @ cell
    return coords * const * Bohr


def _frame_cartesian_angstrom(frame: Dict[str, Any]) -> Any:
    """running log 帧坐标 -> Cartesian Å（Direct 乘 cell；Cartesian 原样，均为 Å）。"""
    coords = np.asarray(frame["coords"], dtype=float)
    if str(frame["coordinate"]).lower().startswith("d"):
        return coords @ np.asarray(frame["cell"], dtype=float)
    return coords


def _max_abs_diff(a: Any, b: Any) -> Tuple[float, Any]:
    diff = np.abs(np.asarray(a, dtype=float) - np.asarray(b, dtype=float))
    return (float(diff.max()) if diff.size else float("nan")), diff


def _max_force_norm(force: Any) -> float:
    arr = np.asarray(force, dtype=float)
    return float(np.max(np.linalg.norm(arr, axis=1))) if arr.size else float("nan")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _build_report(args: argparse.Namespace) -> Dict[str, Any]:
    from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_input
    from atst_tools.external.ASE_interface.abacuslite.io.generalio import read_stru

    log_path = Path(args.log)
    if not log_path.is_file():
        raise SystemExit(f"[error] --log 不存在或不可读: {log_path}")

    # (c) 读入后日志增长探测：读取前后 stat 采样
    def _stat() -> Dict[str, Any]:
        st = log_path.stat()
        return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}

    stat_before = _stat()
    with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
        raw_lines = fh.readlines()
    markers = _scan_markers(raw_lines)
    frame_table = _build_frame_table(markers)
    stat_after = _stat()

    legacyio, latestio = _import_parsers()
    primary, backend_results, traj, forces = _select_primary_backend(
        args, legacyio, latestio
    )

    report: Dict[str, Any] = {
        "args": {
            "log": str(log_path),
            "stru": str(args.stru) if args.stru else None,
            "input": str(args.input_file) if args.input_file else None,
            "atol": args.atol,
            "backend": args.backend,
        },
        "file_stat": {
            "before": stat_before,
            "after": stat_after,
            "changed": stat_before != stat_after,
        },
        "raw_scan": {
            "all_markers": markers,
            "coord_headers": [m for m in markers if m[1] == "coord"],
            "ion_headers": [m for m in markers if m[1] in ("ion_pw", "ion_move")],
            "force_blocks": [m for m in markers if m[1] == "force"],
            "invocations": [m for m in markers if m[1] == "invocation"],
            "natoms_lines": [m for m in markers if m[1] == "natoms"],
            "natoms_values": [m[2] for m in markers if m[1] == "natoms"],
            "md_steps": [m for m in markers if m[1] == "md_step"],
            "time_lines": [m for m in markers if m[1] == "time"],
        },
        "backends": {
            name: {
                "ok": r["ok"],
                "error": r["error"],
                "nframe": r["nframe"],
                "nforce": r["nforce"],
            }
            for name, r in backend_results.items()
        },
        "primary_backend": primary,
        "frame_table": frame_table,
        "parsed": {
            "nframe": len(traj),
            "nforce": len(forces),
            "coordinate": str(traj[0]["coordinate"]) if traj else None,
            "natoms": int(traj[0]["coords"].shape[0]) if traj else None,
        },
        "last_frame": None,
        "stru": None,
        "input": None,
        "diagnosis": None,
    }

    # 末帧信息（力复现 0.0374 vs 0.338 所需）
    if traj and forces:
        report["last_frame"] = {
            "index": len(traj) - 1,
            "coordinate": str(traj[-1]["coordinate"]),
            "coords_cartesian_angstrom": _frame_cartesian_angstrom(traj[-1]).round(6).tolist(),
            "force_max_norm": _max_force_norm(forces[-1]),
            "force": np.asarray(forces[-1], dtype=float).round(6).tolist(),
        }

    # 末帧 vs STRU（统一 Cartesian Å + 绝对 Å 容差）
    if args.stru:
        stru_path = Path(args.stru)
        if stru_path.is_file():
            try:
                stru = read_stru(str(stru_path))
                stru_cart = _stru_cartesian_angstrom(stru)
                report["stru"] = {
                    "coord_type": str(stru["coord_type"]),
                    "natoms": int(stru_cart.shape[0]),
                    "cartesian_angstrom": stru_cart.round(6).tolist(),
                }
                if traj:
                    frame_cart = _frame_cartesian_angstrom(traj[-1])
                    max_diff, diff = _max_abs_diff(frame_cart, stru_cart)
                    report["stru"]["last_frame_max_abs_diff_angstrom"] = max_diff
                    report["stru"]["last_frame_within_atol"] = bool(max_diff <= args.atol)
                    report["stru"]["per_atom_abs_diff_angstrom"] = diff.round(6).tolist()
            except Exception as exc:  # noqa: BLE001 STRU 解析失败不阻断取证
                report["stru"] = {"error": f"{type(exc).__name__}: {exc}"}
        else:
            report["stru"] = {"error": f"文件不存在: {stru_path}"}

    # INPUT calculation
    if args.input_file:
        input_path = Path(args.input_file)
        if input_path.is_file():
            try:
                params = read_input(str(input_path))
                report["input"] = {"calculation": params.get("calculation")}
            except Exception as exc:  # noqa: BLE001
                report["input"] = {"error": f"{type(exc).__name__}: {exc}"}
        else:
            report["input"] = {"error": f"文件不存在: {input_path}"}

    # (a)/(b')/(c) 判定信号
    n_coord = len(report["raw_scan"]["coord_headers"])
    n_ion = len(report["raw_scan"]["ion_headers"])
    n_force = len(report["raw_scan"]["force_blocks"])
    # 调用次数代理：READING UNITCELL 缺失时以 TOTAL ATOM NUMBER 出现次数计数
    # （真实 ABACUS 每次调用都会打印 UNITCELL/原子数信息；金样简化版只有原子数行）
    n_read_unitcell = len(report["raw_scan"]["invocations"])
    n_natoms_lines = len(report["raw_scan"]["natoms_lines"])
    n_invoc = max(n_read_unitcell, n_natoms_lines)
    nframe = report["parsed"]["nframe"]
    nforce = report["parsed"]["nforce"]

    signals: List[str] = []
    if nframe > 0 and nforce > 0 and nframe == nforce and n_coord == nframe:
        signals.append("帧/力块数量一致（解析帧=%d, 解析力块=%d, 坐标头=%d）——无 (a) 帧错位 / 缺块信号" % (nframe, nforce, n_coord))
    else:
        signals.append(
            "数量不一致：坐标头=%d, ION 头=%d, 原始力块=%d, 解析帧=%d, 解析力块=%d —— (a) 帧错位 / 缺块候选，需人工核对时间线"
            % (n_coord, n_ion, n_force, nframe, nforce)
        )
    if n_ion > n_coord:
        signals.append(
            "ION 头数(%d) > 坐标帧数(%d)：存在未产新坐标帧的调用序号 —— (b') 末次调用未产新帧候选"
            % (n_ion, n_coord)
        )
    if n_invoc > 0 and n_coord < n_invoc:
        signals.append(
            "调用计数代理(%d；READING UNITCELL=%d / TOTAL ATOM NUMBER=%d) > 坐标帧数(%d)："
            "存在整体未产帧的 ABACUS 调用 —— (b') 候选"
            % (n_invoc, n_read_unitcell, n_natoms_lines, n_coord)
        )
    if stat_before != stat_after:
        signals.append(
            "脚本读取前后日志 size/mtime 变化（%s -> %s）：运行期间日志在增长 —— (c) 读入后日志增长候选"
            % (stat_before, stat_after)
        )
    else:
        signals.append("脚本读取前后日志 size/mtime 未变化：本次运行期间无日志增长")
    report["diagnosis"] = {"signals": signals}

    return report


def _render_human(report: Dict[str, Any]) -> str:
    args = report["args"]
    out: List[str] = []
    out.append("=== 输入 ===")
    out.append("  log  : %s" % args["log"])
    out.append("  stru : %s" % (args["stru"] or "（未提供）"))
    out.append("  input: %s" % (args["input"] or "（未提供）"))
    out.append("  atol : %g Å（绝对 Å 容差）" % args["atol"])
    out.append("  backend: %s" % args["backend"])

    out.append("")
    out.append("=== 文件采样（(c) 读入后日志增长探测）===")
    fs = report["file_stat"]
    out.append("  读取前: size=%d bytes, mtime_ns=%d" % (fs["before"]["size"], fs["before"]["mtime_ns"]))
    out.append("  读取后: size=%d bytes, mtime_ns=%d" % (fs["after"]["size"], fs["after"]["mtime_ns"]))
    out.append("  结果  : %s" % ("读取期间日志发生变化" if fs["changed"] else "读取期间无日志增长"))

    out.append("")
    out.append("=== 后端解析（双后端交叉）===")
    for name, r in report["backends"].items():
        if r["ok"]:
            out.append("  %-9s: ok, 帧=%d, 力块=%d" % (name, r["nframe"], r["nforce"]))
        else:
            out.append("  %-9s: FAIL (%s)" % (name, r["error"]))
    out.append("  主解析后端: %s" % report["primary_backend"])

    out.append("")
    out.append("=== 原始 marker 扫描 ===")
    rs = report["raw_scan"]
    out.append("  坐标头(DIRECT/CARTESIAN): %d" % len(rs["coord_headers"]))
    out.append("  ION 头(PW ALGORITHM/#ION MOVE#): %d" % len(rs["ion_headers"]))
    out.append("  TOTAL-FORCE 块: %d" % len(rs["force_blocks"]))
    out.append(
        "  调用计数: READING UNITCELL=%d, TOTAL ATOM NUMBER 行=%d（代理）"
        % (len(rs["invocations"]), len(rs["natoms_lines"]))
    )
    out.append("  TOTAL ATOM NUMBER 值: %s" % (rs["natoms_values"] or "（未找到）"))
    if rs["md_steps"]:
        out.append("  MD STEP: %s" % [m[2] for m in rs["md_steps"]])

    out.append("")
    out.append("=== 逐帧（主解析后端 %s）===" % report["primary_backend"])
    parsed = report["parsed"]
    out.append(
        "  解析帧数=%d, 解析力块数=%d, 坐标系=%s, 原子数=%s"
        % (parsed["nframe"], parsed["nforce"], parsed["coordinate"], parsed["natoms"])
    )
    for idx, row in enumerate(report["frame_table"]):
        ion = row["ion"]
        ion_txt = "无"
        if ion is not None:
            iln, ikind, ival = ion
            ion_txt = "ION=%s(%s @L%d)" % (ival, "PW ALGORITHM" if ikind == "ion_pw" else "#ION MOVE#", iln + 1)
        force_txt = ("L%d" % (row["force_line"] + 1)) if row["force_line"] is not None else "无"
        out.append(
            "  frame %d  %s @L%d    %-24s   TOTAL-FORCE @%s"
            % (idx, row["coord_kind"], row["coord_line"] + 1, ion_txt, force_txt)
        )

    if report["last_frame"]:
        lf = report["last_frame"]
        out.append("")
        out.append("=== 末帧 ===")
        out.append("  index=%d, coordinate=%s" % (lf["index"], lf["coordinate"]))
        out.append("  Cartesian Å 坐标: %s" % lf["coords_cartesian_angstrom"])
        out.append("  末帧力 max|F| = %.6f（对照 sella_repro 0.338 实证）" % lf["force_max_norm"])
        out.append("  末帧力: %s" % lf["force"])

    if report["stru"]:
        out.append("")
        out.append("=== 末帧 vs STRU（统一 Cartesian Å + 绝对 Å 容差）===")
        if "error" in report["stru"]:
            out.append("  STRU 解析失败: %s" % report["stru"]["error"])
        else:
            st = report["stru"]
            out.append("  STRU coord_type=%s, natoms=%d" % (st["coord_type"], st["natoms"]))
            out.append("  STRU Cartesian Å 坐标: %s" % st["cartesian_angstrom"])
            out.append(
                "  末帧 vs STRU 最大绝对差 = %.6f Å（atol=%g）→ %s"
                % (
                    st["last_frame_max_abs_diff_angstrom"],
                    args["atol"],
                    "一致" if st["last_frame_within_atol"] else "不一致（超容差）",
                )
            )
            out.append("  逐原子绝对差(Å): %s" % st["per_atom_abs_diff_angstrom"])

    if report["input"]:
        out.append("")
        out.append("=== INPUT ===")
        if "error" in report["input"]:
            out.append("  INPUT 解析失败: %s" % report["input"]["error"])
        else:
            out.append("  calculation = %s" % report["input"]["calculation"])

    out.append("")
    out.append("=== 时间线（行号 1-based，按文件顺序）===")
    for ln, kind, val in report["raw_scan"]["all_markers"]:
        if kind == "coord":
            txt = "%s COORDINATES" % val
        elif kind in ("ion_pw", "ion_move"):
            txt = "ION=%s" % val
        elif kind == "natoms":
            txt = "TOTAL ATOM NUMBER = %s" % val
        elif kind == "md_step":
            txt = "MD STEP %s" % val
        elif kind == "time":
            txt = "DONE %s Time=%s s" % val
        elif kind == "invocation":
            txt = "READING UNITCELL INFORMATION"
        elif kind == "force":
            txt = "TOTAL-FORCE (eV/Angstrom)"
        else:
            txt = str(kind)
        out.append("  L%-6d %s" % (ln + 1, txt))

    out.append("")
    out.append("=== 判定信号（a / b' / c）===")
    for sig in report["diagnosis"]["signals"]:
        out.append("  - %s" % sig)

    return "\n".join(out)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="abacuslite_phase0_diagnosis.py",
        description=(
            "ABACUS running log 多帧一致性取证（spec P7；判定 a/b'/c 子机制）。"
            "只读：不写任何文件。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--log", required=True, help="running log 路径（如 running_scf.log）")
    parser.add_argument("--stru", default=None, help="当前 STRU 路径（可选；提供时输出末帧 vs STRU 差异）")
    parser.add_argument("--input", dest="input_file", default=None, help="INPUT 路径（可选；提供时输出 calculation 值）")
    parser.add_argument("--atol", type=float, default=1e-4, help="绝对 Å 容差（默认 1e-4）")
    parser.add_argument(
        "--backend",
        choices=("auto", "legacyio", "latestio"),
        default="auto",
        help="解析后端：auto 按 __LEGACYIO__ 优先对应后端并交叉尝试另一后端（默认）",
    )
    parser.add_argument("--json", action="store_true", help="以 JSON 输出（便于下游脚本解析）")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    report = _build_report(args)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(_render_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

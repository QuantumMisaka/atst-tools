# ABACUS STRU I/O 与 ase-abacus fork 兼容性审查

**版本**: 2.0.2
**日期**: 2026-06-05
**状态**: 维护
**责任人**: ATST-Tools maintainers
**范围**: 对比 ATST-Tools 当前 abacuslite STRU read/write 路径与 `temp_repos/ase-abacus` ASE fork 中注册的 ABACUS STRU I/O。

## 摘要

本报告确认两个问题：

1. 当前 ATST-Tools / abacuslite 的 ABACUS STRU read/write 是否能满足本项目基本需求。
2. 在允许库调用方式和变量名不同的前提下，当前实现是否能基本取代 `ase-abacus` fork 中注册的 `ase.io.read/write(format="abacus")` STRU 功能。

结论是：

- **针对 ATST-Tools 当前基本 ABACUS 工作流需求，abacuslite 的 STRU read/write 功能可以覆盖。**
- **针对 `ase-abacus` fork 的完整 STRU I/O 功能集，当前实现不能完全取代。**

这里的“本项目基本需求”指：NEB、AutoNEB、Dimer、Sella、CCQN、D2S、Relax、Vibration、IRC 等当前工作流需要读入 ABACUS 初末态 `STRU`，并通过 `atst abacus prepare` 写出可供 ABACUS 运行的 `INPUT`、`KPT`、`STRU`。这些路径主要依赖元素、cell、PBC、Direct/Cartesian 坐标、赝势、轨道基组、常规磁矩，以及 `atst neb make` 中的 `--fix` / `--mag` 初猜链元数据设置；当前 abacuslite 路径可以覆盖这些需求。

但 `ase-abacus` fork 的 STRU I/O 功能边界更宽，包括 ASE I/O format 注册、Direct/scaled 坐标写出、ASE constraints/mobility roundtrip、真实初速度 roundtrip、verbose metadata readback 等。当前 ATST-Tools / abacuslite 尚未覆盖这些能力。

## 实现对比

| 对比项 | 当前 ATST-Tools / abacuslite 路径 | `temp_repos/ase-abacus` fork | 结论 |
| --- | --- | --- | --- |
| ASE I/O format 注册 | 当前安装的 ASE 中没有 `stru` 或 `abacus` format | fork 注册 `abacus`，扩展名 `.stru`，glob 为 `STRU*(?!\.*)`，magic 为 `ATOMIC_SPECIES` | 不一致 |
| 直接 `ase.io.read("*.stru")` | 失败，`UnknownFileTypeError: stru` | 支持自动识别或显式 `format="abacus"` | 不一致 |
| 直接 `ase.io.write(..., format="stru")` | 失败，`UnknownFileTypeError: stru` | 通过 ASE I/O 调用 `write_abacus()` | 不一致 |
| 项目 STRU 读入入口 | `read_structure()` 对 `STRU` / `.stru` / `format="abacus"` 分流到 `read_abacus_stru()`；`atst neb make` 的 `INIT`、`FINAL`、`--ts` 已使用该入口 | `ase.io.read(..., format="abacus")` | 调用方式不同，但常规结构读入可覆盖 |
| 项目 STRU 写出入口 | `atst abacus prepare` 直接调用 abacuslite `write_stru()` | `ase.io.write(..., format="abacus")` | 调用方式不同，但常规 ABACUS 输入准备可覆盖 |
| 基础结构字段 | 常规 STRU 中 symbols、formula、PBC、cell、positions 可保留 | 同样可保留 | 本项目基本需求可覆盖 |
| Writer 参数 | `pp_file`、`orb_file`、`fname`；当前总是写 Cartesian 坐标和默认 mobility | `scaled`、`pp`、`basis`、`offsite_basis`、`init_vel`、`pp_basis_default` 等 | fork 功能更多 |
| verbose metadata readback | `read_structure()` 返回 `Atoms`；`read_stru()` 返回解析 dict，但不写入 `Atoms.info` | `read_abacus(..., verbose=True)` 可将 pp/basis/offsite/descriptor 写入 `Atoms.info` | 不覆盖 |

相关代码路径：

- ATST 结构读入分流：`src/atst_tools/utils/io.py`
- ATST ABACUS 输入准备：`src/atst_tools/utils/abacus_io.py`
- vendored abacuslite STRU parser/writer：`src/atst_tools/external/ASE_interface/abacuslite/io/generalio.py`
- ASE fork format 注册：`temp_repos/ase-abacus/ase/io/formats.py`
- ASE fork STRU reader/writer：`temp_repos/ase-abacus/ase/io/abacus.py`

## 功能点覆盖矩阵

下表忽略库调用方式差异，只判断当前 ATST-Tools / abacuslite 是否覆盖相同的实际 STRU 功能点。

| 功能点 | 当前 ATST-Tools / abacuslite 状态 | 对本项目基本需求 | 对 fork 完整替代 |
| --- | --- | --- | --- |
| 元素类型和 species 分组 | `read_stru()` / `read_structure()` 保留元素；`write_stru()` 按元素首次出现顺序分组 | 覆盖 | 基本覆盖 |
| 赝势文件 | `read_stru()` 可解析 `pp_file`；`write_stru()` 可写出 `pp_file`；`read_structure()` 不把 pp 写入 `Atoms.info` | 覆盖 | 部分覆盖 |
| 数值轨道基组 | `read_stru()` 可解析 `NUMERICAL_ORBITAL`；`write_stru()` 可写出 `orb_file`；`read_structure()` 不把 basis 写入 `Atoms.info` | 覆盖 | 部分覆盖 |
| Cartesian 坐标读入 | `read_structure()` 可正确转换 Cartesian STRU 坐标 | 覆盖 | 覆盖 |
| Direct / 分数坐标读入 | `read_structure()` 通过 `set_scaled_positions()` 转换 Direct 坐标 | 覆盖 | 覆盖 |
| Cartesian 坐标写出 | `write_stru()` 写出 Cartesian `ATOMIC_POSITIONS` | 覆盖 | 覆盖 |
| Direct / scaled 坐标写出 | `write_stru()` 没有 `scaled` / Direct 写出选项，当前总是写 Cartesian | 当前基本需求不要求 | 不覆盖 |
| 全冻结原子 mobility 读入 | `read_structure()` 将 `m 0 0 0` / `0 0 0` 转成 `FixAtoms` | 覆盖当前常见固定原子读入 | 覆盖不完整 |
| 部分方向 mobility 读入 | `read_stru()` 可解析部分 `m` 值；`read_structure()` 只生成全冻结 `FixAtoms`，不恢复 `FixCartesian` | 当前基本需求通常不依赖 | 不覆盖为 `Atoms` 语义 |
| constraints 写回 mobility | `write_stru()` 当前对所有原子写 `m 1 1 1`，不保留 ASE `FixAtoms` / `FixCartesian` | 当前基本输入准备够用 | 不覆盖 |
| 标量磁矩 | `read_structure()` 和 `write_stru()` 可处理标量 magmom | 覆盖 | 覆盖 |
| 三分量磁矩 | `read_structure()` 和 `write_stru()` 可处理全三分量 Cartesian magmom；混合标量/三分量仍不稳健 | 覆盖常规场景 | 基本覆盖但有边界 |
| 初速度读入 | `read_stru()` 可解析 `v` / `vel` / `velocity`；`read_structure()` 不把真实速度转入 `Atoms` velocities | 当前基本需求不依赖 | 不覆盖为 `Atoms` 语义 |
| 初速度写出 | `write_stru()` 写出零速度，不保留 `Atoms.get_velocities()` | 当前基本需求不依赖 | 不覆盖 |
| `ABFS_ORBITAL` / `NUMERICAL_DESCRIPTOR` | 当前 `read_stru()` block list 不包含这些扩展块；`write_stru()` 不写出 | 当前基本需求不依赖 | 不覆盖 |
| `latname` / lattice parameter fallback | 当前 `read_structure()` 依赖 abacuslite dict 中的 lattice vectors | 当前 examples 和准备路径可满足 | 不覆盖 fork 的 latname 能力 |

因此，实际边界是：

- **可以覆盖本项目当前基本需求**：常规 ABACUS 工作流的结构读入、元素/坐标/cell/PBC/磁矩处理，以及通过 config 中的 pseudopotentials / basissets 写出 ABACUS 输入文件。
- **可以覆盖 `atst neb make` 的 STRU 输入需求**：ABACUS `STRU` / `.stru` 可作为初态、末态和 TS guess 输入；读入后生成的 ASE `Atoms` 可以继续应用 `--fix HEIGHT:DIR` 和 `--mag ELEMENT:MOMENT`。`linear` 和 `IDPP` 两种初猜链生成路径均已用 `examples/02_neb_H2-Au` 端点转换 STRU 后做一致性验证。
- **不能完整取代 `ase-abacus` fork**：需要完整 ASE I/O plugin 行为、Direct 坐标写出、constraint/mobility roundtrip、真实 velocity roundtrip、verbose metadata readback 或扩展 basis/descriptor 块时，当前实现不够。

## 验证证据

当前 `atst-dev` 环境中没有注册 `stru` 或 `abacus` ASE I/O format：

```text
$ /home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dev/bin/python -c "from ase.io.formats import ioformats; print('ase_file', __import__('ase').__file__); print('stru', 'stru' in ioformats); print('abacus', 'abacus' in ioformats); print([k for k in sorted(ioformats) if 'abacus' in k.lower() or 'stru' in k.lower()])"
ase_file /home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dev/lib/python3.10/site-packages/ase/__init__.py
stru False
abacus False
['struct', 'struct_out']
```

因此直接 ASE STRU API 会失败：

```text
ase.io.read("examples/06_relax_H2-Au/inputs/init.stru")
-> ase.io.formats.UnknownFileTypeError: stru

ase.io.read("examples/06_relax_H2-Au/inputs/init.stru", format="stru")
-> ase.io.formats.UnknownFileTypeError: stru

ase.io.read("examples/06_relax_H2-Au/inputs/init.stru", format="abacus")
-> ase.io.formats.UnknownFileTypeError: abacus

ase.io.write("/tmp/.../out.stru", atoms, format="stru")
-> ase.io.formats.UnknownFileTypeError: stru
```

`ase-abacus` fork 中 `abacus` format 已注册：

```text
$ PYTHONPATH=/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/temp_repos/ase-abacus /home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dev/bin/python -c "from ase.io.formats import ioformats; import ase; print('ase_file', ase.__file__); print('abacus_registered', 'abacus' in ioformats); print('extensions', ioformats['abacus'].extensions); print('globs', ioformats['abacus'].globs)"
ase_file /home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/temp_repos/ase-abacus/ase/__init__.py
abacus_registered True
extensions ['stru']
globs ['STRU*(?!\\.*)']
```

同一个项目示例 STRU 经 ATST 路径和 fork 路径读入后，基础结构身份一致：

```text
$ PYTHONPATH=/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/src /home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dev/bin/python -c "from atst_tools.utils.io import read_structure; p='/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/examples/06_relax_H2-Au/inputs/init.stru'; a=read_structure(p); print('atst', len(a), a.get_chemical_formula(), [round(float(x),8) for x in a.cell.lengths()])"
atst 66 H2Au64 [11.53519523, 19.06379273, 11.53519543]

$ PYTHONPATH=/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/temp_repos/ase-abacus /home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dev/bin/python -c "from ase.io import read; p='/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/examples/06_relax_H2-Au/inputs/init.stru'; a=read(p, format='abacus'); print('fork', len(a), a.get_chemical_formula(), [round(float(x),8) for x in a.cell.lengths()])"
fork 66 H2Au64 [11.53519523, 19.06379273, 11.53519543]
```

abacuslite writer 可写出常规 ABACUS STRU：

```text
$ PYTHONPATH=/home/pku-jianghong/liuzhaoqing/work/deepmodeling/atst-tools/src /home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dev/bin/python -c "import tempfile, pathlib; from ase import Atoms; from atst_tools.external.ASE_interface.abacuslite.io.generalio import write_stru, read_stru; d=tempfile.TemporaryDirectory(); p=write_stru(Atoms('H', positions=[[0,0,0]], cell=[5,5,5], pbc=True), d.name, {'H':'H.upf'}, {'H':'H.orb'}, 'STRU'); data=read_stru(p); print('abacuslite_generalio', pathlib.Path(p).name, data['species'][0]['symbol'], data['species'][0]['natom'])"
abacuslite_generalio STRU H 1
```

## 测试实践

当前 ATST 测试覆盖的是项目本地行为，而不是 fork 的完整 ASE I/O plugin contract：

- `tests/unit/test_post_analysis_io.py::test_read_structure_dispatches_abacus_stru`：确认 `read_structure()` 能读 STRU，保留 PBC、全冻结原子和磁矩。
- `tests/unit/test_post_analysis_io.py` 中 June 5 新增测试：确认 Cartesian STRU 坐标、三分量磁矩可读，同时明确当前只保留全冻结 `FixAtoms`，不会把 STRU velocity 转成真实 `Atoms` velocities。
- `tests/unit/test_abacuslite_profile.py::test_write_stru_preserves_first_occurrence_species_order`：确认 species 顺序按首次出现顺序。
- `tests/unit/test_abacuslite_profile.py` 中 June 5 新增测试：确认 `write_stru()` 写出 Cartesian 坐标、pp/orb 和磁矩，同时明确当前写出默认 mobility 和零速度，不保留 ASE constraints 或输入速度。
- `tests/unit/test_cli.py`：确认 `atst abacus prepare` 会写出 `INPUT`、`KPT` 和 `STRU`。
- `tests/unit/test_idpp.py::test_generate_from_abacus_stru_matches_example_traj_endpoints`：将 `examples/02_neb_H2-Au/inputs/init_neb_chain.traj` 的首尾帧先转换为 ABACUS STRU，再运行 `idpp.generate(method="linear")`；所得初猜链与直接结构输入链在有效数字内一致。
- `tests/unit/test_idpp.py::test_generate_idpp_from_abacus_stru_matches_example_traj_endpoints`：将同一 examples/02 首尾帧转换为 ABACUS STRU，再运行 `idpp.generate(method="IDPP")`；所得 IDPP 初猜链与直接结构输入链在机器精度内一致。该测试同时防止输入 `.traj` 自带 ASE constraints 在 IDPP 坐标写回阶段隐式改写中间 image。
- `tests/unit/test_cli.py::test_neb_make_accepts_stru_input_with_fix_and_mag`：确认 `atst neb make` 接受 ABACUS STRU 端点输入，并且读入后仍能正常应用 `--fix` 和 `--mag`。

`temp_repos/ase-abacus/ase/test/fio/abacus/test_geometry_abacus.py` 则覆盖 fork 的 ASE-level I/O 行为，包括 `Si.write(..., format="abacus")`、scaled/cartesian output、constraints、pp/basis metadata 和 `latname` lattice construction。

因此，两者测试实践的性质不同：

- ATST 测试证明当前项目 wrapper 和 abacuslite helper 对本项目工作流可用。
- fork 测试证明 ASE-native `abacus` format plugin 的公共 API 行为。

## 结论

针对 ATST-Tools 当前基本需求，结论是：

**abacuslite 的 STRU read/write 功能可以覆盖。**

理由是当前项目的核心 ABACUS 工作流只需要：

- 读入 examples / config 中的 `STRU` 初末态结构；
- 保留元素、cell、PBC、Direct/Cartesian 坐标和常规磁矩；
- 从 config 中读取 pseudopotentials / basissets；
- 通过 `atst abacus prepare` 写出 ABACUS 可用的 `INPUT`、`KPT`、`STRU`。

这些需求已经由 `read_structure()`、abacuslite `read_stru()` / `write_stru()`、`atst abacus prepare` 和现有单元测试覆盖。

针对 `atst neb make` 需要设置 `--fix` / `--mag` 的场景，结论也是：

**当前 abacuslite STRU read 路径可以满足 ATST-Tools 基本需求。**

原因是 `atst neb make` 现在对初态、末态和可选 TS guess 统一使用 `read_structure(..., parallel=False)`。当输入为 ABACUS `STRU` / `.stru` 时，该入口会通过 abacuslite parser 生成 ASE `Atoms`；随后 `set_fix_for_Atoms()` 和 `set_magmom_for_Atoms()` 直接作用在中间 image 的 ASE `Atoms` 上。因此，`--fix HEIGHT:DIR` 和 `--mag ELEMENT:MOMENT` 不依赖 ASE fork 的 `abacus` I/O format 注册，也不依赖 `ase.io.read("*.stru")` 原生可用。IDPP 写回优化坐标时也已显式忽略输入端点自带 constraints，避免 `.traj` 与 `STRU` 在 metadata 表达能力不同的情况下产生中间 image 坐标分叉。

但针对完整 `ase-abacus` fork 替代，结论是：

**当前实现不能完全取代。**

阻断项包括：

1. 没有安装态 ASE `stru` / `abacus` format 注册；
2. 没有直接 `ase.io.read/write` STRU API 兼容；
3. 没有 Direct/scaled STRU 写出选项；
4. 没有完整 ASE constraint/mobility roundtrip；
5. 没有真实初速度 roundtrip；
6. verbose metadata readback 与 fork 不一致；
7. 不覆盖 `ABFS_ORBITAL`、`NUMERICAL_DESCRIPTOR`、`latname` 等扩展能力。

工程判断：**当前 abacuslite STRU read/write 足够支撑 ATST-Tools 的基本 ABACUS 工作流；只有当项目目标升级为完整替代 `ase-abacus` fork 的 ASE I/O plugin 时，才需要补齐上述缺口。**

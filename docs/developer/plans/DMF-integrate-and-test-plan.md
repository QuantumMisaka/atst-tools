# DMF 集成与验证端到端实施计划

  ## Summary

  基于 docs/reports/DMF_DIRECT_MAXFLUX_RESEARCH_2026-06-17.html 的新版路线推进：P1 非周期基线 -> P2 PBC 实验层 -> P3
  生产级案例验收 -> P4 D2S 支持。.trae/specs/plan-dmf-integration-validation 仍保留旧的 P2=D2S 顺序，实施第一步必须先
  同步 SPEC/tasks/checklist，避免代码按过时路线开发。

  依赖策略按用户选择：完整 vendored PyDMF，不依赖外部 pydmf 包；但 cyipopt/IPOPT 仍作为运行环境前提。验证环境以克隆
  dpeva-dpa4-test 为基线，补齐当前 ATST 与 cyipopt。

  ## Current Status (2026-06-18)

  - P0 spec alignment: done. `.trae/specs/plan-dmf-integration-validation/{spec,tasks,checklist}.md` 已同步为 P1 非周期、P2 PBC、P3 生产案例、P4 D2S。
  - P0 environment alignment: cache-local smoke done. home 下 `conda create -n atst-dmf-dpa4 --clone dpeva-dpa4-test -y` 曾因 `Disk quota exceeded` 失败；已改在 `/cache_local/liuzhaoqing/atst-dmf-dpa4` 克隆 `dpeva-dpa4-test`，安装 `cyipopt`/IPOPT，并 `pip install -e .` 当前工作树。
  - P1 non-periodic standalone: code/schema/CLI/tests/docs/example done. 已新增 `calculation.type: dmf`、`DMFWorkflow`、vendored PyDMF、`examples/16_dmf_nonperiodic/`。
  - P1 runtime dependency smoke: done. `/cache_local/liuzhaoqing/atst-dmf-dpa4` 已通过 `ase/torch/deepmd/cyipopt/atst_tools` import smoke、vendored PyDMF NumPy/torch import smoke，以及 direct PyDMF + ASE EMT `cfbenm -> DirectMaxFlux -> tmax` smoke。证据见 `docs/reports/DMF_ENVIRONMENT_SMOKE_2026-06-18.md`。
  - P2 PBC experimental guard: code/schema/tests/example/docs done for the guard layer. 已新增 `examples/17_dmf_pbc_cartesian_unwrapped/`，要求 fixed cell、预 unwrap Cartesian、`initial_path: linear`、`confirm_pbc_risk: true`、`remove_rotation_and_translation: false`。
  - P3 production validation: candidate-comparison runtime done, refinement/TS validation not done. `examples/18_dmf_production_validation/` 已在 SAI job `525521` 完成 `01_neb_Li-Si` 与 `02_neb_H2-Au` 两个 DMF `tmax` candidate 生成，并通过 `scripts/validate_dmf_candidates.py` 对比 ABACUS/DP references；证据见 `docs/reports/DMF_P3_RUNTIME_VALIDATION_2026-06-18.md`。候选尚未接 Dimer/Sella/CCQN refinement，也未做 vibration/IRC TS validation，因此 DMF 仍只能标记为 experimental。
  - P4 D2S support: unit-level runtime integration, SAI Sella smoke, focused vibration validation, focused descent-IRC endpoint validation, and ABACUS single-point comparison done for the two-case evidence set. Schema 已提供 `rough_method: neb|dmf` 且默认 `neb`；`rough_method=dmf` 现在会复用 standalone DMF runner 生成 rough path 和 `tmax` candidate，再接现有 Dimer/Sella/CCQN/vibration stage。SAI job `526327` 已完成 Li-Si 与 H2-Au 两个 `rough_method: dmf -> Sella` smoke，证据见 `docs/reports/DMF_P4_D2S_RUNTIME_SMOKE_2026-06-18.md`。SAI job `526601` 已完成同两案例 `rough_method: dmf -> Sella -> focused vibration` 验证，局域模式均得到一个虚频，证据见 `docs/reports/DMF_P4_D2S_VIBRATION_VALIDATION_2026-06-18.md`。SAI job `526657` 已完成同两案例 `rough_method: dmf -> Sella -> focused vibration -> descent IRC endpoint` 验证，局域反应原子端点 RMSD 均通过 `0.25 A` 阈值，证据见 `docs/reports/DMF_P4_D2S_IRC_ENDPOINT_VALIDATION_2026-06-18.md`。SAI job `526738` 完成初始 ABACUS comparison，H2-Au raw force gate 失败；SAI job `526921` 完成 H2-Au corrective ABACUS Sella；SAI job `527093` 完成 refined ABACUS comparison，Li-Si 与 H2-Au 均通过 barrier/RMSD/constrained-fmax gate，证据见 `docs/reports/DMF_P4_D2S_ABACUS_COMPARISON_2026-06-18.md`。该路径仍标 experimental，不能替代默认 rough NEB。

  Latest local verification:

  - `pytest tests/unit/test_config.py tests/unit/test_cli.py tests/unit/test_dmf_workflow.py -q`
  - `atst config validate examples/16_dmf_nonperiodic/config_dp.yaml --print-normalized`
  - `atst config validate examples/17_dmf_pbc_cartesian_unwrapped/config_dp.yaml --print-normalized`
  - `atst config validate examples/18_dmf_production_validation/config_01_Li-Si_dmf_dp.yaml --print-normalized`
  - `atst config validate examples/18_dmf_production_validation/config_02_H2-Au_dmf_dp.yaml --print-normalized`
  - `python scripts/validate_dmf_candidates.py --help`
  - `atst run --show-template dmf --calculator dp`
  - `/cache_local/liuzhaoqing/atst-dmf-dpa4/bin/python -c "import ase, torch, deepmd, cyipopt; import atst_tools"`
  - direct vendored PyDMF + ASE EMT smoke under `/cache_local/liuzhaoqing/atst-dmf-smoke-20260618`
  - SAI Slurm job `525521`: `examples/18_dmf_production_validation/submit_dmf_dp_rush_1gpu.sbatch`, `COMPLETED`, exit `0:0`, elapsed `00:02:41`
  - SAI Slurm job `526327`: `examples/18_dmf_production_validation/submit_d2s_dmf_sella_dp_rush_1gpu.sbatch`, `COMPLETED`, exit `0:0`, elapsed `00:02:56`
  - SAI Slurm job `526601`: `examples/18_dmf_production_validation/submit_d2s_dmf_sella_vib_dp_rush_1gpu.sbatch`, `COMPLETED`, exit `0:0`, elapsed `00:02:32`
  - SAI Slurm job `526657`: `examples/18_dmf_production_validation/submit_d2s_dmf_irc_dp_rush_1gpu.sbatch`, `COMPLETED`, exit `0:0`, elapsed `00:02:07`
  - SAI Slurm job `526738`: `examples/18_dmf_production_validation/submit_d2s_dmf_abacus_compare_rush_gpu.sbatch`, `COMPLETED`, exit `0:0`, elapsed `00:03:51`, initial suite status `fail` due H2-Au raw ABACUS force gate.
  - SAI Slurm job `526921`: `examples/18_dmf_production_validation/submit_h2au_dmf_abacus_sella_rush_gpu.sbatch`, `COMPLETED`, exit `0:0`, elapsed `00:15:46`, H2-Au corrective ABACUS Sella final `fmax=0.0992 eV/A`.
  - SAI Slurm job `527093`: `examples/18_dmf_production_validation/submit_d2s_dmf_abacus_refined_compare_rush_gpu.sbatch`, `COMPLETED`, exit `0:0`, elapsed `00:03:47`, refined suite status `pass` for Li-Si and H2-Au using constrained candidate forces.

  ## Key Changes

  - Vendor PyDMF:
      - 将 temp_repos/dmf 的完整上游源码引入 src/atst_tools/external/pydmf/，保留 LICENSE、README、upstream commit
        ed7ed53 和 UPSTREAM.md。

      - Python import 走 atst_tools.external.pydmf.dmf，不污染顶层 dmf 包名。
      - 保留 torch 后端源码；torch 后端不作为 P1 默认路径，但纳入 import smoke。

  - 新增 standalone DMF workflow:
      - 新增 calculation.type: dmf，定位为 experimental TS candidate/path optimizer。
      - 最小 YAML 字段：init_file、final_file、directory、trajectory、tmax_trajectory、summary_file、
        artifact_manifest、initial_path: linear|fbenm|cfbenm、nsegs、dspl、nmove、beta、update_teval、tol、parallel、
        remove_rotation_and_translation、pbc_mode: reject|cartesian_unwrapped、confirm_pbc_risk。

      - 默认：initial_path=cfbenm、pbc_mode=reject、confirm_pbc_risk=false、remove_rotation_and_translation=true。

  - PBC guard:
      - 若端点 Atoms.pbc.any() 且 pbc_mode=reject，拒绝运行。
      - 若 pbc_mode=cartesian_unwrapped，必须 confirm_pbc_risk=true 且 remove_rotation_and_translation=false；要求端
        点 cell/PBC 一致，只按当前 Cartesian positions 运行，不声称 MIC/fractional 支持。

  - 输出语义：
      - 写出 DMF evaluation path、tmax candidate trajectory、JSON summary、artifact manifest。
      - `tmax` candidate 在写入前会做一次 single-point energy/forces 评估，便于后续 refinement/validation 工具读取候选能量与 `fmax`。
      - summary 明确标记 experimental=true、result_type=ts_candidate、validated_ts=false。

  - D2S 后置：
      - P4 才新增 calculation.d2s.rough_method: neb|dmf，默认仍为 neb。
      - rough_method=dmf 复用 standalone DMF runner 生成 tmax，再接现有 Dimer/Sella/CCQN 和 vibration/IRC
        validation。

  ## Implementation Phases

  - P0 spec/env alignment:
      - 更新 .trae/specs/plan-dmf-integration-validation/{spec,tasks,checklist}.md，把阶段顺序改为 P1 非周期、P2
        PBC、P3 生产案例、P4 D2S。

      - 克隆环境：conda create -n atst-dmf-dpa4 --clone dpeva-dpa4-test。
      - 安装验证依赖：conda install -n atst-dmf-dpa4 -c conda-forge cyipopt ipopt，再用该环境 pip install -e .。

  - P1 non-periodic standalone:
      - 修改 schema、template、dispatch，新增 DMFWorkflow。
      - 用 EMT/DP 小分子或 cluster example 验证 non-PBC cfbenm -> DirectMaxFlux -> tmax。
      - 新增 atst run --show-template dmf、atst run --list-types 覆盖。

  - P2 PBC experimental:
      - 加入 PBC runtime guard 和 cartesian_unwrapped 实验路径。
      - 添加 DP 快速 toy PBC case，验证固定 cell、同一周期图像、关闭 rotation/translation removal。
      - 禁止 fbenm/cfbenm 默认用于 PBC；PBC 实验默认使用 linear 或显式预处理路径。

  - P3 production validation:
      - 用 Li migration、H2-Au adsorbate dissociation、Cy-Pt 或 Zn migration 中至少两个案例做 DP/ABACUS 对照 CI-NEB。
      - 当前已完成 Li-Si 与 H2-Au 的 staging configs、Slurm 入口、candidate-vs-reference report harness 和 SAI runtime candidate comparison；尚未完成 refinement、TS mode、IRC endpoint connection 验证。

  - P4 D2S integration:
      - 在 D2SCalculation 加 rough_method: neb|dmf 和嵌套 dmf 配置。
      - 重构 D2S rough stage：neb 走现有 run_rough_neb()；dmf 走 DMF runner 并返回 candidate chain/candidate atoms。
      - manifest 记录 dmf_candidate -> single_ended -> validation 关系。
      - 当前已完成 unit-level runtime integration、SAI `rough_method: dmf -> Sella` smoke、focused vibration validation、focused descent-IRC endpoint validation 与 ABACUS single-point comparison；H2-Au corrective ABACUS refinement 后 refined comparison 通过 constrained-fmax gate。

  ## Test Plan

  - Unit tests:
      - tests/unit/test_config.py: dmf schema defaults、PBC guard config、templates validate、unknown fields
        rejected、D2S rough_method defaults.

      - tests/unit/test_cli.py: --list-types 包含 dmf，--show-template dmf 输出 experimental/PBC 提示。
      - 新增 tests/unit/test_dmf_workflow.py: monkeypatch vendored PyDMF runner，验证 dispatch、dependency error、
        manifest、summary、PBC rejection、PBC confirmation。

      - Vendor smoke: import NumPy and torch PyDMF namespaces；cyipopt 缺失时错误信息可执行。

  - Local commands:
      - pytest tests/unit/test_config.py tests/unit/test_cli.py tests/unit/test_dmf_workflow.py -q
      - python scripts/generate_yaml_reference.py 或项目现有 YAML 文档生成命令后，运行 pytest tests/unit/
        test_config.py -q

      - python scripts/check_docs_governance.py
      - git diff --check -- README.md docs examples/README.md AGENTS.md

  - Environment validation:
      - /home/pku-jianghong/liuzhaoqing/.conda/envs/atst-dmf-dpa4/bin/python -c "import ase, torch, deepmd, cyipopt;
        import atst_tools"

      - GPU/Slurm 验证只通过 sbatch 提交，不在登录节点跑重计算。

  ## Docs And Examples

  - 新增 examples/16_dmf_nonperiodic/ 作为 P1 smoke。
  - P2 新增实验性 PBC example，但 README 必须写明 cartesian_unwrapped 限制。
  - 更新 README.md、docs/user/CONFIG_REFERENCE.md、docs/user/YAML_INPUT_VARIABLES.md、docs/user/USER_GUIDE_CN.md、
    examples/README.md。

  - 更新 docs/reports/FEATURE_STATUS_MATRIX.md：DMF 标为 experimental，不进入生产级 supported。
  - P3 完成后新增 runtime validation report，并同步 docs/reports/DOCUMENTATION_STATUS_REPORT.md。

  ## Assumptions

  - HTML 报告优先于 .trae 旧 SPEC 的阶段顺序；实施时先修订 SPEC。
  - Vendored PyDMF 允许按 MIT license 引入，必须保留许可证和上游来源。
  - 首轮不实现 fractional-coordinate/MIC-aware DMF；PBC 仅限固定 cell、预 unwrap、Cartesian 实验模式。
  - D2S 支持可作为实验性 opt-in rough stage 接入，但默认路径必须保持 `rough_method: neb`，且在 refinement、vibration/IRC runtime 验收完成前不得标为 supported 生产路径。

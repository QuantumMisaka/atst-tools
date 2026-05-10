# Tasks（更新版）

## Priority 1 - High Priority (Core Robustness)
- [x] Task 1.1: 实现共享 restart/cache helper
  - [x] Subtask 1.1.1: 新建 `utils/restart_helpers.py`
  - [x] Subtask 1.1.2: 实现 `get_last_frame(traj_file)`
  - [x] Subtask 1.1.3: 实现 `get_last_neb_band(traj_file, expected_n_images)`
  - [x] Subtask 1.1.4: 实现 `check_cache_files(vib_dir)` 和 `clean_cache_files(vib_dir, keep_good=True)`
  - [x] Subtask 1.1.5: 添加单元测试
- [x] Task 1.2: 完善 Vibration 续跑机制
  - [x] Subtask 1.2.1: 修改 `vibration.py` 的 `_prepare_cache` 方法，使用共享 helper
  - [x] Subtask 1.2.2: 更新 `_vibration_post_command` 添加详细错误提示
  - [x] Subtask 1.2.3: 测试验证功能
- [x] Task 1.3: 完善 NEB/D2S/Dimer/Sella/Relax 续算
  - [x] Subtask 1.3.1: 修改 `main.py` 中的 `run_neb` 使用共享 helper
  - [x] Subtask 1.3.2: 修改 `dimer.py`、`sella.py`、`relax.py` 中的 restart 逻辑
  - [x] Subtask 1.3.3: 修改 `d2s.py` 使用共享 helper
  - [x] Subtask 1.3.4: 添加不完整 trajectory 时的明确异常

## Priority 2 - Medium Priority (Feature Enhancements)
- [x] Task 2.1: 实现 `atst relax post` 命令
  - [x] Subtask 2.1.1: 在 `cli.py` 中添加 relax 子命令
  - [x] Subtask 2.1.2: 实现读取轨迹、输出能量/受力、保存结构
  - [x] Subtask 2.1.3: 测试验证功能
- [x] Task 2.2: 实现 IRC 计算支持
  - [x] Subtask 2.2.1: 研究并确认 sella.IRC 的使用方式
  - [x] Subtask 2.2.2: 在 `workflows/` 中添加 `irc.py`
  - [x] Subtask 2.2.3: 在 `main.py` 中添加 dispatch
  - [x] Subtask 2.2.4: 添加配置模板
  - [x] Subtask 2.2.5: 添加单元测试
- [x] Task 2.3: 参数简化和兼容
  - [x] Subtask 2.3.1: 将 dimer make-from-neb 的 `--output-structure` 重命名为 `--output-traj`
  - [x] Subtask 2.3.2: 保留 `--output-structure` 作为隐藏兼容别名

## Priority 3 - Low Priority (Usability/Documentation)
- [x] Task 3.1: 增强 CLI help 和文档
  - [x] Subtask 3.1.1: 增强各个子命令的 help 信息
  - [x] Subtask 3.1.2: 在 abacuslite factory 中添加来源提示信息（仅记录一次）
  - [x] Subtask 3.1.3: 更新 README.md
  - [x] Subtask 3.1.4: 更新 docs/index.md
  - [x] Subtask 3.1.5: 更新 CLI_REFERENCE.md
  - [x] Subtask 3.1.6: 更新 CONFIG_REFERENCE.md
  - [x] Subtask 3.1.7: 新增正式报告到 docs/reports/
- [x] Task 3.2: 集成/烟测和工作树检查
  - [x] Subtask 3.2.1: 运行 pytest tests -q
  - [x] Subtask 3.2.2: 运行 python -m compileall -q src/atst_tools tests
  - [x] Subtask 3.2.3: 运行 git status --short 检查
  - [x] Subtask 3.2.4: 运行 git check-ignore -v 验证

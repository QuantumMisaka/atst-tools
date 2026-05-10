# Checklist（更新版）

## Priority 1 - High Priority (Core Robustness)
- [ ] 共享 restart/cache helper 已实现
- [ ] `get_last_frame(traj_file)` 已实现并测试
- [ ] `get_last_neb_band(traj_file, expected_n_images)` 已实现并测试
- [ ] `check_cache_files(vib_dir)` 和 `clean_cache_files(vib_dir, keep_good=True)` 已实现并测试
- [ ] Vibration `_prepare_cache` 使用共享 helper，restart=true 时保留好 cache、删除坏 cache
- [ ] Vibration `_prepare_cache` 在非 restart 时清空整个 vib 目录
- [ ] `_vibration_post_command` 有详细的错误提示
- [ ] NEB restart 使用共享 helper，从目标 trajectory 读取最后完整 band，并校验 image 数
- [ ] NEB restart 在不完整 trajectory 时抛出明确异常
- [ ] D2S 使用同一 helper 判断是否可续算
- [ ] Dimer/Sella/Relax restart 从对应 trajectory 最后一帧续算
- [ ] Dimer/Sella/Relax 在 trajectory 不存在或不可读时给出明确错误，不静默回退

## Priority 2 - Medium Priority (Feature Enhancements)
- [ ] `atst relax post` 命令已实现
- [ ] 支持 `--ind` 参数指定帧
- [ ] 支持多种输出格式（默认 stru）
- [ ] 正确输出能量和最大原子受力
- [ ] IRC 计算支持已添加（`calculation.type: irc`）
- [ ] IRC workflow 已实现，基于 sella.IRC
- [ ] IRC 集成到 main.py
- [ ] IRC 配置模板已添加
- [ ] dimer make-from-neb 使用 `--output-traj` 作为公开参数
- [ ] `--output-structure` 保留为隐藏兼容别名

## Priority 3 - Low Priority (Usability/Documentation)
- [ ] 所有 CLI 子命令的 help 信息已增强
- [ ] abacuslite factory 中有来源提示信息，且仅记录一次
- [ ] README.md 已更新
- [ ] docs/index.md 已更新
- [ ] CLI_REFERENCE.md 已更新
- [ ] CONFIG_REFERENCE.md 已更新
- [ ] 新增正式报告到 docs/reports/
- [ ] pytest tests -q 已通过
- [ ] python -m compileall -q src/atst_tools tests 已通过
- [ ] git status --short 不出现新 Slurm/ABACUS/vibration/trajectory 输出
- [ ] git check-ignore -v 验证运行输出被 ignore，examples/tests 输入未被 ignore

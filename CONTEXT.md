# WhisperKey / Vibemouse Mac — 项目上下文

> 手动刷新 | 2026-03-06

## 如何恢复工作

- **使用的 Skill**: direct
- **推荐恢复命令**: `./start.sh`
- **底层启动命令**: `.venv/bin/python -m whisperkey_mac.main`

## 当前状态

- **产品当前名称**: WhisperKey
- **仓库目录名**: `20260302__python__vibemouse-mac`（历史命名，尚未改目录）
- **完成度**: MVP 已成型，可本地运行，后台自启动已恢复
- **最近处理日期**: 2026-03-06

## 已确认能力

- 已有 CLI 入口、首次运行向导、热键监听、录音、转录、文本注入、帮助诊断
- `pyproject.toml` 当前包名为 `whisperkey-mac`，命令入口为 `whisperkey`
- `README.md` / `README.zh.md` 已切换到 WhisperKey 品牌

## 本轮已修复

- 修复本地启动链：`start.sh` 不再依赖易失的 console script，改为直接运行 `python -m whisperkey_mac.main`
- `WhisperKey.command` 现在委托给 `start.sh`
- 更新 `.gitignore` 中的旧日志/配置路径注释
- 为 README 增加 Python 3.10+ 的明确提示，避免 macOS 系统 Python 3.8 导致环境创建失败
- 已使用 Python 3.12 重建本地 `.venv` 并完成 `pip install -e .`
- 已验证 `./start.sh help` 与 `.venv/bin/whisperkey help` 可以正常启动诊断命令
- 已完成一次自动化 `setup`，配置文件已生成到 `~/.config/whisperkey/config.json`
- 已修复开机自启：旧的 `com.vibemouse` LaunchAgent 已停用并备份，新的 `com.whisperkey` 已安装到 `~/Library/Application Support/whisperkey/venv` 并成功加载运行
- 已清理旧残留：`~/Library/Application Support/vibemouse`、`~/.config/vibemouse`、`/tmp/vibemouse.log`

## 当前阻塞 / 风险

- 首次模型下载仍需要联网（HuggingFace）
- macOS 运行仍依赖 **辅助功能** 与 **输入监控** 权限
- 已确认模型缓存存在、配置文件存在、后台 LaunchAgent 运行中；真实录音与粘贴链路仍建议手动验证一次
- 仓库目录名仍保留 `vibemouse-mac`，若要完全统一品牌，需要单独处理目录/远端/发布资产

## 下一步建议

1. 重开机一次，确认 `com.whisperkey` 会自动恢复运行
2. 执行一次真实录音转写，验证热键、模型、粘贴与权限链路
3. 如需节省空间，可评估是否删除未使用的 `base` 模型缓存（约 141MB）
4. 如需品牌完全统一，再处理目录名与发布资产中的 `vibemouse-mac` 历史命名

## 关键链接

- GitHub: https://github.com/Phat-Po/whisperkey-mac

# Proposal: V1.14.19 Local Data Management

## Why
Windows 安装版把程序文件和用户数据分开保存。用户把 MINOS-CORE 安装到其它盘符后，旧项目、运行记录和输出仍会留在 `%LOCALAPPDATA%\MINOS-CORE`，但设置页没有入口解释、备份或清空这些数据。

## What
- 在桌面设置页显示数据目录、数据库、输出目录、日志目录和备份目录。
- 提供本地数据备份 zip，包含 SQLite 数据库、输出文件、日志和 manifest。
- 提供 `workspace` 清空和 `factory_reset` 两种清理入口。
- 清空项目/run 时保留备份目录；恢复初始状态后重新 seed 默认知识规则。
- 备份 SQLite 时使用在线 backup API，确保 WAL 中已提交数据进入备份。

## Non-goals
- 不做自动数据迁移。
- 不改变默认用户数据目录。
- 不删除 Codex、OpenAI 环境变量或系统级密钥。

## Acceptance
- 设置页能看到本地数据路径、数量、大小和最后备份。
- 备份 zip 可打开，且包含完整 SQLite 数据库、`out/`、`logs/` 和 `backup_manifest.json`。
- WAL 模式下已提交数据能进入备份 SQLite。
- 清空项目/run 不删除备份；恢复初始状态后知识规则仍可用。

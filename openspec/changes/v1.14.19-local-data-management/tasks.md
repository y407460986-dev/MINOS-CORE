# Tasks: V1.14.19 Local Data Management

## Define
- [x] /// 1. 明确问题：安装目录不是数据目录，用户需要看见和管理 `%LOCALAPPDATA%\MINOS-CORE`。
- [x] /// 2. 明确非目标：不迁移数据、不删除外部密钥、不改变默认数据目录。

## Specify
- [x] /// 3. 定义数据管理状态字段：路径、项目数、run 数、知识规则数、输出大小、数据库大小、最后备份。
- [x] /// 4. 定义备份内容：SQLite 数据库、`out/`、`logs/`、`backup_manifest.json`。
- [x] /// 5. 定义清空语义：`workspace` 保留设置/知识规则，`factory_reset` 重置设置/知识规则并重新 seed。

## Implement
- [x] /// 6. 新增 `DesktopDataManagementService`。
- [x] /// 7. 新增 settings 数据管理 API。
- [x] /// 8. 新增 Tauri 设置页数据管理卡片和打开路径命令。
- [x] /// 9. 将 SQLite 备份改为在线 backup API，覆盖 WAL 数据。

## Verify
- [x] /// 10. 服务层测试覆盖状态、备份、WAL、清空和恢复初始状态。
- [x] /// 11. API 测试覆盖状态、备份和清空。
- [x] /// 12. Tauri 静态测试覆盖设置页入口。

# Design: V1.14.19 Local Data Management

## Boundary
本功能属于桌面 sidecar 的本地数据管理能力，不改变三表生成、AI 推理或导出业务规则。

## Service
`DesktopDataManagementService` 复用现有 SQLite 连接和迁移逻辑：
- `get_status()` 只读统计路径、表数量和目录大小。
- `create_backup()` 先用 `sqlite3.Connection.backup()` 生成临时数据库，再压缩数据库、输出目录、日志目录和 manifest。
- `clear_data()` 使用 SQL 删除业务表数据，避免运行中直接删除 SQLite 文件。

## UI
设置页展示数据管理卡片：
- 路径用等宽文本显示。
- 备份和打开目录是普通操作。
- 清空项目和恢复初始状态要求用户输入固定确认文字。

## Safety
- 备份目录固定在数据目录 `backups` 下。
- 删除输出目录内容时保留 `backups`。
- `factory_reset` 只清 MINOS SQLite 内部设置和知识规则，不碰系统环境变量或 Codex 文件。

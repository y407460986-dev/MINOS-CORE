# Design: V3.2.1 MinerU Late Failure Recovery

## Failure Shape
真实失败记录的关键片段是：

- MinerU CLI 启动本地 `mineru-api`。
- VLM layout 阶段已经跑到 `100%`。
- 后续 extract/predict 阶段报 `All connection attempts failed`。
- MINOS 收到 MinerU 子进程非零退出，直接抛出 `MinerU OCR failed`。

这说明失败点在 MinerU 本地解析服务/后处理链路，不是 MINOS 的文本 AI 配置，也不是 PFD 生成阶段。

## Recovery Rule
`MinerUOCRAdapter._run_local_mineru(...)` 保持现有 CLI 调用方式。唯一恢复规则是：

1. 子进程正常退出：读取输出目录第一份 Markdown。
2. 子进程非零退出：先读取输出目录第一份 Markdown。
3. 如果 Markdown 存在且可读：返回该内容，继续转换为 OCR page/block evidence。
4. 如果 Markdown 不存在：保留原始异常信息，抛出 `OCRDependencyError`。
5. 如果 MinerU 可执行文件启动失败：直接抛出依赖错误，不复用目录里的旧文件。

这样不会把半成品伪装成完整结果；只有 MinerU 已经落盘了可读 Markdown 时才继续。

## Failure Message
桌面失败格式仍保留：

- 原始错误
- 原因判断
- 处理方案
- 放弃任务

但 `_guess_failure_reason(...)` / `_default_failure_actions(...)` 在通用 `api/key` 判断前先匹配 MinerU 本地连接失败，避免 `mineru-api` 命中 AI 配置规则。

## Risk
如果用户显式传入长期复用的 MinerU 输出目录，目录里可能已有旧 Markdown。当前桌面默认不传持久 MinerU 输出目录，使用临时目录；回归测试模拟的是本次 CLI 运行中写出 Markdown 后失败的场景。后续如果要把 MinerU 输出目录持久化，需要在调用前清空本次任务目录或按输入文件名/时间戳定位结果。
